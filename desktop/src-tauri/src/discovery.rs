//! ONVIF camera discovery (WS-Discovery): a multicast Probe to 239.255.255.250:3702 from every local
//! IPv4 interface, answers collected for a short window. Every interface is probed on purpose: the
//! lab PC has two network cards and its default route does not face the cameras.
//!
//! Only ONVIF devices answer; the platform, rangefinder and relay are not found this way.

use crate::onvif::first_text;
use serde::Serialize;
use socket2::{Domain, Protocol, SockAddr, Socket, Type};
use std::{
    collections::BTreeMap,
    net::{Ipv4Addr, SocketAddr, SocketAddrV4, UdpSocket},
    thread,
    time::{Duration, Instant},
};

const GROUP: SocketAddrV4 = SocketAddrV4::new(Ipv4Addr::new(239, 255, 255, 250), 3702);
/// Cameras answer within about a second; slow ones take longer.
const WINDOW: Duration = Duration::from_millis(2500);
/// Some cameras answer only one of the two device types.
const TYPES: [&str; 2] = ["dn:NetworkVideoTransmitter", "tds:Device"];

#[derive(Serialize, Clone, Debug, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct FoundCamera {
    pub ip: String,
    /// ONVIF (HTTP) port from the camera's service address.
    pub port: u16,
    pub name: String,
    pub hardware: String,
    /// Not inside any subnet of this PC: found, but it cannot be connected to until readdressed.
    pub other_subnet: bool,
}

fn probe(types: &str) -> String {
    let id: [u8; 16] = rand::random();
    let hex: String = id.iter().map(|byte| format!("{byte:02x}")).collect();
    let uuid = format!("{}-{}-{}-{}-{}", &hex[..8], &hex[8..12], &hex[12..16], &hex[16..20], &hex[20..]);
    format!(
        concat!(
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
            "<s:Envelope xmlns:s=\"http://www.w3.org/2003/05/soap-envelope\" xmlns:a=\"http://schemas.xmlsoap.org/ws/2004/08/addressing\" ",
            "xmlns:d=\"http://schemas.xmlsoap.org/ws/2005/04/discovery\" xmlns:dn=\"http://www.onvif.org/ver10/network/wsdl\" ",
            "xmlns:tds=\"http://www.onvif.org/ver10/device/wsdl\"><s:Header>",
            "<a:Action s:mustUnderstand=\"1\">http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</a:Action>",
            "<a:MessageID>uuid:{}</a:MessageID>",
            "<a:ReplyTo><a:Address>http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</a:Address></a:ReplyTo>",
            "<a:To s:mustUnderstand=\"1\">urn:schemas-xmlsoap-org:ws:2005:04:discovery</a:To>",
            "</s:Header><s:Body><d:Probe><d:Types>{}</d:Types></d:Probe></s:Body></s:Envelope>"
        ),
        uuid, types
    )
}

fn percent_decode(text: &str) -> String {
    let bytes = text.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut index = 0;
    while index < bytes.len() {
        let hex = bytes.get(index + 1..index + 3).and_then(|pair| std::str::from_utf8(pair).ok());
        match (bytes[index], hex.and_then(|pair| u8::from_str_radix(pair, 16).ok())) {
            (b'%', Some(byte)) => {
                out.push(byte);
                index += 3;
            }
            (byte, _) => {
                out.push(byte);
                index += 1;
            }
        }
    }
    String::from_utf8_lossy(&out).into_owned()
}

/// Value of an `onvif://www.onvif.org/<key>/<value>` scope.
fn scope(scopes: &str, key: &str) -> String {
    let prefix = format!("onvif://www.onvif.org/{key}/");
    scopes
        .split_whitespace()
        .find_map(|item| item.strip_prefix(&prefix))
        .map(|value| percent_decode(value).trim().to_string())
        .unwrap_or_default()
}

/// ONVIF port from the service addresses: the one naming the answering host, else the first IPv4 one.
fn service_port(xaddrs: &str, host: Ipv4Addr) -> u16 {
    let urls: Vec<url::Url> = xaddrs.split_whitespace().filter_map(|item| url::Url::parse(item).ok()).collect();
    let is_v4 = |url: &url::Url| matches!(url.host(), Some(url::Host::Ipv4(_)));
    urls.iter()
        .find(|url| url.host() == Some(url::Host::Ipv4(host)))
        .or_else(|| urls.iter().find(|url| is_v4(url)))
        .and_then(|url| url.port_or_known_default())
        .unwrap_or(80)
}

/// A ProbeMatch answer from `from`, if it is one.
fn parse_match(xml: &str, from: Ipv4Addr, subnets: &[(Ipv4Addr, Ipv4Addr)]) -> Option<FoundCamera> {
    if !xml.contains("ProbeMatch") {
        return None;
    }
    let scopes = first_text(xml, "Scopes").unwrap_or_default();
    let xaddrs = first_text(xml, "XAddrs").unwrap_or_default();
    let within = |(ip, mask): &(Ipv4Addr, Ipv4Addr)| u32::from(*ip) & u32::from(*mask) == u32::from(from) & u32::from(*mask);
    Some(FoundCamera {
        ip: from.to_string(),
        port: service_port(&xaddrs, from),
        name: scope(&scopes, "name"),
        hardware: scope(&scopes, "hardware"),
        other_subnet: !subnets.iter().any(within),
    })
}

/// Probes through one interface and returns every answer as (source, message).
fn probe_from(local: Ipv4Addr) -> std::io::Result<Vec<(Ipv4Addr, String)>> {
    let socket = Socket::new(Domain::IPV4, Type::DGRAM, Some(Protocol::UDP))?;
    socket.bind(&SockAddr::from(SocketAddrV4::new(local, 0)))?;
    socket.set_multicast_if_v4(&local)?;
    let socket: UdpSocket = socket.into();
    for types in TYPES {
        socket.send_to(probe(types).as_bytes(), GROUP)?;
    }
    let deadline = Instant::now() + WINDOW;
    let mut answers = Vec::new();
    let mut buffer = vec![0_u8; 65_536];
    while let Some(left) = deadline.checked_duration_since(Instant::now()).filter(|left| !left.is_zero()) {
        socket.set_read_timeout(Some(left))?;
        match socket.recv_from(&mut buffer) {
            Ok((count, SocketAddr::V4(from))) => answers.push((*from.ip(), String::from_utf8_lossy(&buffer[..count]).into_owned())),
            Ok(_) => {}
            Err(error) if matches!(error.kind(), std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut) => break,
            // Windows reports ICMP «port unreachable» from an earlier send as a receive error.
            Err(error) if error.kind() == std::io::ErrorKind::ConnectionReset => continue,
            Err(error) => return Err(error),
        }
    }
    Ok(answers)
}

fn discover() -> Result<Vec<FoundCamera>, String> {
    let interfaces: Vec<(Ipv4Addr, Ipv4Addr)> = if_addrs::get_if_addrs()
        .map_err(|error| format!("сетевые интерфейсы: {error}"))?
        .into_iter()
        .filter_map(|interface| match interface.addr {
            if_addrs::IfAddr::V4(v4) if !v4.ip.is_loopback() && !v4.ip.is_link_local() => Some((v4.ip, v4.netmask)),
            _ => None,
        })
        .collect();
    if interfaces.is_empty() {
        return Err("нет сетевых интерфейсов IPv4".into());
    }
    let probes: Vec<_> = interfaces.iter().map(|&(local, _)| thread::spawn(move || (local, probe_from(local)))).collect();
    let mut found = BTreeMap::new();
    for probe in probes {
        let Ok((local, result)) = probe.join() else { continue };
        match result {
            Ok(answers) => {
                for (from, xml) in answers {
                    if let Some(camera) = parse_match(&xml, from, &interfaces) {
                        found.entry(u32::from(from)).or_insert(camera);
                    }
                }
            }
            // One unusable interface (disconnected, virtual) must not hide the cameras on the others.
            Err(error) => eprintln!("[discovery] {local}: {error}"),
        }
    }
    Ok(found.into_values().collect())
}

/// Finds ONVIF cameras on every local network; sorted by address.
#[tauri::command]
pub async fn discover_cameras() -> Result<Vec<FoundCamera>, String> {
    let found = crate::run_blocking(discover).await?;
    eprintln!(
        "[discovery] найдено {}: {}",
        found.len(),
        found.iter().map(|camera| format!("{} ({})", camera.ip, camera.hardware)).collect::<Vec<_>>().join(", ")
    );
    Ok(found)
}

#[cfg(test)]
mod tests {
    use super::*;

    const MATCH: &str = r#"<?xml version="1.0" encoding="UTF-8"?><SOAP-ENV:Envelope><SOAP-ENV:Body><d:ProbeMatches><d:ProbeMatch>
        <wsa:EndpointReference><wsa:Address>urn:uuid:1</wsa:Address></wsa:EndpointReference>
        <d:Types>dn:NetworkVideoTransmitter tds:Device</d:Types>
        <d:Scopes>onvif://www.onvif.org/type/video_encoder onvif://www.onvif.org/name/Thermal%20Cam onvif://www.onvif.org/hardware/IP_Camera</d:Scopes>
        <d:XAddrs>http://[fe80::1]/onvif/device_service http://192.168.1.108:8080/onvif/device_service</d:XAddrs>
        </d:ProbeMatch></d:ProbeMatches></SOAP-ENV:Body></SOAP-ENV:Envelope>"#;

    #[test]
    fn probe_match_gives_address_port_and_names() {
        let lab = [(Ipv4Addr::new(192, 168, 1, 100), Ipv4Addr::new(255, 255, 255, 0))];
        let camera = parse_match(MATCH, Ipv4Addr::new(192, 168, 1, 108), &lab).unwrap();
        assert_eq!(
            camera,
            FoundCamera { ip: "192.168.1.108".into(), port: 8080, name: "Thermal Cam".into(), hardware: "IP_Camera".into(), other_subnet: false }
        );
        // A camera still on its factory address in another subnet is reported, marked unreachable.
        assert!(parse_match(MATCH, Ipv4Addr::new(192, 168, 0, 99), &lab).unwrap().other_subnet);
        assert_eq!(parse_match("<Hello/>", Ipv4Addr::new(192, 168, 1, 108), &lab), None);
    }

    #[test]
    fn service_port_defaults_to_http() {
        let host = Ipv4Addr::new(192, 168, 1, 68);
        assert_eq!(service_port("http://192.168.1.68/onvif/device_service", host), 80);
        assert_eq!(service_port("http://10.0.0.5:8000/onvif/device_service", host), 8000);
        assert_eq!(service_port("", host), 80);
    }

    /// Live network: `cargo test --lib real_network -- --ignored --nocapture`.
    #[test]
    #[ignore]
    fn real_network() {
        let started = Instant::now();
        let found = discover().unwrap();
        println!("{:?}: {found:#?}", started.elapsed());
    }

    #[test]
    fn probe_is_well_formed() {
        let message = probe("dn:NetworkVideoTransmitter");
        assert!(message.contains("<d:Types>dn:NetworkVideoTransmitter</d:Types>"));
        assert!(message.contains("<a:MessageID>uuid:"));
        assert_ne!(probe("tds:Device"), probe("tds:Device"));
    }
}
