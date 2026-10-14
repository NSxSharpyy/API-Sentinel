use std::mem::size_of;

use api_sentinel_ebpf_common::NetworkEvent;
use aya::{
    maps::RingBuf,
    programs::{KProbe, TracePoint},
};
use log::{debug, warn};
use tokio::signal;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    env_logger::init();

    // Remove the memory-lock limit for older kernels.
    let rlim = libc::rlimit {
        rlim_cur: libc::RLIM_INFINITY,
        rlim_max: libc::RLIM_INFINITY,
    };

    let ret = unsafe { libc::setrlimit(libc::RLIMIT_MEMLOCK, &rlim) };

    if ret != 0 {
        debug!("remove limit on locked memory failed, ret is: {ret}");
    }

    // Load the compiled eBPF object.
    let mut ebpf = aya::Ebpf::load(aya::include_bytes_aligned!(concat!(
        env!("OUT_DIR"),
        "/api-sentinel-ebpf"
    )))?;

    // Attach the TCP lifecycle tracepoint.
    {
        let program: &mut TracePoint = ebpf
            .program_mut("api_sentinel_ebpf")
            .ok_or_else(|| anyhow::anyhow!("tracepoint program not found"))?
            .try_into()?;

        program.load()?;
        program.attach("sock", "inet_sock_set_state")?;
    }

    // Attach the IPv4 connect kprobe.
    {
        let connect_program: &mut KProbe = ebpf
            .program_mut("api_sentinel_tcp_v4_connect")
            .ok_or_else(|| anyhow::anyhow!("connect kprobe not found"))?
            .try_into()?;

        connect_program.load()?;
        connect_program.attach("tcp_v4_connect", 0)?;
    }

    // Take ownership of the EVENTS ring-buffer map.
    let event_map = ebpf
        .take_map("EVENTS")
        .ok_or_else(|| anyhow::anyhow!("EVENTS map not found"))?;

    let ring_buf = RingBuf::try_from(event_map)?;

    let mut ring_buf =
        tokio::io::unix::AsyncFd::with_interest(ring_buf, tokio::io::Interest::READABLE)?;

    let ctrl_c = signal::ctrl_c();
    tokio::pin!(ctrl_c);

    println!("API-Sentinel: listening for structured TCP events...");
    println!("Press Ctrl-C to stop.");

    loop {
        tokio::select! {
            result = &mut ctrl_c => {
                result?;
                break;
            }

            result = ring_buf.readable_mut() => {
                let mut guard = result?;

                while let Some(item) = guard.get_inner_mut().next() {
                    if item.len() != size_of::<NetworkEvent>() {
                        warn!(
                            "Ignoring event with unexpected size: {} bytes",
                            item.len()
                        );
                        continue;
                    }

                    // Copy the event from the ring buffer.
                    let event = unsafe {
                        std::ptr::read_unaligned(
                            item.as_ptr().cast::<NetworkEvent>()
                        )
                    };

                    let process = if event.attribution_known == 1 {
                        event.tgid.to_string()
                    } else {
                        "UNKNOWN".to_string()
                    };

                    println!(
                        "NET_EVENT tgid={} family={} protocol={} \
                         tcp_state={}->{} \
                         src={}.{}.{}.{}:{} \
                         dst={}.{}.{}.{}:{}",
                        process,
                        event.family,
                        event.protocol,
                        event.old_state,
                        event.new_state,
                        event.source_ipv4[0],
                        event.source_ipv4[1],
                        event.source_ipv4[2],
                        event.source_ipv4[3],
                        event.source_port,
                        event.destination_ipv4[0],
                        event.destination_ipv4[1],
                        event.destination_ipv4[2],
                        event.destination_ipv4[3],
                        event.destination_port,
                    );
                }

                guard.clear_ready();
            }
        }
    }

    println!("Exiting...");
    Ok(())
}
