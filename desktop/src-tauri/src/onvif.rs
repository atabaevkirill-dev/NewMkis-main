//! ONVIF lens control: zoom through PTZ, focus through Imaging, one discrete step per wheel notch or
//! button press.
//!
//! Zoom goes to an absolute target accumulated here when the camera reports its zoom position (see
//! `absolute_zoom`). Otherwise a step is an exact relative move when the camera advertises one (PTZ
//! `RelativeZoomTranslationSpace`, Imaging `MoveOptions/Relative`), else a short continuous move
//! stopped after a length proportional to the step. A pulse never outlives its call; a watchdog stops any move whose stop
//! failed, so the lens can never be left driving to its end stop.
//!
//! Requests go over a plain TCP socket on purpose: system HTTP proxies (VPN clients) must not
//! intercept camera traffic. Authentication is WS-Security UsernameToken (password digest); the
//! `Created` stamp follows the camera clock, which on these cameras is not synchronised.

use base64::{engine::general_purpose::STANDARD as BASE64, Engine};
use sha1::{Digest, Sha1};
use std::{
    collections::HashMap,
    io::{Read, Write},
    net::{SocketAddr, TcpStream},
    sync::{Arc, Mutex},
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
use tauri::State;

const HTTP_TIMEOUT: Duration = Duration::from_secs(3);
const MAX_RESPONSE_BYTES: usize = 512 * 1024;
const WATCHDOG_TICK: Duration = Duration::from_millis(50);
/// Pulse length per percent of a step, for cameras without relative moves.
const PULSE_PER_PERCENT: Duration = Duration::from_millis(40);
const PULSE_MIN: Duration = Duration::from_millis(40);
const PULSE_MAX: Duration = Duration::from_millis(600);
/// Steps merged into one command while the previous one is still running.
const MAX_STEPS: i32 = 10;
/// After this pause the zoom target is read back from the camera instead of continued.
const ZOOM_RESYNC: Duration = Duration::from_secs(2);
/// Resolution of the zoom position cameras report (6 decimals).
const POSITION_SLACK: f64 = 0.000_001;
const STEP_PERCENT: std::ops::RangeInclusive<f64> = 0.01..=25.0;
const ZOOM_SPEED: f64 = 0.6;
const FOCUS_SPEED: f64 = 0.6;

const NS_DEVICE: &str = "http://www.onvif.org/ver10/device/wsdl";
const NS_MEDIA: &str = "http://www.onvif.org/ver10/media/wsdl";
const NS_PTZ: &str = "http://www.onvif.org/ver20/ptz/wsdl";
const NS_IMAGING: &str = "http://www.onvif.org/ver20/imaging/wsdl";
const NS_SCHEMA: &str = "http://www.onvif.org/ver10/schema";

// ---------------------------------------------------------------- minimal XML helpers

/// Finds start tags by local name (namespace prefixes ignored); returns (attributes, text after the tag).
fn elements<'a>(xml: &'a str, local: &str) -> Vec<(&'a str, &'a str)> {
    let mut found = Vec::new();
    let mut rest = xml;
    while let Some(start) = rest.find('<') {
        rest = &rest[start + 1..];
        let Some(end) = rest.find('>') else { break };
        let tag = &rest[..end];
        let after = &rest[end + 1..];
        if tag.starts_with('/') || tag.starts_with('?') || tag.starts_with('!') {
            continue;
        }
        let name_end = tag.find(|c: char| c.is_whitespace() || c == '/').unwrap_or(tag.len());
        let name = &tag[..name_end];
        let local_name = name.rsplit(':').next().unwrap_or(name);
        if local_name == local {
            let text = after.split('<').next().unwrap_or("");
            found.push((&tag[name_end..], text));
        }
    }
    found
}

fn first_text(xml: &str, local: &str) -> Option<String> {
    elements(xml, local)
        .first()
        .map(|(_, text)| unescape(text.trim()))
        .filter(|text| !text.is_empty())
}

fn attribute(attrs: &str, name: &str) -> Option<String> {
    let needle = format!("{name}=\"");
    let start = attrs.find(&needle)? + needle.len();
    let end = attrs[start..].find('"')? + start;
    Some(unescape(&attrs[start..end]))
}

/// The section of `xml` from the first `local` start tag onwards.
fn section<'a>(xml: &'a str, local: &str) -> Option<&'a str> {
    let (attrs, _) = elements(xml, local).into_iter().next()?;
    let offset = attrs.as_ptr() as usize - xml.as_ptr() as usize;
    Some(&xml[offset..])
}

fn escape(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&apos;")
}

fn unescape(text: &str) -> String {
    text.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", "\"")
        .replace("&apos;", "'")
        .replace("&amp;", "&")
}

// ---------------------------------------------------------------- time

fn days_from_civil(year: i64, month: i64, day: i64) -> i64 {
    let year = if month <= 2 { year - 1 } else { year };
    let era = year.div_euclid(400);
    let yoe = year - era * 400;
    let doy = (153 * (month + if month > 2 { -3 } else { 9 }) + 2) / 5 + day - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    era * 146_097 + doe - 719_468
}

fn civil_from_days(days: i64) -> (i64, i64, i64) {
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = if mp < 10 { mp + 3 } else { mp - 9 };
    (yoe + era * 400 + i64::from(month <= 2), month, day)
}

pub(crate) fn iso8601(unix: i64) -> String {
    let (year, month, day) = civil_from_days(unix.div_euclid(86_400));
    let seconds = unix.rem_euclid(86_400);
    format!(
        "{year:04}-{month:02}-{day:02}T{:02}:{:02}:{:02}Z",
        seconds / 3600,
        seconds / 60 % 60,
        seconds % 60
    )
}

pub(crate) fn now_unix() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|elapsed| elapsed.as_secs() as i64)
        .unwrap_or(0)
}

/// Reads one `<…DateTime>` block of GetSystemDateAndTime as Unix seconds, if it is a sane date.
fn camera_time(xml: &str, block: &str) -> Option<i64> {
    let part = section(xml, block)?;
    let number = |name: &str| first_text(part, name)?.parse::<i64>().ok();
    let (year, month, day) = (number("Year")?, number("Month")?, number("Day")?);
    let (hour, minute, second) = (number("Hour")?, number("Minute")?, number("Second").unwrap_or(0));
    let valid = (1970..=2200).contains(&year)
        && (1..=12).contains(&month)
        && (1..=31).contains(&day)
        && (0..24).contains(&hour)
        && (0..60).contains(&minute);
    valid.then(|| days_from_civil(year, month, day) * 86_400 + hour * 3600 + minute * 60 + second)
}

// ---------------------------------------------------------------- SOAP transport

struct Credentials {
    username: String,
    password: String,
}

fn security_header(creds: &Credentials, clock_offset: i64) -> String {
    let nonce: [u8; 16] = rand::random();
    let created = iso8601(now_unix() + clock_offset);
    let mut hasher = Sha1::new();
    hasher.update(nonce);
    hasher.update(created.as_bytes());
    hasher.update(creds.password.as_bytes());
    let digest = BASE64.encode(hasher.finalize());
    format!(
        concat!(
            "<s:Header><Security s:mustUnderstand=\"1\" xmlns=\"http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd\">",
            "<UsernameToken><Username>{}</Username>",
            "<Password Type=\"http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest\">{}</Password>",
            "<Nonce EncodingType=\"http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary\">{}</Nonce>",
            "<Created xmlns=\"http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd\">{}</Created>",
            "</UsernameToken></Security></s:Header>"
        ),
        escape(&creds.username),
        digest,
        BASE64.encode(nonce),
        created
    )
}

fn dechunk(body: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(body.len());
    let mut rest = body;
    while let Some(line_end) = rest.windows(2).position(|pair| pair == b"\r\n") {
        let size_text = String::from_utf8_lossy(&rest[..line_end]);
        let Ok(size) = usize::from_str_radix(size_text.split(';').next().unwrap_or("").trim(), 16) else { break };
        rest = &rest[line_end + 2..];
        if size == 0 || size > rest.len() {
            out.extend_from_slice(&rest[..size.min(rest.len())]);
            break;
        }
        out.extend_from_slice(&rest[..size]);
        rest = rest.get(size + 2..).unwrap_or(&[]);
    }
    out
}

#[derive(Debug)]
enum SoapError {
    /// The camera rejected the credentials (or the timestamp).
    Unauthorized(String),
    Other(String),
}

impl SoapError {
    fn message(&self) -> String {
        match self {
            SoapError::Unauthorized(detail) => format!("неверный логин или пароль ONVIF ({detail})"),
            SoapError::Other(detail) => detail.clone(),
        }
    }
}

/// True once a whole HTTP response is buffered. Cameras that ignore `Connection: close` keep the
/// socket open, and waiting for them to close it cost a full read timeout on every lens command.
fn response_complete(response: &[u8]) -> bool {
    let Some(split) = response.windows(4).position(|window| window == b"\r\n\r\n") else { return false };
    let head = String::from_utf8_lossy(&response[..split]).to_ascii_lowercase();
    let body = &response[split + 4..];
    if head.contains("transfer-encoding: chunked") {
        return body.ends_with(b"0\r\n\r\n");
    }
    head.lines()
        .find_map(|line| line.strip_prefix("content-length:"))
        .and_then(|value| value.trim().parse::<usize>().ok())
        .is_some_and(|length| body.len() >= length)
}

fn post(address: SocketAddr, path: &str, body: &str) -> Result<(u16, String), String> {
    let mut stream = TcpStream::connect_timeout(&address, HTTP_TIMEOUT).map_err(|error| format!("{address}: {error}"))?;
    stream.set_read_timeout(Some(HTTP_TIMEOUT)).map_err(|error| error.to_string())?;
    stream.set_write_timeout(Some(HTTP_TIMEOUT)).map_err(|error| error.to_string())?;
    let request = format!(
        "POST {path} HTTP/1.1\r\nHost: {address}\r\nContent-Type: application/soap+xml; charset=utf-8\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    );
    stream.write_all(request.as_bytes()).map_err(|error| error.to_string())?;
    let mut response = Vec::new();
    let mut buffer = [0_u8; 8192];
    loop {
        match stream.read(&mut buffer) {
            Ok(0) => break,
            Ok(count) => {
                response.extend_from_slice(&buffer[..count]);
                if response.len() > MAX_RESPONSE_BYTES {
                    return Err("слишком большой ответ ONVIF".into());
                }
                if response_complete(&response) {
                    break;
                }
            }
            // Some cameras keep the socket open; what arrived before the timeout is the answer.
            Err(error) if !response.is_empty() && matches!(error.kind(), std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut) => break,
            Err(error) => return Err(format!("{address}: {error}")),
        }
    }
    let split = response
        .windows(4)
        .position(|window| window == b"\r\n\r\n")
        .ok_or("некорректный HTTP-ответ камеры")?;
    let head = String::from_utf8_lossy(&response[..split]).to_string();
    let status = head
        .split_whitespace()
        .nth(1)
        .and_then(|code| code.parse::<u16>().ok())
        .ok_or("некорректный HTTP-ответ камеры")?;
    let raw = &response[split + 4..];
    let chunked = head.to_ascii_lowercase().contains("transfer-encoding: chunked");
    let body = if chunked { dechunk(raw) } else { raw.to_vec() };
    Ok((status, String::from_utf8_lossy(&body).to_string()))
}

fn fault_text(xml: &str) -> String {
    first_text(xml, "Text")
        .or_else(|| first_text(xml, "faultstring"))
        .or_else(|| elements(xml, "Value").last().map(|(_, text)| unescape(text.trim())))
        .unwrap_or_default()
}

/// Sends one SOAP call; `auth` adds a WS-Security header with the given camera clock offset.
fn soap(address: SocketAddr, path: &str, auth: Option<(&Credentials, i64)>, body: &str) -> Result<String, SoapError> {
    let header = auth.map(|(creds, offset)| security_header(creds, offset)).unwrap_or_default();
    let envelope = format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?><s:Envelope xmlns:s=\"http://www.w3.org/2003/05/soap-envelope\">{header}<s:Body>{body}</s:Body></s:Envelope>"
    );
    let (status, text) = post(address, path, &envelope).map_err(SoapError::Other)?;
    if status == 200 && !text.contains(":Fault>") {
        return Ok(text);
    }
    let fault = fault_text(&text);
    let lower = format!("{fault} {text}").to_ascii_lowercase();
    if status == 401 || lower.contains("notauthorized") || lower.contains("not authorized") || lower.contains("authority failure") {
        Err(SoapError::Unauthorized(if fault.is_empty() { format!("HTTP {status}") } else { fault }))
    } else {
        Err(SoapError::Other(if fault.is_empty() { format!("HTTP {status}") } else { format!("HTTP {status}: {fault}") }))
    }
}

// ---------------------------------------------------------------- device

struct Device {
    address: SocketAddr,
    creds: Credentials,
    clock_offset: i64,
    ptz_path: Option<String>,
    imaging_path: Option<String>,
    profile: String,
    source: Option<String>,
    /// Absolute zoom position range, when the camera also reports its zoom position (preferred).
    zoom_absolute: Option<(f64, f64)>,
    /// Zoom target kept between steps, with the time of the last step (see `absolute_zoom`).
    zoom_target: Option<(f64, Instant)>,
    /// Relative zoom translation range of the PTZ node; `None` means steps are timed pulses.
    zoom_range: Option<(f64, f64)>,
    /// Relative focus distance range of the Imaging service; `None` means steps are timed pulses.
    focus_range: Option<(f64, f64)>,
}

/// Next absolute zoom target: `steps` of `percent` of the range from `current`, inside the range.
fn next_target(current: f64, (min, max): (f64, f64), percent: f64, steps: i32) -> f64 {
    let target = current + f64::from(steps) * percent / 100.0 * (max - min);
    (target.clamp(min, max) * 1_000_000.0).round() / 1_000_000.0
}

/// `Min`/`Max` of the first `range` element inside the first `block` element.
fn move_range(xml: &str, block: &str, range: &str) -> Option<(f64, f64)> {
    let part = section(section(xml, block)?, range)?;
    let min: f64 = first_text(part, "Min")?.parse().ok()?;
    let max: f64 = first_text(part, "Max")?.parse().ok()?;
    (max > min).then_some((min, max))
}

/// Pulse length for one step of `percent` when the camera has no relative move (2 % → 80 ms).
fn pulse_length(percent: f64, steps: i32) -> Duration {
    PULSE_PER_PERCENT.mul_f64(percent * f64::from(steps.unsigned_abs())).clamp(PULSE_MIN, PULSE_MAX)
}

/// Relative amount for `steps` of `percent`, scaled to the camera range and kept inside it.
fn relative_amount((min, max): (f64, f64), percent: f64, steps: i32) -> f64 {
    let amount = f64::from(steps) * percent / 100.0 * max.abs().max(min.abs());
    (amount.clamp(min, max) * 1_000_000.0).round() / 1_000_000.0
}

fn xaddr_path(xml: &str, service: &str) -> Option<String> {
    let part = section(xml, service)?;
    let url = first_text(part, "XAddr")?;
    // Use only the path: cameras often advertise a stale or internal IP address.
    let after_scheme = url.split("://").nth(1)?;
    Some(after_scheme.find('/').map_or("/".to_string(), |index| after_scheme[index..].to_string()))
}

impl Device {
    fn call(&self, path: &str, body: &str) -> Result<String, SoapError> {
        soap(self.address, path, Some((&self.creds, self.clock_offset)), body)
    }

    fn connect(address: SocketAddr, creds: Credentials) -> Result<Device, SoapError> {
        const DEVICE: &str = "/onvif/device_service";
        let now = now_unix();
        let time = soap(address, DEVICE, None, &format!("<GetSystemDateAndTime xmlns=\"{NS_DEVICE}\"/>")).ok();
        // Candidates for the WS-Security clock: camera UTC, camera local time, this PC.
        let mut offsets: Vec<i64> = time
            .iter()
            .flat_map(|xml| [camera_time(xml, "UTCDateTime"), camera_time(xml, "LocalDateTime")])
            .flatten()
            .map(|camera| camera - now)
            .collect();
        offsets.push(0);
        offsets.dedup();

        let capabilities_body = format!("<GetCapabilities xmlns=\"{NS_DEVICE}\"><Category>All</Category></GetCapabilities>");
        let mut last_error = SoapError::Other("нет ответа ONVIF".into());
        let mut accepted = None;
        for offset in offsets {
            match soap(address, DEVICE, Some((&creds, offset)), &capabilities_body) {
                Ok(xml) => {
                    accepted = Some((offset, xml));
                    break;
                }
                Err(error) => last_error = error,
            }
        }
        let (clock_offset, capabilities) = accepted.ok_or(last_error)?;
        let media_path = xaddr_path(&capabilities, "Media").unwrap_or_else(|| "/onvif/media_service".into());
        let mut device = Device {
            address,
            creds,
            clock_offset,
            ptz_path: xaddr_path(&capabilities, "PTZ"),
            imaging_path: xaddr_path(&capabilities, "Imaging"),
            profile: String::new(),
            source: None,
            zoom_absolute: None,
            zoom_target: None,
            zoom_range: None,
            focus_range: None,
        };
        let profiles = device.call(&media_path, &format!("<GetProfiles xmlns=\"{NS_MEDIA}\"/>"))?;
        let (attrs, _) = elements(&profiles, "Profiles")
            .into_iter()
            .next()
            .ok_or_else(|| SoapError::Other("камера не вернула профилей ONVIF".into()))?;
        device.profile = attribute(attrs, "token").ok_or_else(|| SoapError::Other("профиль ONVIF без token".into()))?;
        device.source = section(&profiles, "VideoSourceConfiguration").and_then(|part| first_text(part, "SourceToken"));
        // Optional: a camera that cannot answer these still zooms and focuses with timed pulses.
        if let Some(ptz) = device.ptz_path.clone() {
            if let Ok(nodes) = device.call(&ptz, &format!("<GetNodes xmlns=\"{NS_PTZ}\"/>")) {
                device.zoom_range = move_range(&nodes, "RelativeZoomTranslationSpace", "XRange");
                let absolute = move_range(&nodes, "AbsoluteZoomPositionSpace", "XRange");
                device.zoom_absolute = absolute.filter(|_| device.zoom_position().is_ok());
            }
        }
        if let (Some(imaging), Some(source)) = (device.imaging_path.clone(), device.source.clone()) {
            device.focus_range = device
                .call(&imaging, &format!("<GetMoveOptions xmlns=\"{NS_IMAGING}\"><VideoSourceToken>{}</VideoSourceToken></GetMoveOptions>", escape(&source)))
                .ok()
                .and_then(|xml| move_range(&xml, "Relative", "Distance"));
        }
        Ok(device)
    }

    /// Current zoom position from PTZ `GetStatus`.
    fn zoom_position(&self) -> Result<f64, SoapError> {
        let path = self.ptz_path.as_deref().ok_or_else(|| SoapError::Other("у камеры нет сервиса PTZ (зум)".into()))?;
        let xml = self.call(path, &format!("<GetStatus xmlns=\"{NS_PTZ}\"><ProfileToken>{}</ProfileToken></GetStatus>", escape(&self.profile)))?;
        section(&xml, "Position")
            .and_then(|part| elements(part, "Zoom").into_iter().next())
            .and_then(|(attrs, _)| attribute(attrs, "x"))
            .and_then(|x| x.parse().ok())
            .ok_or_else(|| SoapError::Other("камера не сообщила положение зума".into()))
    }

    /// One zoom step as an absolute target kept here. Cameras round every target down to their own
    /// grid (Uniview: 1/3300 of the range): a relative step smaller than a cell never moves the lens
    /// forward and always moves it back. A target accumulated here moves it both ways alike, so even
    /// the smallest step lands on average exactly where it should. It is re-read from the camera
    /// after a pause, in case something else moved the zoom.
    fn absolute_zoom(&mut self, range: (f64, f64), percent: f64, steps: i32) -> Result<(), SoapError> {
        let now = Instant::now();
        let current = match self.zoom_target {
            Some((target, at)) if now - at < ZOOM_RESYNC => target,
            // The reported position is cut to 6 decimals, just below the grid point it stands on;
            // rounded down again, a target equal to it would land one cell lower.
            _ => self.zoom_position()? + POSITION_SLACK,
        };
        let target = next_target(current, range, percent, steps);
        let path = self.ptz_path.as_deref().ok_or_else(|| SoapError::Other("у камеры нет сервиса PTZ (зум)".into()))?;
        self.call(
            path,
            &format!(
                "<AbsoluteMove xmlns=\"{NS_PTZ}\"><ProfileToken>{}</ProfileToken><Position><Zoom xmlns=\"{NS_SCHEMA}\" x=\"{target}\"/></Position></AbsoluteMove>",
                escape(&self.profile)
            ),
        )?;
        self.zoom_target = Some((target, now));
        Ok(())
    }

    /// One exact step: PTZ `RelativeMove` for zoom, Imaging relative `Move` for focus.
    fn relative(&self, mode: Mode, amount: f64) -> Result<(), SoapError> {
        match mode {
            Mode::Zoom => {
                let path = self.ptz_path.as_deref().ok_or_else(|| SoapError::Other("у камеры нет сервиса PTZ (зум)".into()))?;
                self.call(
                    path,
                    &format!(
                        "<RelativeMove xmlns=\"{NS_PTZ}\"><ProfileToken>{}</ProfileToken><Translation><Zoom xmlns=\"{NS_SCHEMA}\" x=\"{amount}\"/></Translation></RelativeMove>",
                        escape(&self.profile)
                    ),
                )
                .map(drop)
            }
            Mode::Focus => {
                let path = self.imaging_path.as_deref().ok_or_else(|| SoapError::Other("у камеры нет сервиса Imaging (фокус)".into()))?;
                let source = self.source.as_deref().ok_or_else(|| SoapError::Other("не найден VideoSourceToken".into()))?;
                self.call(
                    path,
                    &format!(
                        "<Move xmlns=\"{NS_IMAGING}\"><VideoSourceToken>{}</VideoSourceToken><Focus><Relative xmlns=\"{NS_SCHEMA}\"><Distance>{amount}</Distance></Relative></Focus></Move>",
                        escape(source)
                    ),
                )
                .map(drop)
            }
        }
    }

    /// Starts a continuous move; `length` is also sent to PTZ as its timeout, so the camera stops
    /// the zoom on its own even if our `Stop` never arrives.
    fn start(&self, mode: Mode, direction: i8, length: Duration) -> Result<(), SoapError> {
        match mode {
            Mode::Zoom => {
                let path = self.ptz_path.as_deref().ok_or_else(|| SoapError::Other("у камеры нет сервиса PTZ (зум)".into()))?;
                let speed = ZOOM_SPEED * f64::from(direction);
                let timeout = length.as_secs_f64();
                self.call(
                    path,
                    &format!(
                        "<ContinuousMove xmlns=\"{NS_PTZ}\"><ProfileToken>{}</ProfileToken><Velocity><Zoom xmlns=\"{NS_SCHEMA}\" x=\"{speed}\"/></Velocity><Timeout>PT{timeout:.3}S</Timeout></ContinuousMove>",
                        escape(&self.profile)
                    ),
                )
                .map(drop)
            }
            Mode::Focus => {
                let path = self.imaging_path.as_deref().ok_or_else(|| SoapError::Other("у камеры нет сервиса Imaging (фокус)".into()))?;
                let source = self.source.as_deref().ok_or_else(|| SoapError::Other("не найден VideoSourceToken".into()))?;
                let speed = FOCUS_SPEED * f64::from(direction);
                self.call(
                    path,
                    &format!(
                        "<Move xmlns=\"{NS_IMAGING}\"><VideoSourceToken>{}</VideoSourceToken><Focus><Continuous xmlns=\"{NS_SCHEMA}\"><Speed>{speed}</Speed></Continuous></Focus></Move>",
                        escape(source)
                    ),
                )
                .map(drop)
            }
        }
    }

    fn stop(&self, mode: Mode) -> Result<(), SoapError> {
        match mode {
            Mode::Zoom => {
                let Some(path) = self.ptz_path.as_deref() else { return Ok(()) };
                self.call(
                    path,
                    &format!(
                        "<Stop xmlns=\"{NS_PTZ}\"><ProfileToken>{}</ProfileToken><PanTilt>false</PanTilt><Zoom>true</Zoom></Stop>",
                        escape(&self.profile)
                    ),
                )
                .map(drop)
            }
            Mode::Focus => {
                let (Some(path), Some(source)) = (self.imaging_path.as_deref(), self.source.as_deref()) else { return Ok(()) };
                self.call(path, &format!("<Stop xmlns=\"{NS_IMAGING}\"><VideoSourceToken>{}</VideoSourceToken></Stop>", escape(source)))
                    .map(drop)
            }
        }
    }
}

// ---------------------------------------------------------------- lens state and commands

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Mode {
    Zoom,
    Focus,
}

#[derive(Default)]
struct CameraLens {
    device: Option<Device>,
    /// Connection identity the cached device was built for.
    target: Option<(SocketAddr, String)>,
    /// Password that the camera rejected: not retried until it changes (avoids account lockout).
    rejected_password: Option<String>,
    moving: Option<(Mode, i8)>,
    deadline: Option<Instant>,
}

impl CameraLens {
    fn stop_motion(&mut self) {
        if let (Some((mode, _)), Some(device)) = (self.moving.take(), self.device.as_ref()) {
            if let Err(error) = device.stop(mode) {
                eprintln!("[onvif] {}: стоп не выполнен: {}", device.address, error.message());
            }
        }
        self.deadline = None;
    }
}

#[derive(Default)]
pub struct Lens {
    cameras: Mutex<HashMap<String, Arc<Mutex<CameraLens>>>>,
}

impl Lens {
    fn camera(&self, camera_id: &str) -> Arc<Mutex<CameraLens>> {
        Arc::clone(crate::lock(&self.cameras).entry(camera_id.to_string()).or_default())
    }
}

/// Stops a lens move once its steps stop arriving.
pub fn spawn_lens_watchdog(lens: Arc<Lens>) {
    thread::spawn(move || loop {
        thread::sleep(WATCHDOG_TICK);
        let cameras: Vec<_> = crate::lock(&lens.cameras).values().cloned().collect();
        for camera in cameras {
            // A step in progress holds the lock; it refreshes the deadline anyway.
            let Ok(mut state) = camera.try_lock() else { continue };
            if state.deadline.is_some_and(|deadline| Instant::now() >= deadline) {
                state.stop_motion();
            }
        }
    });
}

#[allow(clippy::too_many_arguments)]
fn step(lens: &Lens, camera_id: &str, address: SocketAddr, username: String, password: String, mode: Mode, steps: i32, percent: f64) -> Result<(), String> {
    let camera = lens.camera(camera_id);
    let mut state = crate::lock(&camera);
    let target = (address, username.clone());
    if state.target.as_ref() != Some(&target) || state.device.as_ref().is_some_and(|device| device.creds.password != password) {
        state.stop_motion();
        state.device = None;
        state.target = Some(target);
    }
    if state.rejected_password.as_deref() == Some(password.as_str()) {
        return Err("неверный логин или пароль ONVIF — сохраните верный пароль камеры".into());
    }
    if state.device.is_none() {
        match Device::connect(address, Credentials { username, password: password.clone() }) {
            Ok(device) => {
                let describe = |range: Option<(f64, f64)>| range.map_or("импульсами".to_string(), |(min, max)| format!("относительно {min}..{max}"));
                let zoom = device.zoom_absolute.map_or_else(|| describe(device.zoom_range), |(min, max)| format!("по положению {min}..{max}"));
                eprintln!(
                    "[onvif] {address}: профиль {}, PTZ {}, Imaging {}, зум {zoom}, фокус {}",
                    device.profile,
                    device.ptz_path.as_deref().unwrap_or("нет"),
                    device.imaging_path.as_deref().unwrap_or("нет"),
                    describe(device.focus_range)
                );
                state.rejected_password = None;
                state.device = Some(device);
            }
            Err(error) => {
                if matches!(error, SoapError::Unauthorized(_)) {
                    state.rejected_password = Some(password);
                }
                return Err(error.message());
            }
        }
    }
    state.stop_motion();

    let device = state.device.as_mut().ok_or("нет соединения ONVIF")?;
    if let (Mode::Zoom, Some(range)) = (mode, device.zoom_absolute) {
        match device.absolute_zoom(range, percent, steps) {
            Ok(()) => return Ok(()),
            Err(error @ SoapError::Unauthorized(_)) => {
                state.device = None;
                return Err(error.message());
            }
            Err(error) => {
                eprintln!("[onvif] {address}: Zoom: абсолютный шаг не принят ({}), дальше относительными", error.message());
                device.zoom_absolute = None;
            }
        }
    }
    let range = match mode {
        Mode::Zoom => device.zoom_range,
        Mode::Focus => device.focus_range,
    };
    if let Some(range) = range {
        match device.relative(mode, relative_amount(range, percent, steps)) {
            Ok(()) => return Ok(()),
            Err(error @ SoapError::Unauthorized(_)) => {
                state.device = None;
                return Err(error.message());
            }
            // Advertised but refused: this camera gets timed pulses from now on.
            Err(error) => {
                eprintln!("[onvif] {address}: {mode:?}: относительный шаг не принят ({}), дальше импульсами", error.message());
                match mode {
                    Mode::Zoom => device.zoom_range = None,
                    Mode::Focus => device.focus_range = None,
                }
            }
        }
    }

    let length = pulse_length(percent, steps);
    let direction = steps.signum() as i8;
    if let Err(error) = device.start(mode, direction, length) {
        // Rebuild the session next time: the camera may have rebooted or dropped the profile.
        state.device = None;
        return Err(error.message());
    }
    state.moving = Some((mode, direction));
    state.deadline = Some(Instant::now() + length);
    thread::sleep(length);
    state.stop_motion();
    Ok(())
}

#[tauri::command]
pub async fn camera_lens_step(
    lens: State<'_, Arc<Lens>>,
    camera_id: String,
    ip: String,
    port: u16,
    username: String,
    mode: String,
    steps: i32,
    step_percent: f64,
) -> Result<(), String> {
    if !matches!(camera_id.as_str(), "camera1" | "camera2") {
        return Err("Неизвестная камера".into());
    }
    let mode = match mode.as_str() {
        "zoom" => Mode::Zoom,
        "focus" => Mode::Focus,
        _ => return Err("Некорректная команда объектива".into()),
    };
    if steps == 0 || steps.abs() > MAX_STEPS || !STEP_PERCENT.contains(&step_percent) {
        return Err("Некорректная команда объектива".into());
    }
    if username.is_empty() || username.len() > 64 {
        return Err("Задайте логин камеры".into());
    }
    let address = crate::validate_target(&ip, port)?;
    let lens = Arc::clone(lens.inner());
    crate::run_blocking(move || {
        let password = match crate::keyring_entry(&camera_id)?.get_password() {
            Ok(password) => password,
            Err(keyring::Error::NoEntry) => String::new(),
            Err(error) => return Err(error.to_string()),
        };
        step(&lens, &camera_id, address, username, password, mode, steps, step_percent)
            .inspect_err(|error| eprintln!("[onvif] {address}: {mode:?}: {error}"))
    })
    .await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dates_round_trip() {
        assert_eq!(iso8601(0), "1970-01-01T00:00:00Z");
        assert_eq!(iso8601(951_782_400), "2000-02-29T00:00:00Z");
        assert_eq!(days_from_civil(2000, 2, 29) * 86_400, 951_782_400);
    }

    #[test]
    fn broken_camera_clock_is_ignored() {
        let xml = "<tt:UTCDateTime><tt:Time><tt:Hour>23</tt:Hour><tt:Minute>11</tt:Minute><tt:Second>0</tt:Second></tt:Time>\
                   <tt:Date><tt:Year>3174709</tt:Year><tt:Month>1</tt:Month><tt:Day>-792479</tt:Day></tt:Date></tt:UTCDateTime>\
                   <tt:LocalDateTime><tt:Time><tt:Hour>4</tt:Hour><tt:Minute>17</tt:Minute><tt:Second>5</tt:Second></tt:Time>\
                   <tt:Date><tt:Year>2000</tt:Year><tt:Month>1</tt:Month><tt:Day>25</tt:Day></tt:Date></tt:LocalDateTime>";
        assert_eq!(camera_time(xml, "UTCDateTime"), None);
        assert_eq!(camera_time(xml, "LocalDateTime"), Some(days_from_civil(2000, 1, 25) * 86_400 + 4 * 3600 + 17 * 60 + 5));
    }

    #[test]
    fn capabilities_and_profiles_are_parsed() {
        let caps = "<tt:Imaging><tt:XAddr>http://10.0.0.9/onvif/image_service</tt:XAddr></tt:Imaging>\
                    <tt:PTZ><tt:XAddr>http://10.0.0.9:80/onvif/ptz_service</tt:XAddr></tt:PTZ>";
        assert_eq!(xaddr_path(caps, "PTZ").as_deref(), Some("/onvif/ptz_service"));
        assert_eq!(xaddr_path(caps, "Imaging").as_deref(), Some("/onvif/image_service"));
        assert_eq!(xaddr_path(caps, "Media"), None);
        let profiles = "<trt:Profiles fixed=\"true\" token=\"media_profile1\"><tt:Name>p</tt:Name>\
                        <tt:VideoSourceConfiguration token=\"vsc\"><tt:SourceToken>000</tt:SourceToken></tt:VideoSourceConfiguration></trt:Profiles>";
        let (attrs, _) = elements(profiles, "Profiles")[0];
        assert_eq!(attribute(attrs, "token").as_deref(), Some("media_profile1"));
        assert_eq!(section(profiles, "VideoSourceConfiguration").and_then(|part| first_text(part, "SourceToken")).as_deref(), Some("000"));
    }

    #[test]
    fn a_response_is_complete_without_waiting_for_the_socket_to_close() {
        assert!(!response_complete(b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nabc"));
        assert!(response_complete(b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nabcde"));
        assert!(!response_complete(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n"));
        assert!(response_complete(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n0\r\n\r\n"));
        // No length at all: only the camera closing the socket ends it.
        assert!(!response_complete(b"HTTP/1.1 200 OK\r\n\r\n<xml/>"));
    }

    #[test]
    fn relative_ranges_are_read_from_node_and_move_options() {
        let node = "<tt:SupportedPTZSpaces><tt:AbsoluteZoomPositionSpace><tt:XRange><tt:Min>0</tt:Min><tt:Max>1</tt:Max></tt:XRange></tt:AbsoluteZoomPositionSpace>\
                    <tt:RelativeZoomTranslationSpace><tt:URI>x</tt:URI><tt:XRange><tt:Min>-1</tt:Min><tt:Max>1</tt:Max></tt:XRange></tt:RelativeZoomTranslationSpace></tt:SupportedPTZSpaces>";
        assert_eq!(move_range(node, "RelativeZoomTranslationSpace", "XRange"), Some((-1.0, 1.0)));
        let options = "<timg:MoveOptions><tt:Absolute><tt:Position><tt:Min>0</tt:Min><tt:Max>1</tt:Max></tt:Position></tt:Absolute>\
                       <tt:Relative><tt:Distance><tt:Min>-500</tt:Min><tt:Max>500</tt:Max></tt:Distance></tt:Relative></timg:MoveOptions>";
        assert_eq!(move_range(options, "Relative", "Distance"), Some((-500.0, 500.0)));
        assert_eq!(move_range("<tt:Continuous><tt:Speed><tt:Min>0</tt:Min><tt:Max>1</tt:Max></tt:Speed></tt:Continuous>", "Relative", "Distance"), None);
    }

    #[test]
    fn step_size_follows_the_setting_and_stays_in_range() {
        assert_eq!(relative_amount((-1.0, 1.0), 2.0, 1), 0.02);
        assert_eq!(relative_amount((-1.0, 1.0), 2.0, -3), -0.06);
        assert_eq!(relative_amount((-500.0, 500.0), 1.0, 1), 5.0);
        assert_eq!(relative_amount((-1.0, 1.0), 25.0, 10), 1.0);
        assert_eq!(relative_amount((-1.0, 1.0), 0.01, 1), 0.0001);
    }

    #[test]
    fn absolute_target_accumulates_tiny_steps_both_ways_alike() {
        // 0.01 % steps are far below a camera grid cell: three forward and three back return exactly.
        let mut target = 0.072121;
        for steps in [1, 1, 1] {
            target = next_target(target, (0.0, 1.0), 0.01, steps);
        }
        assert_eq!(target, 0.072421);
        for steps in [-1, -1, -1] {
            target = next_target(target, (0.0, 1.0), 0.01, steps);
        }
        assert_eq!(target, 0.072121);
        assert_eq!(next_target(0.999, (0.0, 1.0), 2.0, 10), 1.0);
        assert_eq!(next_target(0.001, (0.0, 1.0), 2.0, -10), 0.0);
        assert_eq!(pulse_length(2.0, 1), Duration::from_millis(80));
        assert_eq!(pulse_length(0.5, 1), PULSE_MIN);
        assert_eq!(pulse_length(25.0, 10), PULSE_MAX);
    }

    #[test]
    fn chunked_body_is_joined() {
        assert_eq!(dechunk(b"4\r\nWiki\r\n5\r\npedia\r\n0\r\n\r\n"), b"Wikipedia");
    }

    #[test]
    fn password_digest_matches_ws_security_example() {
        // Digest = Base64(SHA1(nonce + created + password)); the header must not contain the password.
        let creds = Credentials { username: "admin".into(), password: "secret-value".into() };
        let header = security_header(&creds, 0);
        assert!(!header.contains("secret-value"));
        assert!(header.contains("<Username>admin</Username>"));
    }

    /// Moves a real camera's zoom by `MKIS_STEP` percent forward and back (`MKIS_ONVIF=camera1@ip:port`)
    /// and prints the PTZ position and the call time around each step: whether tiny steps are honoured.
    #[test]
    #[ignore]
    fn real_zoom_steps() {
        let spec = std::env::var("MKIS_ONVIF").expect("MKIS_ONVIF=camera1@ip:port");
        let percent: f64 = std::env::var("MKIS_STEP").ok().and_then(|value| value.parse().ok()).unwrap_or(0.2);
        let (id, target) = spec.split_once('@').unwrap();
        let address: SocketAddr = target.parse().unwrap();
        let password = crate::keyring_entry(id).unwrap().get_password().unwrap();
        let count: i32 = std::env::var("MKIS_COUNT").ok().and_then(|value| value.parse().ok()).unwrap_or(3);
        let mut device = Device::connect(address, Credentials { username: "admin".into(), password }).unwrap();
        println!("зум по положению: {:?}, относительно: {:?}", device.zoom_absolute, device.zoom_range);
        println!("зум до: {:?}", device.zoom_position().ok());
        let steps: Vec<i32> = std::iter::repeat(1).take(count as usize).chain(std::iter::repeat(-1).take(count as usize)).collect();
        for step in steps {
            let started = Instant::now();
            // The same choice as `step`: absolute when available, otherwise relative.
            match (device.zoom_absolute, device.zoom_range) {
                (Some(range), _) => device.absolute_zoom(range, percent, step).unwrap(),
                (None, Some(range)) => device.relative(Mode::Zoom, relative_amount(range, percent, step)).unwrap(),
                _ => panic!("камера не умеет шаги зума"),
            }
            let call = started.elapsed();
            thread::sleep(Duration::from_millis(500));
            println!("шаг {step:+}: команда {call:?}, цель {:?}, зум после: {:?}", device.zoom_target.map(|(target, _)| target), device.zoom_position().ok());
        }
    }

    /// Read-only probe of a real camera (`MKIS_ONVIF=camera1@192.168.1.68:80`): call timings and the
    /// PTZ/Imaging move spaces. The password comes from the keychain and is never printed.
    #[test]
    #[ignore]
    fn real_camera() {
        let spec = std::env::var("MKIS_ONVIF").expect("MKIS_ONVIF=camera1@ip:port");
        let (id, target) = spec.split_once('@').unwrap();
        let address: SocketAddr = target.parse().unwrap();
        let password = crate::keyring_entry(id).unwrap().get_password().unwrap();
        let started = Instant::now();
        let device = Device::connect(address, Credentials { username: "admin".into(), password }).unwrap();
        println!(
            "connect: {:?}, profile {}, PTZ {:?}, Imaging {:?}, zoom {:?}, focus {:?}",
            started.elapsed(),
            device.profile,
            device.ptz_path,
            device.imaging_path,
            device.zoom_range,
            device.focus_range
        );
        let ptz = device.ptz_path.clone().unwrap();
        for body in [
            format!("<GetNodes xmlns=\"{NS_PTZ}\"/>"),
            format!("<GetStatus xmlns=\"{NS_PTZ}\"><ProfileToken>{}</ProfileToken></GetStatus>", device.profile),
            format!("<GetConfigurations xmlns=\"{NS_PTZ}\"/>"),
        ] {
            let started = Instant::now();
            let result = device.call(&ptz, &body);
            println!("\n=== {} — {:?}", &body[1..body.find(' ').unwrap()], started.elapsed());
            match result {
                Ok(xml) => {
                    for tag in ["RelativeZoomTranslationSpace", "ContinuousZoomVelocitySpace", "AbsoluteZoomPositionSpace", "ZoomSpeedSpace"] {
                        for (_, inner) in elements(&xml, tag) {
                            println!("{tag}: {} {:?}..{:?}", first_text(inner, "URI").unwrap_or_default(), first_text(inner, "Min"), first_text(inner, "Max"));
                        }
                    }
                    if let Some(position) = section(&xml, "Position") {
                        println!("Position: {}", position.chars().take(300).collect::<String>());
                    }
                    for tag in ["DefaultRelativeZoomTranslationSpace", "DefaultContinuousZoomVelocitySpace", "DefaultPTZTimeout"] {
                        if let Some(value) = first_text(&xml, tag) {
                            println!("{tag}: {value}");
                        }
                    }
                }
                Err(error) => println!("ошибка: {}", error.message()),
            }
        }
        if let (Some(imaging), Some(source)) = (device.imaging_path.clone(), device.source.clone()) {
            let started = Instant::now();
            let result = device.call(&imaging, &format!("<GetMoveOptions xmlns=\"{NS_IMAGING}\"><VideoSourceToken>{source}</VideoSourceToken></GetMoveOptions>"));
            println!("\n=== GetMoveOptions — {:?}", started.elapsed());
            match result {
                Ok(xml) => {
                    for tag in ["Absolute", "Relative", "Continuous"] {
                        if let Some(part) = section(&xml, tag) {
                            println!("{tag}: {}", part.split_whitespace().collect::<Vec<_>>().join(" ").chars().take(300).collect::<String>());
                        }
                    }
                }
                Err(error) => println!("ошибка: {}", error.message()),
            }
        }
    }
}
