#![no_std]

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
    pub reserved: [u8; 3],
}
