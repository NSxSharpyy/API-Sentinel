#![no_std]
#![no_main]

use aya_ebpf::{
    bindings::TC_ACT_PIPE,
    cty::c_void,
    helpers::{bpf_get_current_pid_tgid, generated::bpf_skb_load_bytes},
    macros::{classifier, kprobe, map, tracepoint},
    maps::{HashMap, RingBuf},
    programs::{ProbeContext, TcContext, TracePointContext},
};

use api_sentinel_ebpf_common::{
    EVENT_TYPE_HTTP_REQUEST, EVENT_TYPE_TCP_STATE, HTTP_METHOD_DELETE, HTTP_METHOD_GET,
    HTTP_METHOD_HEAD, HTTP_METHOD_OPTIONS, HTTP_METHOD_PATCH, HTTP_METHOD_POST, HTTP_METHOD_PUT,
    HTTP_METHOD_UNKNOWN, NetworkEvent,
};

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
        event_type: EVENT_TYPE_TCP_STATE,
        http_method: HTTP_METHOD_UNKNOWN,
        uri_len: 0,
        reserved: [0; 3],
        uri_prefix: [0; 16],
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

// Day 9: passive HTTP request detection for untagged Ethernet IPv4/TCP.
const HTTP_ETH_LEN: usize = 14;
const HTTP_IP_LEN: usize = 20;
const HTTP_TCP_LEN: usize = 20;
const HTTP_READ_LEN: usize = 64;
const HTTP_URI_LEN: usize = 16;

#[inline(always)]
fn detect_http_method(p: &[u8; HTTP_READ_LEN]) -> (u8, usize) {
    if p[0] == b'G' && p[1] == b'E' && p[2] == b'T' && p[3] == b' ' {
        return (HTTP_METHOD_GET, 3);
    }
    if p[0] == b'P' && p[1] == b'O' && p[2] == b'S' && p[3] == b'T' && p[4] == b' ' {
        return (HTTP_METHOD_POST, 4);
    }
    if p[0] == b'P' && p[1] == b'U' && p[2] == b'T' && p[3] == b' ' {
        return (HTTP_METHOD_PUT, 3);
    }
    if p[0] == b'D'
        && p[1] == b'E'
        && p[2] == b'L'
        && p[3] == b'E'
        && p[4] == b'T'
        && p[5] == b'E'
        && p[6] == b' '
    {
        return (HTTP_METHOD_DELETE, 6);
    }
    if p[0] == b'P' && p[1] == b'A' && p[2] == b'T' && p[3] == b'C' && p[4] == b'H' && p[5] == b' '
    {
        return (HTTP_METHOD_PATCH, 5);
    }
    if p[0] == b'H' && p[1] == b'E' && p[2] == b'A' && p[3] == b'D' && p[4] == b' ' {
        return (HTTP_METHOD_HEAD, 4);
    }
    if p[0] == b'O'
        && p[1] == b'P'
        && p[2] == b'T'
        && p[3] == b'I'
        && p[4] == b'O'
        && p[5] == b'N'
        && p[6] == b'S'
        && p[7] == b' '
    {
        return (HTTP_METHOD_OPTIONS, 7);
    }
    (HTTP_METHOD_UNKNOWN, 0)
}

#[classifier]
pub fn api_sentinel_http_classifier(ctx: TcContext) -> i32 {
    let packet_len = ctx.len() as usize;

    if packet_len < HTTP_ETH_LEN + HTTP_IP_LEN {
        return TC_ACT_PIPE;
    }

    // Fixed-length Ethernet read.
    let mut eth = [0u8; HTTP_ETH_LEN];
    let ret = unsafe {
        bpf_skb_load_bytes(
            ctx.skb.skb as *const c_void,
            0,
            eth.as_mut_ptr().cast::<c_void>(),
            HTTP_ETH_LEN as u32,
        )
    };
    if ret < 0 || eth[12] != 0x08 || eth[13] != 0x00 {
        return TC_ACT_PIPE;
    }

    // Fixed-length minimum IPv4 read.
    let mut ip = [0u8; HTTP_IP_LEN];
    let ret = unsafe {
        bpf_skb_load_bytes(
            ctx.skb.skb as *const c_void,
            HTTP_ETH_LEN as u32,
            ip.as_mut_ptr().cast::<c_void>(),
            HTTP_IP_LEN as u32,
        )
    };
    if ret < 0 || ip[0] >> 4 != 4 || ip[9] != 6 {
        return TC_ACT_PIPE;
    }

    let ip_header_len = ((ip[0] & 0x0f) as usize) * 4;
    if ip_header_len < HTTP_IP_LEN || ip_header_len > 60 {
        return TC_ACT_PIPE;
    }

    let tcp_offset = HTTP_ETH_LEN + ip_header_len;
    if packet_len < tcp_offset + HTTP_TCP_LEN {
        return TC_ACT_PIPE;
    }

    // Fixed-length minimum TCP read.
    let mut tcp = [0u8; HTTP_TCP_LEN];
    let ret = unsafe {
        bpf_skb_load_bytes(
            ctx.skb.skb as *const c_void,
            tcp_offset as u32,
            tcp.as_mut_ptr().cast::<c_void>(),
            HTTP_TCP_LEN as u32,
        )
    };
    if ret < 0 {
        return TC_ACT_PIPE;
    }

    let tcp_header_len = ((tcp[12] >> 4) as usize) * 4;
    if tcp_header_len < HTTP_TCP_LEN || tcp_header_len > 60 {
        return TC_ACT_PIPE;
    }

    let payload_offset = tcp_offset + tcp_header_len;

    // This initial version inspects payloads only when 64 bytes are present.
    if packet_len < payload_offset + HTTP_READ_LEN {
        return TC_ACT_PIPE;
    }

    let mut payload = [0u8; HTTP_READ_LEN];
    let ret = unsafe {
        bpf_skb_load_bytes(
            ctx.skb.skb as *const c_void,
            payload_offset as u32,
            payload.as_mut_ptr().cast::<c_void>(),
            HTTP_READ_LEN as u32,
        )
    };
    if ret < 0 {
        return TC_ACT_PIPE;
    }

    let (method, method_len) = detect_http_method(&payload);
    if method == HTTP_METHOD_UNKNOWN {
        return TC_ACT_PIPE;
    }

    let uri_start = method_len + 1;
    if uri_start >= HTTP_READ_LEN || payload[uri_start] != b'/' {
        return TC_ACT_PIPE;
    }

    let mut uri = [0u8; HTTP_URI_LEN];
    let mut uri_len = 0u8;

    for i in 0..HTTP_URI_LEN {
        let byte = payload[uri_start + i];
        if byte == b' ' || byte == b'\r' || byte == b'\n' {
            break;
        }
        uri[i] = byte;
        uri_len += 1;
    }

    let src = [ip[12], ip[13], ip[14], ip[15]];
    let dst = [ip[16], ip[17], ip[18], ip[19]];

    let event = NetworkEvent {
        tgid: 0,
        family: 2,
        protocol: 6,
        old_state: 0,
        new_state: 0,
        source_port: u16::from_be_bytes([tcp[0], tcp[1]]),
        destination_port: u16::from_be_bytes([tcp[2], tcp[3]]),
        source_ipv4: src,
        destination_ipv4: dst,
        attribution_known: 0,
        traffic_direction: classify_traffic_direction(src, dst),
        event_type: EVENT_TYPE_HTTP_REQUEST,
        http_method: method,
        uri_len,
        reserved: [0; 3],
        uri_prefix: uri,
    };

    let _ = EVENTS.output::<NetworkEvent>(&event, 0);

    // Passive inspection: let the packet continue.
    TC_ACT_PIPE
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}

#[unsafe(link_section = "license")]
#[unsafe(no_mangle)]
static LICENSE: [u8; 13] = *b"Dual MIT/GPL\0";
