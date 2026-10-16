#![no_std]
#![no_main]

use aya_ebpf::{
    helpers::bpf_get_current_pid_tgid,
    macros::{kprobe, map, tracepoint},
    maps::{HashMap, RingBuf},
    programs::{ProbeContext, TracePointContext},
};

use api_sentinel_ebpf_common::NetworkEvent;

// Map: socket address -> owning process TGID.
#[map]
static SOCKET_TGID: HashMap<u64, u32> = HashMap::with_max_entries(10240, 0);

// Ring buffer: kernel -> userspace network events.
#[map]
static EVENTS: RingBuf = RingBuf::with_byte_size(1 << 24, 0);

// Traffic direction values:
// 0 = Unknown / Other
// 1 = East-West
// 2 = North-South

// Basic heuristic for RFC1918 private IPv4 addresses.
fn is_private_ipv4(ip: [u8; 4]) -> bool {
    ip[0] == 10 || (ip[0] == 172 && ip[1] >= 16 && ip[1] <= 31) || (ip[0] == 192 && ip[1] == 168)
}

fn classify_traffic_direction(source: [u8; 4], destination: [u8; 4]) -> u8 {
    let source_private = is_private_ipv4(source);
    let destination_private = is_private_ipv4(destination);

    if source_private && destination_private {
        1 // East-West
    } else if source_private || destination_private {
        2 // North-South
    } else {
        0 // Unknown / Other
    }
}

#[tracepoint]
pub fn api_sentinel_ebpf(ctx: TracePointContext) -> u32 {
    match try_api_sentinel_ebpf(ctx) {
        Ok(ret) => ret,
        Err(ret) => ret,
    }
}

fn try_api_sentinel_ebpf(ctx: TracePointContext) -> Result<u32, u32> {
    let socket_addr = unsafe { ctx.read_at::<u64>(8) }.map_err(|_| 1u32)?;
    let old_state = unsafe { ctx.read_at::<i32>(16) }.map_err(|_| 1u32)?;
    let new_state = unsafe { ctx.read_at::<i32>(20) }.map_err(|_| 1u32)?;
    let source_port = unsafe { ctx.read_at::<u16>(24) }.map_err(|_| 1u32)?;
    let destination_port = unsafe { ctx.read_at::<u16>(26) }.map_err(|_| 1u32)?;

    let family = unsafe { ctx.read_at::<u16>(28) }.map_err(|_| 1u32)?;
    let protocol = unsafe { ctx.read_at::<u16>(30) }.map_err(|_| 1u32)?;

    // AF_INET = 2, IPPROTO_TCP = 6.
    if family != 2 || protocol != 6 {
        return Ok(0);
    }

    let src0 = unsafe { ctx.read_at::<u8>(32) }.map_err(|_| 1u32)?;
    let src1 = unsafe { ctx.read_at::<u8>(33) }.map_err(|_| 1u32)?;
    let src2 = unsafe { ctx.read_at::<u8>(34) }.map_err(|_| 1u32)?;
    let src3 = unsafe { ctx.read_at::<u8>(35) }.map_err(|_| 1u32)?;

    let dst0 = unsafe { ctx.read_at::<u8>(36) }.map_err(|_| 1u32)?;
    let dst1 = unsafe { ctx.read_at::<u8>(37) }.map_err(|_| 1u32)?;
    let dst2 = unsafe { ctx.read_at::<u8>(38) }.map_err(|_| 1u32)?;
    let dst3 = unsafe { ctx.read_at::<u8>(39) }.map_err(|_| 1u32)?;

    let source_ipv4 = [src0, src1, src2, src3];
    let destination_ipv4 = [dst0, dst1, dst2, dst3];

    let (tgid, attribution_known) = match unsafe { SOCKET_TGID.get(&socket_addr) } {
        Some(owner_tgid) => (*owner_tgid, 1u8),
        None => (0u32, 0u8),
    };

    let traffic_direction = classify_traffic_direction(source_ipv4, destination_ipv4);

    let event = NetworkEvent {
        tgid,
        family,
        protocol,
        old_state,
        new_state,
        source_port,
        destination_port,
        source_ipv4,
        destination_ipv4,
        attribution_known,
        traffic_direction,
        reserved: [0; 2],
    };

    // Send the structured event to userspace.
    // The event may be dropped if the ring buffer is full.
    let _ = EVENTS.output::<NetworkEvent>(&event, 0);

    // TCP_CLOSE = state 7.
    if new_state == 7 {
        let _ = SOCKET_TGID.remove(&socket_addr);
    }

    Ok(0)
}

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
