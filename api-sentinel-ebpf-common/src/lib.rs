#![no_std]

pub const EVENT_TYPE_TCP_STATE: u8 = 1;
pub const EVENT_TYPE_HTTP_REQUEST: u8 = 2;

pub const HTTP_METHOD_UNKNOWN: u8 = 0;
pub const HTTP_METHOD_GET: u8 = 1;
pub const HTTP_METHOD_POST: u8 = 2;
pub const HTTP_METHOD_PUT: u8 = 3;
pub const HTTP_METHOD_DELETE: u8 = 4;
pub const HTTP_METHOD_PATCH: u8 = 5;
pub const HTTP_METHOD_HEAD: u8 = 6;
pub const HTTP_METHOD_OPTIONS: u8 = 7;

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct NetworkEvent {
    pub tgid: u32,
    pub family: u16,
    pub protocol: u16,
    pub old_state: i32,
    pub new_state: i32,
    pub source_port: u16,
    pub destination_port: u16,
    pub source_ipv4: [u8; 4],
    pub destination_ipv4: [u8; 4],
    pub attribution_known: u8,
    pub traffic_direction: u8,
    pub event_type: u8,
    pub http_method: u8,
    pub uri_len: u8,
    pub reserved: [u8; 3],
    pub uri_prefix: [u8; 16],
}
