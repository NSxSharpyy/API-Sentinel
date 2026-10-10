#![no_std]
#![no_main]

use aya_ebpf::{macros::tracepoint, programs::TracePointContext};
use aya_log_ebpf::info;

#[tracepoint]
pub fn api_sentinel_ebpf(ctx: TracePointContext) -> u32 {
    match try_api_sentinel_ebpf(ctx) {
        Ok(ret) => ret,
        Err(ret) => ret,
    }
}

fn try_api_sentinel_ebpf(ctx: TracePointContext) -> Result<u32, u32> {
    let oldstate = unsafe { ctx.read_at::<i32>(16) }.map_err(|_| 1u32)?;
    let newstate = unsafe { ctx.read_at::<i32>(20) }.map_err(|_| 1u32)?;
    let sport = unsafe { ctx.read_at::<u16>(24) }.map_err(|_| 1u32)?;
    let dport = unsafe { ctx.read_at::<u16>(26) }.map_err(|_| 1u32)?;

    let old_name = match oldstate {
        1 => "ESTABLISHED",
        2 => "SYN_SENT",
        3 => "SYN_RECV",
        4 => "FIN_WAIT1",
        5 => "FIN_WAIT2",
        6 => "TIME_WAIT",
        7 => "CLOSE",
        8 => "CLOSE_WAIT",
        9 => "LAST_ACK",
        10 => "LISTEN",
        11 => "CLOSING",
        _ => "UNKNOWN",
    };

    let new_name = match newstate {
        1 => "ESTABLISHED",
        2 => "SYN_SENT",
        3 => "SYN_RECV",
        4 => "FIN_WAIT1",
        5 => "FIN_WAIT2",
        6 => "TIME_WAIT",
        7 => "CLOSE",
        8 => "CLOSE_WAIT",
        9 => "LAST_ACK",
        10 => "LISTEN",
        11 => "CLOSING",
        _ => "UNKNOWN",
    };

    info!(
        &ctx,
        "TCP state change: {} -> {}, ports {} -> {}",
        old_name,
        new_name,
        sport,
        dport
    );

    Ok(0)
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}

#[unsafe(link_section = "license")]
#[unsafe(no_mangle)]
static LICENSE: [u8; 13] = *b"Dual MIT/GPL\0";
