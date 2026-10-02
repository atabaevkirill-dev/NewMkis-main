//! Laser rangefinder: the 3 km eye-safe module (1535 nm, class 1) behind a serial-to-TCP converter
//! (module UART 115200 8N1 ↔ TCP, project default 192.168.1.7:20108). Frames are
//! `EE 16 <len> 03 <command> <params…> <sum>` (docs/RANGEFINDER_PROTOCOL.md).
//!
//! One persistent link: a reader thread splits the byte stream into frames, sends every range reply
//! and fault report to the window as a `rangefinder` event (continuous ranging streams them) and hands
//! the other replies to the command waiting for them. Commands run one at a time.
//!
//! Continuous ranging fires the laser up to 10 times a second, so it always has a deadline: a watchdog
//! stops it when the deadline passes, and quitting the app stops it too.

use serde::Serialize;
use std::{
    collections::VecDeque,
    io::{Read, Write},
    net::{Shutdown, SocketAddr, TcpStream},
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Condvar, Mutex,
    },
    thread,
    time::{Duration, Instant},
};
use tauri::{AppHandle, Emitter, State};

const HEADER: [u8; 2] = [0xEE, 0x16];
const DEVICE: u8 = 0x03;
const CONNECT_TIMEOUT: Duration = Duration::from_secs(2);
const REPLY_TIMEOUT: Duration = Duration::from_millis(1500);
/// The first range after power-on takes up to 600 ms (manual); the converter adds a little.
const RANGE_TIMEOUT: Duration = Duration::from_millis(2500);
/// After the first range reply, more targets (multi-target mode) may follow.
const FOLLOW_UP: Duration = Duration::from_millis(200);
const MAX_QUEUED: usize = 64;
const WATCHDOG_TICK: Duration = Duration::from_millis(250);
/// A stop that was not confirmed is sent again after this.
const STOP_RETRY: Duration = Duration::from_secs(1);
pub const FREQUENCY_HZ: std::ops::RangeInclusive<u8> = 1..=10;
pub const GATE_METRES: std::ops::RangeInclusive<u16> = 10..=20_000;
const CONTINUOUS_SECONDS: std::ops::RangeInclusive<u32> = 1..=3600;

const SELF_TEST: u8 = 0x01;
const RANGE: u8 = 0x02;
const TARGET_MODE: u8 = 0x03;
const CONTINUOUS: u8 = 0x04;
const STOP: u8 = 0x05;
const FAULT: u8 = 0x06;
const FREQUENCY: u8 = 0xA1;
const SET_GATE_MIN: u8 = 0xA2;
const GATE_MIN: u8 = 0xA3;
const SET_GATE_MAX: u8 = 0xA4;
const GATE_MAX: u8 = 0xA5;
const FPGA_VERSION: u8 = 0xA6;
const MCU_VERSION: u8 = 0xA7;
const HARDWARE_VERSION: u8 = 0xA8;
const SERIAL: u8 = 0xA9;
const PULSES_TOTAL: u8 = 0x90;
const PULSES_SINCE_POWER_ON: u8 = 0x91;

pub(crate) fn frame(command: u8, params: &[u8]) -> Vec<u8> {
    let mut body = vec![DEVICE, command];
    body.extend_from_slice(params);
    let sum = body.iter().fold(0_u8, |acc, byte| acc.wrapping_add(*byte));
    let mut out = HEADER.to_vec();
    out.push(body.len() as u8);
    out.extend(body);
    out.push(sum);
    out
}

#[derive(Clone, Debug, PartialEq)]
pub(crate) struct Frame {
    pub command: u8,
    pub params: Vec<u8>,
}

/// Takes every complete, checked frame off the front of `buffer`. Bytes before a header, frames with a
/// bad length or checksum are skipped; an incomplete frame stays for the next read.
pub(crate) fn take_frames(buffer: &mut Vec<u8>) -> Vec<Frame> {
    let mut frames = Vec::new();
    loop {
        let Some(start) = buffer.windows(2).position(|pair| pair == HEADER) else {
            // A trailing 0xEE may be the first half of the next header.
            let keep = usize::from(buffer.last() == Some(&HEADER[0]));
            buffer.drain(..buffer.len() - keep);
            break;
        };
        buffer.drain(..start);
        if buffer.len() < 3 {
            break;
        }
        let length = usize::from(buffer[2]);
        if !(2..=6).contains(&length) {
            buffer.drain(..2);
            continue;
        }
        let total = 3 + length + 1;
        if buffer.len() < total {
            break;
        }
        let body = &buffer[3..3 + length];
        let sum = body.iter().fold(0_u8, |acc, byte| acc.wrapping_add(*byte));
        if sum != buffer[total - 1] || body[0] != DEVICE {
            buffer.drain(..2);
            continue;
        }
        frames.push(Frame { command: body[1], params: body[2..].to_vec() });
        buffer.drain(..total);
    }
    frames
}

/// One range result.
#[derive(Clone, Debug, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Target {
    /// Number of the target in multi-target mode (0 = first), 0 otherwise.
    pub index: u8,
    /// 0 single target, 1 a nearer target exists, 2 a farther target exists, 3 both, 4 out of range.
    pub code: u8,
    /// Metres; `None` when out of range.
    pub distance: Option<f64>,
}

fn target(params: &[u8]) -> Option<Target> {
    let [status, high, low, tenths] = params else { return None };
    let code = status & 0x0F;
    let distance = (code != 4).then(|| f64::from(u16::from_be_bytes([*high, *low])) + f64::from(*tenths) * 0.1);
    Some(Target { index: status >> 4, code, distance: distance.map(|metres| (metres * 10.0).round() / 10.0) })
}

/// Status bits of a self-test or fault report, 1 = normal; returns what is wrong.
fn faults(flags: u8) -> Vec<String> {
    const NAMES: [&str; 8] = [
        "сбой FPGA",
        "нет излучения лазера",
        "нет опорного импульса",
        "нет отражения",
        "смещение приёмника выключено",
        "смещение приёмника не в норме",
        "температура вне нормы",
        "излучение заблокировано",
    ];
    (0..8).filter(|bit| flags & (1 << bit) == 0).map(|bit| NAMES[bit].to_string()).collect()
}

const NO_ECHO: &str = "нет отражения";

#[derive(Clone, Serialize)]
#[serde(tag = "kind", rename_all = "camelCase")]
pub enum Event {
    #[serde(rename_all = "camelCase")]
    Target { target: Target, continuous: bool },
    /// The module reports a fault after a range reply (only when something is wrong).
    #[serde(rename_all = "camelCase")]
    Fault { flags: u8, faults: Vec<String> },
    #[serde(rename_all = "camelCase")]
    Continuous { on: bool, reason: String },
    #[serde(rename_all = "camelCase")]
    Link { connected: bool, message: String },
}

fn emit(app: &AppHandle, event: Event) {
    let _ = app.emit("rangefinder", event);
}

#[derive(Default)]
struct Replies {
    queue: Mutex<VecDeque<Frame>>,
    ready: Condvar,
    closed: AtomicBool,
}

impl Replies {
    fn push(&self, frame: Frame) {
        let mut queue = self.queue.lock().unwrap_or_else(|poison| poison.into_inner());
        if queue.len() >= MAX_QUEUED {
            queue.pop_front();
        }
        queue.push_back(frame);
        self.ready.notify_all();
    }

    fn close(&self) {
        self.closed.store(true, Ordering::SeqCst);
        self.ready.notify_all();
    }

    /// Waits for a frame with `command`; `None` on timeout or a closed link.
    fn wait(&self, command: u8, deadline: Instant) -> Option<Frame> {
        let mut queue = self.queue.lock().unwrap_or_else(|poison| poison.into_inner());
        loop {
            if let Some(position) = queue.iter().position(|frame| frame.command == command) {
                return queue.remove(position);
            }
            let now = Instant::now();
            if self.closed.load(Ordering::SeqCst) || now >= deadline {
                return None;
            }
            queue = self.ready.wait_timeout(queue, deadline - now).unwrap_or_else(|poison| poison.into_inner()).0;
        }
    }

    fn forget(&self, command: u8) {
        self.queue.lock().unwrap_or_else(|poison| poison.into_inner()).retain(|frame| frame.command != command);
    }
}

struct Link {
    address: SocketAddr,
    writer: TcpStream,
    replies: Arc<Replies>,
}

struct Running {
    address: SocketAddr,
    until: Instant,
}

#[derive(Default)]
pub struct Rangefinder {
    link: Mutex<Option<Link>>,
    /// One command at a time.
    busy: Mutex<()>,
    continuous: Mutex<Option<Running>>,
}

fn reader(app: AppHandle, address: SocketAddr, mut stream: TcpStream, replies: Arc<Replies>) {
    let mut pending = Vec::new();
    let mut buffer = [0_u8; 512];
    let message = loop {
        match stream.read(&mut buffer) {
            Ok(0) => break "соединение закрыто".to_string(),
            Ok(count) => {
                pending.extend_from_slice(&buffer[..count]);
                for frame in take_frames(&mut pending) {
                    match frame.command {
                        RANGE | CONTINUOUS => {
                            if let Some(target) = target(&frame.params) {
                                emit(&app, Event::Target { target, continuous: frame.command == CONTINUOUS });
                            }
                        }
                        FAULT => {
                            if let Some(flags) = frame.params.get(3) {
                                emit(&app, Event::Fault { flags: *flags, faults: faults(*flags) });
                            }
                        }
                        _ => {}
                    }
                    replies.push(frame);
                }
            }
            Err(error) if matches!(error.kind(), std::io::ErrorKind::Interrupted) => continue,
            Err(error) => break error.to_string(),
        }
    };
    replies.close();
    eprintln!("[rangefinder] {address}: {message}");
    emit(&app, Event::Link { connected: false, message });
}

impl Rangefinder {
    /// The link to `address`, connected (or reconnected) when needed.
    fn link(&self, app: &AppHandle, address: SocketAddr) -> Result<(TcpStream, Arc<Replies>), String> {
        let mut slot = self.link.lock().unwrap_or_else(|poison| poison.into_inner());
        if let Some(link) = slot.as_ref() {
            if link.address == address && !link.replies.closed.load(Ordering::SeqCst) {
                return Ok((link.writer.try_clone().map_err(|error| error.to_string())?, Arc::clone(&link.replies)));
            }
            let _ = link.writer.shutdown(Shutdown::Both);
        }
        *slot = None;
        let stream = TcpStream::connect_timeout(&address, CONNECT_TIMEOUT).map_err(|error| format!("{address}: {error}"))?;
        let _ = stream.set_nodelay(true);
        stream.set_write_timeout(Some(REPLY_TIMEOUT)).map_err(|error| error.to_string())?;
        let replies = Arc::new(Replies::default());
        let read_half = stream.try_clone().map_err(|error| error.to_string())?;
        let (thread_app, thread_replies) = (app.clone(), Arc::clone(&replies));
        thread::spawn(move || reader(thread_app, address, read_half, thread_replies));
        eprintln!("[rangefinder] {address}: связь установлена");
        emit(app, Event::Link { connected: true, message: address.to_string() });
        let writer = stream.try_clone().map_err(|error| error.to_string())?;
        *slot = Some(Link { address, writer, replies: Arc::clone(&replies) });
        Ok((stream, replies))
    }

    /// Sends a command and waits for the reply with `expect`.
    fn request(&self, app: &AppHandle, address: SocketAddr, command: u8, params: &[u8], expect: u8, timeout: Duration) -> Result<Frame, String> {
        let (mut writer, replies) = self.link(app, address)?;
        replies.forget(expect);
        if let Err(error) = writer.write_all(&frame(command, params)) {
            replies.close();
            return Err(format!("дальномер: {error}"));
        }
        replies
            .wait(expect, Instant::now() + timeout)
            .ok_or_else(|| if replies.closed.load(Ordering::SeqCst) { "связь с дальномером прервана".to_string() } else { format!("дальномер не ответил за {} мс", timeout.as_millis()) })
    }

    fn continuous_running(&self) -> bool {
        self.continuous.lock().unwrap_or_else(|poison| poison.into_inner()).is_some()
    }

    /// Stops continuous ranging; when the stop is not confirmed it is tried again by the watchdog.
    fn stop(&self, app: &AppHandle, address: SocketAddr, reason: &str) -> Result<(), String> {
        let _busy = self.busy.lock().unwrap_or_else(|poison| poison.into_inner());
        match self.request(app, address, STOP, &[], STOP, REPLY_TIMEOUT) {
            Ok(_) => {
                *self.continuous.lock().unwrap_or_else(|poison| poison.into_inner()) = None;
                eprintln!("[rangefinder] {address}: непрерывный замер остановлен ({reason})");
                emit(app, Event::Continuous { on: false, reason: reason.to_string() });
                Ok(())
            }
            Err(error) => {
                if let Some(running) = self.continuous.lock().unwrap_or_else(|poison| poison.into_inner()).as_mut() {
                    running.until = Instant::now() + STOP_RETRY;
                }
                Err(format!("стоп не подтверждён: {error}"))
            }
        }
    }

    /// Sends a stop without waiting (the app is closing).
    pub fn stop_on_exit(&self) {
        if !self.continuous_running() {
            return;
        }
        if let Some(link) = self.link.lock().unwrap_or_else(|poison| poison.into_inner()).as_mut() {
            let _ = link.writer.write_all(&frame(STOP, &[]));
            eprintln!("[rangefinder] {}: стоп при выходе", link.address);
        }
    }
}

/// Stops continuous ranging when its deadline passes (and retries an unconfirmed stop).
pub fn spawn_watchdog(rangefinder: Arc<Rangefinder>, app: AppHandle) {
    thread::spawn(move || loop {
        thread::sleep(WATCHDOG_TICK);
        let due = rangefinder
            .continuous
            .lock()
            .unwrap_or_else(|poison| poison.into_inner())
            .as_ref()
            .filter(|running| Instant::now() >= running.until)
            .map(|running| running.address);
        if let Some(address) = due {
            if let Err(error) = rangefinder.stop(&app, address, "истёк срок непрерывного замера") {
                eprintln!("[rangefinder] {address}: {error}");
            }
        }
    });
}

fn version(params: &[u8]) -> String {
    match params {
        [version, day, month_year, ..] => format!("V{}.{} · {:02}.{:02}.{}", version >> 4, version & 0x0F, day, month_year >> 4, 2020 + u32::from(month_year & 0x0F)),
        _ => "—".into(),
    }
}

fn counter(params: &[u8]) -> Option<u32> {
    match params {
        [high, middle, low] => Some(u32::from_be_bytes([0, *high, *middle, *low])),
        _ => None,
    }
}

fn metres(params: &[u8]) -> Option<u16> {
    match params {
        [high, low, ..] => Some(u16::from_be_bytes([*high, *low])),
        _ => None,
    }
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Info {
    pub serial: String,
    pub fpga: String,
    pub mcu: String,
    pub hardware: String,
    pub pulses_total: Option<u32>,
    pub pulses_since_power_on: Option<u32>,
    pub gate_min: Option<u16>,
    pub gate_max: Option<u16>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SelfTest {
    pub ok: bool,
    /// Echo intensity 0–255.
    pub echo: u8,
    pub power_ok: bool,
    /// Everything that is not normal («нет отражения» only means nothing is in front of the module).
    pub faults: Vec<String>,
    pub raw: String,
}

fn self_test(params: &[u8]) -> Option<SelfTest> {
    let [_, echo, flags, power] = params else { return None };
    let mut faults = faults(*flags);
    let power_ok = power & 1 == 1;
    if !power_ok {
        faults.push("питание 5,6 В не в норме".into());
    }
    let ok = faults.iter().all(|fault| fault == NO_ECHO);
    Some(SelfTest { ok, echo: *echo, power_ok, faults, raw: params.iter().map(|byte| format!("{byte:02X}")).collect::<Vec<_>>().join(" ") })
}

#[derive(Serialize)]
pub struct Gates {
    pub min: Option<u16>,
    pub max: Option<u16>,
}

fn address(ip: &str, port: u16) -> Result<SocketAddr, String> {
    crate::validate_target(ip, port)
}

/// One range measurement (single shot); all targets the module reports for it.
#[tauri::command]
pub async fn rangefinder_measure(app: AppHandle, rangefinder: State<'_, Arc<Rangefinder>>, ip: String, port: u16) -> Result<Vec<Target>, String> {
    let address = address(&ip, port)?;
    let rangefinder = Arc::clone(rangefinder.inner());
    crate::run_blocking(move || {
        if rangefinder.continuous_running() {
            return Err("идёт непрерывный замер".into());
        }
        let _busy = rangefinder.busy.lock().unwrap_or_else(|poison| poison.into_inner());
        let first = rangefinder.request(&app, address, RANGE, &[], RANGE, RANGE_TIMEOUT)?;
        let mut targets: Vec<Target> = target(&first.params).into_iter().collect();
        // Multi-target mode: one reply per target, sent back to back.
        let (_, replies) = rangefinder.link(&app, address)?;
        let deadline = Instant::now() + FOLLOW_UP;
        while let Some(next) = replies.wait(RANGE, deadline) {
            targets.extend(target(&next.params));
        }
        Ok(targets)
    })
    .await
}

/// Starts continuous ranging at `frequency_hz` for at most `max_seconds`, or stops it.
#[tauri::command]
pub async fn rangefinder_continuous(app: AppHandle, rangefinder: State<'_, Arc<Rangefinder>>, ip: String, port: u16, on: bool, frequency_hz: u8, max_seconds: u32) -> Result<(), String> {
    let address = address(&ip, port)?;
    if on && (!FREQUENCY_HZ.contains(&frequency_hz) || !CONTINUOUS_SECONDS.contains(&max_seconds)) {
        return Err("Частота 1–10 Гц, длительность 1–3600 с".into());
    }
    let rangefinder = Arc::clone(rangefinder.inner());
    crate::run_blocking(move || {
        if !on {
            return rangefinder.stop(&app, address, "остановлен оператором");
        }
        let _busy = rangefinder.busy.lock().unwrap_or_else(|poison| poison.into_inner());
        rangefinder.request(&app, address, FREQUENCY, &[frequency_hz, 0], FREQUENCY, REPLY_TIMEOUT)?;
        // The deadline is set before the start, so even a start whose reply is lost gets stopped.
        *rangefinder.continuous.lock().unwrap_or_else(|poison| poison.into_inner()) = Some(Running { address, until: Instant::now() + Duration::from_secs(u64::from(max_seconds)) });
        rangefinder.request(&app, address, CONTINUOUS, &[], CONTINUOUS, RANGE_TIMEOUT)?;
        eprintln!("[rangefinder] {address}: непрерывный замер {frequency_hz} Гц, не дольше {max_seconds} с");
        emit(&app, Event::Continuous { on: true, reason: format!("{frequency_hz} Гц · автостоп через {max_seconds} с") });
        Ok(())
    })
    .await
}

/// First, last or several targets (`first`, `last`, `multi`).
#[tauri::command]
pub async fn rangefinder_target_mode(app: AppHandle, rangefinder: State<'_, Arc<Rangefinder>>, ip: String, port: u16, mode: String) -> Result<(), String> {
    let address = address(&ip, port)?;
    let code = match mode.as_str() {
        "first" => 1,
        "last" => 2,
        "multi" => 3,
        _ => return Err("Режим цели: first, last или multi".into()),
    };
    let rangefinder = Arc::clone(rangefinder.inner());
    crate::run_blocking(move || {
        let _busy = rangefinder.busy.lock().unwrap_or_else(|poison| poison.into_inner());
        rangefinder.request(&app, address, TARGET_MODE, &[code], TARGET_MODE, REPLY_TIMEOUT).map(|_| ())
    })
    .await
}

/// Range gate: targets nearer than `min` or farther than `max` metres are ignored. Values given are
/// written first; the gate the module holds is returned.
#[tauri::command]
pub async fn rangefinder_gates(app: AppHandle, rangefinder: State<'_, Arc<Rangefinder>>, ip: String, port: u16, min: Option<u16>, max: Option<u16>) -> Result<Gates, String> {
    let address = address(&ip, port)?;
    if min.iter().chain(max.iter()).any(|value| !GATE_METRES.contains(value)) {
        return Err("Строб: от 10 до 20000 м".into());
    }
    if let (Some(min), Some(max)) = (min, max) {
        if min >= max {
            return Err("Строб: ближняя граница должна быть меньше дальней".into());
        }
    }
    let rangefinder = Arc::clone(rangefinder.inner());
    crate::run_blocking(move || {
        let _busy = rangefinder.busy.lock().unwrap_or_else(|poison| poison.into_inner());
        if let Some(min) = min {
            rangefinder.request(&app, address, SET_GATE_MIN, &min.to_be_bytes(), SET_GATE_MIN, REPLY_TIMEOUT)?;
        }
        if let Some(max) = max {
            rangefinder.request(&app, address, SET_GATE_MAX, &max.to_be_bytes(), SET_GATE_MAX, REPLY_TIMEOUT)?;
        }
        let min = metres(&rangefinder.request(&app, address, GATE_MIN, &[], GATE_MIN, REPLY_TIMEOUT)?.params);
        let max = metres(&rangefinder.request(&app, address, GATE_MAX, &[], GATE_MAX, REPLY_TIMEOUT)?.params);
        Ok(Gates { min, max })
    })
    .await
}

/// Built-in test of the module (it fires the laser once).
#[tauri::command]
pub async fn rangefinder_self_test(app: AppHandle, rangefinder: State<'_, Arc<Rangefinder>>, ip: String, port: u16) -> Result<SelfTest, String> {
    let address = address(&ip, port)?;
    let rangefinder = Arc::clone(rangefinder.inner());
    crate::run_blocking(move || {
        if rangefinder.continuous_running() {
            return Err("идёт непрерывный замер".into());
        }
        let _busy = rangefinder.busy.lock().unwrap_or_else(|poison| poison.into_inner());
        let reply = rangefinder.request(&app, address, SELF_TEST, &[], SELF_TEST, RANGE_TIMEOUT)?;
        self_test(&reply.params).ok_or_else(|| "некорректный ответ самодиагностики".into())
    })
    .await
}

/// Serial number, firmware and hardware versions, pulse counters and range gate (no laser emission).
#[tauri::command]
pub async fn rangefinder_info(app: AppHandle, rangefinder: State<'_, Arc<Rangefinder>>, ip: String, port: u16) -> Result<Info, String> {
    let address = address(&ip, port)?;
    let rangefinder = Arc::clone(rangefinder.inner());
    crate::run_blocking(move || {
        let _busy = rangefinder.busy.lock().unwrap_or_else(|poison| poison.into_inner());
        let ask = |command: u8| rangefinder.request(&app, address, command, &[], command, REPLY_TIMEOUT).map(|reply| reply.params);
        let serial = match ask(SERIAL)?.as_slice() {
            [month_year, high, low] => format!("{:02}.{} № {}", month_year >> 4, 2020 + u32::from(month_year & 0x0F), u16::from_be_bytes([*high, *low])),
            _ => "—".into(),
        };
        let hardware = match ask(HARDWARE_VERSION)?.as_slice() {
            [board, control, detector, driver] => {
                let v = |byte: &u8| format!("V{}.{}", byte >> 4, byte & 0x0F);
                format!("плата {} · управление {} · приёмник {} · драйвер {}", v(board), v(control), v(detector), v(driver))
            }
            _ => "—".into(),
        };
        Ok(Info {
            serial,
            fpga: version(&ask(FPGA_VERSION)?),
            mcu: version(&ask(MCU_VERSION)?),
            hardware,
            pulses_total: counter(&ask(PULSES_TOTAL)?),
            pulses_since_power_on: counter(&ask(PULSES_SINCE_POWER_ON)?),
            gate_min: metres(&ask(GATE_MIN)?),
            gate_max: metres(&ask(GATE_MAX)?),
        })
    })
    .await
}

#[cfg(test)]
mod tests {
    use super::*;

    fn bytes(hex: &str) -> Vec<u8> {
        hex.split_whitespace().map(|byte| u8::from_str_radix(byte, 16).unwrap()).collect()
    }

    #[test]
    fn frames_match_the_manual_examples() {
        assert_eq!(frame(RANGE, &[]), bytes("ee 16 02 03 02 05"));
        assert_eq!(frame(TARGET_MODE, &[1]), bytes("ee 16 03 03 03 01 07"));
        assert_eq!(frame(FREQUENCY, &[5, 0]), bytes("ee 16 04 03 a1 05 00 a9"));
        assert_eq!(frame(STOP, &[]), bytes("ee 16 02 03 05 08"));
    }

    #[test]
    fn the_stream_is_split_into_checked_frames() {
        // Noise, a frame, a frame with a broken checksum, a frame split across reads.
        let mut buffer = bytes("00 ff ee 16 06 03 02 00 01 2c 05 37 ee 16 02 03 05 09 ee 16 06 03");
        let frames = take_frames(&mut buffer);
        assert_eq!(frames, vec![Frame { command: RANGE, params: vec![0x00, 0x01, 0x2C, 0x05] }]);
        assert_eq!(buffer, bytes("ee 16 06 03"), "the incomplete frame waits for the rest");
        buffer.extend(bytes("04 04 00 00 00 0b"));
        assert_eq!(take_frames(&mut buffer), vec![Frame { command: CONTINUOUS, params: vec![0x04, 0, 0, 0] }]);
        assert!(buffer.is_empty());
    }

    #[test]
    fn ranges_and_states_are_decoded() {
        assert_eq!(target(&[0x00, 0x01, 0x2C, 0x05]), Some(Target { index: 0, code: 0, distance: Some(300.5) }));
        // Manual example: out of range.
        assert_eq!(target(&bytes("04 00 00 00")), Some(Target { index: 0, code: 4, distance: None }));
        // Multi-target mode: second target, a nearer one exists.
        assert_eq!(target(&[0x11, 0x10, 0x68, 0x00]), Some(Target { index: 1, code: 1, distance: Some(4200.0) }));
    }

    #[test]
    fn self_test_of_the_manual_example_is_healthy_without_a_target() {
        // RECV: ee 16 06 03 01 ff 00 f7 ff f9 — everything normal, no echo.
        let test = self_test(&bytes("ff 00 f7 ff")).unwrap();
        assert!(test.ok);
        assert_eq!(test.faults, vec![NO_ECHO.to_string()]);
        let broken = self_test(&bytes("ff 00 b5 fe")).unwrap();
        assert!(!broken.ok);
        assert!(broken.faults.contains(&"нет излучения лазера".to_string()) && broken.faults.contains(&"температура вне нормы".to_string()));
        assert!(!broken.power_ok);
    }

    #[test]
    fn versions_and_counters_of_the_stand_module_are_decoded() {
        // Answers of the stand module (2026-10-02).
        assert_eq!(version(&bytes("16 1c 24 6c")), "V1.6 · 28.02.2024");
        assert_eq!(version(&bytes("23 14 c3 66")), "V2.3 · 20.12.2023");
        assert_eq!(counter(&bytes("00 25 03")), Some(9475));
        assert_eq!(metres(&bytes("10 68")), Some(4200));
    }

    /// Read-only probe of the real module (`MKIS_LRF=192.168.1.7:20108`): versions, serial, counters
    /// and gate, with reply times. Nothing here fires the laser.
    #[test]
    #[ignore]
    fn real_rangefinder_info() {
        let address: SocketAddr = std::env::var("MKIS_LRF").expect("MKIS_LRF=ip:port").parse().unwrap();
        let mut stream = TcpStream::connect_timeout(&address, CONNECT_TIMEOUT).unwrap();
        stream.set_read_timeout(Some(Duration::from_millis(100))).unwrap();
        for command in [SERIAL, FPGA_VERSION, MCU_VERSION, HARDWARE_VERSION, PULSES_TOTAL, PULSES_SINCE_POWER_ON, GATE_MIN, GATE_MAX] {
            let started = Instant::now();
            stream.write_all(&frame(command, &[])).unwrap();
            let mut pending = Vec::new();
            let mut buffer = [0_u8; 64];
            let reply = loop {
                if let Ok(count) = stream.read(&mut buffer) {
                    pending.extend_from_slice(&buffer[..count]);
                }
                if let Some(frame) = take_frames(&mut pending).into_iter().find(|frame| frame.command == command) {
                    break Some(frame);
                }
                if started.elapsed() > REPLY_TIMEOUT {
                    break None;
                }
            };
            println!("{command:#04x}: {:?} — {:?}", reply.map(|frame| frame.params), started.elapsed());
        }
    }
}
