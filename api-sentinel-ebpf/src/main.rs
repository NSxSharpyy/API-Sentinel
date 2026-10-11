use aya::programs::{KProbe, TracePoint};

#[rustfmt::skip]
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

    // Initialize eBPF logging.
    match aya_log::EbpfLogger::init(&mut ebpf) {
        Err(e) => warn!("failed to initialize eBPF logger: {e}"),
        Ok(logger) => {
            let mut logger =
                tokio::io::unix::AsyncFd::with_interest(logger, tokio::io::Interest::READABLE)?;

            tokio::task::spawn(async move {
                loop {
                    let mut guard = logger.readable_mut().await.unwrap();
                    guard.get_inner_mut().flush();
                    guard.clear_ready();
                }
            });
        }
    }

    // Attach the TCP lifecycle tracepoint.
    {
        let program: &mut TracePoint = ebpf.program_mut("api_sentinel_ebpf").unwrap().try_into()?;

        program.load()?;
        program.attach("sock", "inet_sock_set_state")?;
    }

    // Attach the IPv4 connect KProbe.
    {
        let connect_program: &mut KProbe = ebpf
            .program_mut("api_sentinel_tcp_v4_connect")
            .unwrap()
            .try_into()?;

        connect_program.load()?;
        connect_program.attach("tcp_v4_connect", 0)?;
    }

    let ctrl_c = signal::ctrl_c();

    println!("Waiting for Ctrl-C...");
    ctrl_c.await?;
    println!("Exiting...");

    Ok(())
}
