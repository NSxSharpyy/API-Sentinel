#![no_std]
#![no_main]

use aya_ebpf::{
    helpers::bpf_get_current_pid_tgid,
    macros::{kprobe, map, tracepoint},
    maps::HashMap,
    programs::{ProbeContext, TracePointContext},
};
use aya_log_ebpf::info;

// Maps socket address to the TGID that entered tcp_v4_connect.
#[map]
static SOCKET_TGID: HashMap<u64, u32> = HashMap::with_max_entries(10240, 0);

#[tracepoint]
pub fn api_sentinel_ebpf(ctx: TracePointContext) -> u32 {
    match try_api_sentinel_ebpf(ctx) {
        Ok(ret) => ret,
        Err(ret) => ret,
    }
}

fn try_api_sentinel_ebpf(ctx: TracePointContext) -> Result<u32, u32> {
    // Read socket pointer from inet_sock_set_state.
    let socket_addr = unsafe { ctx.read_at::<u64>(8) }.map_err(|_| 1u32)?;

    let oldstate = unsafe { ctx.read_at::<i32>(16) }.map_err(|_| 1u32)?;

    let newstate = unsafe { ctx.read_at::<i32>(20) }.map_err(|_| 1u32)?;

    let sport = unsafe { ctx.read_at::<u16>(24) }.map_err(|_| 1u32)?;

    let dport = unsafe { ctx.read_at::<u16>(26) }.map_err(|_| 1u32)?;

    // Find the process recorded for this socket.
    let owner_tgid = match unsafe { SOCKET_TGID.get(&socket_addr) } {
        Some(tgid) => *tgid,
        None => 0,
    };

    // Log numeric TCP states to keep the eBPF program smaller.
    info!(
        &ctx,
        "Socket owner TGID: {}, TCP states: {} -> {}, ports {} -> {}",
        owner_tgid,
        oldstate,
        newstate,
        sport,
        dport
    );

    // Remove the entry when the socket reaches TCP_CLOSE (state 7).
    if newstate == 7 {
        let _ = SOCKET_TGID.remove(&socket_addr);
    }

    Ok(0)
}

// Capture the socket pointer and owner when IPv4 connect starts.
#[kprobe]
pub fn api_sentinel_tcp_v4_connect(ctx: ProbeContext) -> u32 {
    let socket: *const u8 = match ctx.arg(0) {
        Some(socket) => socket,
        None => return 1,
    };

    let socket_addr = socket as u64;

    let pid_tgid = bpf_get_current_pid_tgid();
    let tgid = (pid_tgid >> 32) as u32;

    match SOCKET_TGID.insert(&socket_addr, &tgid, 0) {
        Ok(()) => 0,
        Err(_) => 1,
    }
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}

#[unsafe(link_section = "license")]
#[unsafe(no_mangle)]
static LICENSE: [u8; 13] = *b"Dual MIT/GPL\0";
