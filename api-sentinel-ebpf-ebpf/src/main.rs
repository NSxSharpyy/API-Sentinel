#![no_std]
#![no_main]

use aya_ebpf::{
    helpers::bpf_get_current_pid_tgid,
    macros::{kprobe, map, tracepoint},
    maps::HashMap,
    programs::{ProbeContext, TracePointContext},
};

use aya_log_ebpf::info;

// Map: socket address -> owning process TGID
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
    // Read socket address and TCP state fields.
    let socket_addr = unsafe { ctx.read_at::<u64>(8) }.map_err(|_| 1u32)?;

    let oldstate = unsafe { ctx.read_at::<i32>(16) }.map_err(|_| 1u32)?;
    let newstate = unsafe { ctx.read_at::<i32>(20) }.map_err(|_| 1u32)?;
    let sport = unsafe { ctx.read_at::<u16>(24) }.map_err(|_| 1u32)?;
    let dport = unsafe { ctx.read_at::<u16>(26) }.map_err(|_| 1u32)?;

    // Read address family and network protocol.
    let family = unsafe { ctx.read_at::<u16>(28) }.map_err(|_| 1u32)?;
    let protocol = unsafe { ctx.read_at::<u16>(30) }.map_err(|_| 1u32)?;

    // Process only IPv4 TCP events.
    // AF_INET = 2, IPPROTO_TCP = 6.
    if family != 2 || protocol != 6 {
        return Ok(0);
    }

    // IPv4 source address: bytes at offsets 32-35.
    let src0 = unsafe { ctx.read_at::<u8>(32) }.map_err(|_| 1u32)?;
    let src1 = unsafe { ctx.read_at::<u8>(33) }.map_err(|_| 1u32)?;
    let src2 = unsafe { ctx.read_at::<u8>(34) }.map_err(|_| 1u32)?;
    let src3 = unsafe { ctx.read_at::<u8>(35) }.map_err(|_| 1u32)?;

    // IPv4 destination address: bytes at offsets 36-39.
    let dst0 = unsafe { ctx.read_at::<u8>(36) }.map_err(|_| 1u32)?;
    let dst1 = unsafe { ctx.read_at::<u8>(37) }.map_err(|_| 1u32)?;
    let dst2 = unsafe { ctx.read_at::<u8>(38) }.map_err(|_| 1u32)?;
    let dst3 = unsafe { ctx.read_at::<u8>(39) }.map_err(|_| 1u32)?;

    // Look up the owning process for this socket.
    let owner_tgid = match unsafe { SOCKET_TGID.get(&socket_addr) } {
        Some(tgid) => *tgid,
        None => 0,
    };

    // Log TCP states, ports, address family and protocol.
    info!(
        &ctx,
        "TGID {}, family {}, protocol {}, TCP {} -> {}, ports {} -> {}",
        owner_tgid,
        family,
        protocol,
        oldstate,
        newstate,
        sport,
        dport
    );

    // Log IPv4 source and destination addresses.
    info!(
        &ctx,
        "IPv4 source {}.{}.{}.{} destination {}.{}.{}.{}",
        src0,
        src1,
        src2,
        src3,
        dst0,
        dst1,
        dst2,
        dst3
    );

    // TCP_CLOSE = state 7; remove the socket from the map.
    if newstate == 7 {
        let _ = SOCKET_TGID.remove(&socket_addr);
    }

    Ok(0)
}

// Record the TGID when an IPv4 connection begins.
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
