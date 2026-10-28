use std::{mem::size_of, process::Command};

use anyhow::Context;
use api_sentinel_ebpf_common::{
    EVENT_TYPE_HTTP_REQUEST, EVENT_TYPE_TCP_STATE, HTTP_METHOD_DELETE, HTTP_METHOD_GET,
    HTTP_METHOD_HEAD, HTTP_METHOD_OPTIONS, HTTP_METHOD_PATCH, HTTP_METHOD_POST, HTTP_METHOD_PUT,
    NetworkEvent,
};
use aya::{
    maps::{HashMap, PerCpuArray, RingBuf},
    programs::{KProbe, SchedClassifier, TcAttachType, TracePoint, tc},
};
use log::{debug, warn};
use tokio::signal;

const INTERFACE: &str = "ens33";

fn direction_name(value: u8) -> &'static str {
    match value {
        1 => "EAST-WEST",
        2 => "NORTH-SOUTH",
        _ => "UNKNOWN/OTHER",
    }
}

fn method_name(value: u8) -> &'static str {
    match value {
        HTTP_METHOD_GET => "GET",
        HTTP_METHOD_POST => "POST",
        HTTP_METHOD_PUT => "PUT",
        HTTP_METHOD_DELETE => "DELETE",
        HTTP_METHOD_PATCH => "PATCH",
        HTTP_METHOD_HEAD => "HEAD",
        HTTP_METHOD_OPTIONS => "OPTIONS",
        _ => "UNKNOWN",
    }
}

fn ensure_clsact(interface: &str) -> anyhow::Result<()> {
    let output = Command::new("tc")
        .args(["qdisc", "show", "dev", interface])
        .output()
        .with_context(|| format!("Could not inspect qdisc on {interface}"))?;

    if !output.status.success() {
        anyhow::bail!("tc qdisc check failed for {interface}");
    }

    let listing = String::from_utf8_lossy(&output.stdout);
    if listing
        .lines()
        .any(|line| line.trim_start().starts_with("qdisc clsact"))
    {
        println!("clsact already exists on {interface}");
        return Ok(());
    }

    tc::qdisc_add_clsact(interface)?;
    println!("Added clsact to {interface}");
    Ok(())
}

fn read_total_drops(
    drops_map: &PerCpuArray<&mut aya::maps::MapData, u64>,
) -> anyhow::Result<u64> {
    let values = drops_map.get(&0, 0)?;
    Ok(values.iter().copied().fold(0u64, u64::wrapping_add))
}

fn print_event(event: &NetworkEvent) {
    if event.event_type == EVENT_TYPE_HTTP_REQUEST {
        let len = usize::from(event.uri_len).min(event.uri_prefix.len());
        let uri = String::from_utf8_lossy(&event.uri_prefix[..len]);

        println!(
            "HTTP_REQUEST method={} client_id={} uri_prefix={} direction={} \
             src={}.{}.{}.{}:{} dst={}.{}.{}.{}:{}",
            method_name(event.http_method),
            event.client_id,
            uri,
            direction_name(event.traffic_direction),
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
    } else if event.event_type == EVENT_TYPE_TCP_STATE {
        let process = if event.attribution_known == 1 {
            event.tgid.to_string()
        } else {
            "UNKNOWN".to_string()
        };

        println!(
            "NET_EVENT tgid={} direction={} family={} protocol={} \
             tcp_state={}->{} src={}.{}.{}.{}:{} dst={}.{}.{}.{}:{}",
            process,
            direction_name(event.traffic_direction),
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
    } else {
        warn!("Unknown event type: {}", event.event_type);
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    env_logger::init();

    let rlim = libc::rlimit {
        rlim_cur: libc::RLIM_INFINITY,
        rlim_max: libc::RLIM_INFINITY,
    };

    let ret = unsafe { libc::setrlimit(libc::RLIMIT_MEMLOCK, &rlim) };
    if ret != 0 {
        debug!("setrlimit(RLIMIT_MEMLOCK) returned {ret}");
    }

    let mut ebpf = aya::Ebpf::load(aya::include_bytes_aligned!(concat!(
        env!("OUT_DIR"),
        "/api-sentinel-ebpf"
    )))?;

    {
        let program: &mut TracePoint = ebpf
            .program_mut("api_sentinel_ebpf")
            .context("TCP tracepoint program not found")?
            .try_into()?;
        program.load()?;
        program.attach("sock", "inet_sock_set_state")?;
        println!("TCP lifecycle tracepoint attached");
    }

    {
        let program: &mut KProbe = ebpf
            .program_mut("api_sentinel_tcp_v4_connect")
            .context("TCP connect kprobe not found")?
            .try_into()?;
        program.load()?;
        program.attach("tcp_v4_connect", 0)?;
        println!("TCP connect kprobe attached");
    }

    ensure_clsact(INTERFACE)?;

    {
        let program: &mut SchedClassifier = ebpf
            .program_mut("api_sentinel_http_classifier")
            .context("HTTP classifier program not found in eBPF object")?
            .try_into()?;
        program.load()?;
        program.attach(INTERFACE, TcAttachType::Egress)?;
        println!("HTTP classifier attached to {INTERFACE} egress");
    }

    // Day 10: userspace-to-kernel client-map smoke test.
    // 192.0.2.10 is a documentation-only example address.
    {
        let mut clients = HashMap::<_, u32, u32>::try_from(
            ebpf.map_mut("CLIENT_IDENTIFIERS")
                .ok_or_else(|| anyhow::anyhow!("CLIENT_IDENTIFIERS map not found"))?,
        )?;

        let test_ip = u32::from_ne_bytes([192, 168, 235, 142]);
        let test_client_id = 1001u32;

        clients.insert(test_ip, test_client_id, 0)?;

        let stored_id = clients.get(&test_ip, 0)?;

        if stored_id != test_client_id {
            anyhow::bail!("Client map read-back mismatch");
        }

        println!(
            "CLIENT_IDENTIFIERS map verified: 192.168.235.142 -> {}",
            stored_id
        );
    }

    // Day 20: measure userspace-to-kernel BLOCKLIST map update latency.
    {
        let mut blocklist = HashMap::<_, u32, u32>::try_from(
            ebpf.map_mut("BLOCKLIST")
                .context("BLOCKLIST map not found")?,
        )?;

        // TEST-NET address reserved for documentation and examples.
        let test_ip = u32::from_ne_bytes([192, 0, 2, 20]);
        let block_value = 1u32;

        let start = std::time::Instant::now();
        blocklist.insert(test_ip, block_value, 0)?;
        let update_elapsed = start.elapsed();

        let stored_value = blocklist.get(&test_ip, 0)?;
        if stored_value != block_value {
            anyhow::bail!("BLOCKLIST map read-back mismatch");
        }

        println!(
            "DAY20 blocklist_update_latency_us={:.3} target_us=1000 result={}",
            update_elapsed.as_secs_f64() * 1_000_000.0,
            if update_elapsed.as_micros() < 1000 { "UNDER_1MS" } else { "AT_OR_OVER_1MS" }
        );
        println!("DAY20 BLOCKLIST read-back verified for 192.0.2.20");
    }

    let event_map = ebpf
        .take_map("EVENTS")
        .context("EVENTS ring-buffer map not found")?;

    let ring_buf = RingBuf::try_from(event_map)?;
    let mut ring_buf =
        tokio::io::unix::AsyncFd::with_interest(ring_buf, tokio::io::Interest::READABLE)?;

    let drops_map = ebpf
        .map_mut("EVENT_DROPS")
        .context("EVENT_DROPS per-CPU map not found")?;
    let drops_map = PerCpuArray::<_, u64>::try_from(drops_map)?;

    let ctrl_c = signal::ctrl_c();
    tokio::pin!(ctrl_c);

    println!("API-Sentinel listening on {INTERFACE}");
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

                    let event = unsafe {
                        std::ptr::read_unaligned(
                            item.as_ptr().cast::<NetworkEvent>()
                        )
                    };

                    print_event(&event);
                }

                guard.clear_ready();

                match read_total_drops(&drops_map) {
                    Ok(total) => println!("METRIC ring_buffer_dropped_events={total}"),
                    Err(error) => warn!("Could not read EVENT_DROPS counter: {error}"),
                }
            }
        }
    }

    println!("API-Sentinel exiting");
    Ok(())
}
