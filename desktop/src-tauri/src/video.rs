//! RTSP video: the native side receives H.264/H.265 access units and forwards them unchanged;
//! the webview decodes them with WebCodecs (software decoder: the hardware one released frames in
//! bursts with 150–240 ms stalls; no FFmpeg).
//!
//! Binary messages sent over the channel:
//! - `1` config: `u16 codedW, u16 codedH, u16 width, u16 height, u8 codecLen, codec, description`
//! - `2` frame: `u8 flags (bit 0 = key frame), i64 timestamp µs, access unit (4-byte length NALs)`
//! - `3` state: `u8 state (0 connecting, 1 playing, 2 error), UTF-8 message`

use crate::record::{CameraRecorder, RecordSettings, RecordingEvent, Source};
use futures::StreamExt;
use retina::client::{Credentials, PlayOptions, Session, SessionGroup, SessionOptions, SetupOptions};
use retina::codec::{CodecItem, FrameFormat, ParametersRef, VideoParameters};
use std::{collections::HashMap, sync::Arc, sync::Mutex, time::Duration};
use tauri::{
    async_runtime::JoinHandle,
    ipc::{Channel, InvokeResponseBody},
    AppHandle, Emitter, State,
};
use url::Url;

const MSG_CONFIG: u8 = 1;
const MSG_FRAME: u8 = 2;
const MSG_STATE: u8 = 3;
const STATE_CONNECTING: u8 = 0;
const STATE_PLAYING: u8 = 1;
const STATE_ERROR: u8 = 2;
const CONNECT_TIMEOUT: Duration = Duration::from_secs(6);
/// No frame for this long means the camera stalled: the session is reopened.
const STALL_TIMEOUT: Duration = Duration::from_secs(5);
const RETRY_DELAY: Duration = Duration::from_secs(3);
const AUTH_FAILED: &str = "неверный логин или пароль (401) — повтор остановлен, чтобы камера не заблокировала учётную запись";

fn is_auth_failure(message: &str) -> bool {
    message.contains("401") || message.contains("Unauthorized")
}

/// A camera answering «404» means the path is wrong, not the address: the RTSP error alone does not
/// say that, and every vendor spells the path differently.
fn explain(message: &str) -> String {
    if message.contains("404") || message.contains("Not Found") {
        format!("{message} — проверьте путь потока: Uniview /media/video1, Dahua /cam/realmonitor?channel=1&subtype=0, Beward /av0_0")
    } else {
        message.to_string()
    }
}

/// One stream task per camera, tagged with the UI token that started it. Starting a camera again
/// replaces its task; a stop only ends the task it was issued for, so a late stop from an unmounted
/// view never kills the stream a newer view has just started.
#[derive(Default)]
pub struct Streams {
    tasks: Mutex<HashMap<String, (u64, JoinHandle<()>)>>,
    /// Current recording request; each stream task compares it with what it is writing.
    recording: Arc<Mutex<Option<RecordSettings>>>,
}

/// Everything a stream task needs besides the UI channel.
struct StreamContext {
    camera_id: String,
    url: Url,
    creds: Option<Credentials>,
    recording: Arc<Mutex<Option<RecordSettings>>>,
    app: AppHandle,
}

impl StreamContext {
    fn emit(&self, event: RecordingEvent) {
        if let Some(message) = &event.message {
            eprintln!("[record] {}: {message}", self.camera_id);
        }
        let _ = self.app.emit("recording-state", event);
    }

    /// Starts, keeps or stops this camera's recorder so it matches the current request.
    fn sync_recorder(&self, recorder: &mut Option<CameraRecorder>, clock_rate: u32) {
        let wanted = crate::lock(&self.recording).clone().filter(|settings| settings.includes(&self.camera_id));
        if recorder.as_ref().map(|current| &current.settings) == wanted.as_ref() {
            return;
        }
        if let Some(previous) = recorder.take() {
            self.emit(previous.finish());
        }
        *recorder = wanted.map(|settings| {
            let source = Source { camera_id: self.camera_id.clone(), url: self.url.to_string() };
            CameraRecorder::new(settings, source, clock_rate)
        });
    }
}

impl Streams {
    fn start(&self, camera_id: &str, token: u64, task: JoinHandle<()>) {
        let previous = crate::lock(&self.tasks).insert(camera_id.to_string(), (token, task));
        if let Some((_, previous)) = previous {
            previous.abort();
        }
    }

    fn stop(&self, camera_id: &str, token: u64) {
        let mut tasks = crate::lock(&self.tasks);
        if tasks.get(camera_id).is_some_and(|(current, _)| *current == token) {
            if let Some((_, task)) = tasks.remove(camera_id) {
                task.abort();
            }
        }
    }
}

fn validate_camera(camera_id: &str) -> Result<(), String> {
    if matches!(camera_id, "camera1" | "camera2") {
        Ok(())
    } else {
        Err("Неизвестная камера".into())
    }
}

/// Builds the stream URL without credentials: they are passed to the digest handshake separately.
pub(crate) fn stream_url(ip: &str, port: u16, path: &str) -> Result<Url, String> {
    let address = crate::validate_target(ip, port)?;
    let valid_path = path.starts_with('/')
        && path.len() <= 256
        && path
            .bytes()
            .all(|byte| byte.is_ascii_graphic() && !matches!(byte, b'@' | b'\\' | b'#'));
    if !valid_path {
        return Err("Некорректный путь потока: ожидается вида /media/video1".into());
    }
    Url::parse(&format!("rtsp://{address}{path}")).map_err(|error| error.to_string())
}

fn send(channel: &Channel<InvokeResponseBody>, bytes: Vec<u8>) -> Result<(), String> {
    channel
        .send(InvokeResponseBody::Raw(bytes))
        .map_err(|error| error.to_string())
}

fn send_state(channel: &Channel<InvokeResponseBody>, state: u8, message: &str) -> Result<(), String> {
    let mut bytes = vec![MSG_STATE, state];
    bytes.extend_from_slice(message.as_bytes());
    send(channel, bytes)
}

pub(crate) fn config_message(params: &VideoParameters) -> Vec<u8> {
    let (coded_width, coded_height) = params.coded_pixel_dimensions();
    let (width, height) = params.pixel_dimensions();
    let codec = params.rfc6381_codec().as_bytes();
    let description = params.extra_data();
    let mut bytes = Vec::with_capacity(10 + codec.len() + description.len());
    bytes.push(MSG_CONFIG);
    for value in [coded_width, coded_height, width, height] {
        bytes.extend_from_slice(&(value.min(u32::from(u16::MAX)) as u16).to_le_bytes());
    }
    bytes.push(codec.len().min(255) as u8);
    bytes.extend_from_slice(&codec[..codec.len().min(255)]);
    bytes.extend_from_slice(description);
    bytes
}

pub(crate) fn frame_message(key: bool, timestamp_us: i64, data: &[u8]) -> Vec<u8> {
    let mut bytes = Vec::with_capacity(10 + data.len());
    bytes.push(MSG_FRAME);
    bytes.push(u8::from(key));
    bytes.extend_from_slice(&timestamp_us.to_le_bytes());
    bytes.extend_from_slice(data);
    bytes
}

/// Diagnostics: logs a 5 s summary whenever frames arrived with a pause over 150 ms, with how long handing them
/// to the webview takes, so a stutter can be placed on the camera/network side or the display side.
struct FrameTiming {
    window: std::time::Instant,
    last: Option<std::time::Instant>,
    frames: u32,
    max_gap: Duration,
    max_send: Duration,
    max_bytes: usize,
}

impl FrameTiming {
    fn new() -> Self {
        Self { window: std::time::Instant::now(), last: None, frames: 0, max_gap: Duration::ZERO, max_send: Duration::ZERO, max_bytes: 0 }
    }

    fn frame(&mut self, url: &Url, bytes: usize, send: Duration) {
        let now = std::time::Instant::now();
        if let Some(last) = self.last {
            self.max_gap = self.max_gap.max(now - last);
        }
        self.last = Some(now);
        self.frames += 1;
        self.max_send = self.max_send.max(send);
        self.max_bytes = self.max_bytes.max(bytes);
        let elapsed = now - self.window;
        if elapsed >= Duration::from_secs(5) && self.max_gap < Duration::from_millis(150) {
            *self = Self { last: self.last, ..Self::new() };
        } else if elapsed >= Duration::from_secs(5) {
            eprintln!(
                "[diag] {}: приход {:.1} к/с, макс. пауза {} мс, макс. кадр {} КБ, макс. передача в окно {} мс",
                url.host_str().unwrap_or("?"),
                f64::from(self.frames) / elapsed.as_secs_f64(),
                self.max_gap.as_millis(),
                self.max_bytes / 1024,
                self.max_send.as_millis()
            );
            *self = Self { last: self.last, ..Self::new() };
        }
    }
}

async fn play(
    context: &StreamContext,
    channel: &Channel<InvokeResponseBody>,
    recorder: &mut Option<CameraRecorder>,
) -> Result<(), String> {
    let url = &context.url;
    let options = SessionOptions::default()
        .creds(context.creds.clone())
        .user_agent("MKIS100TEST".into())
        .session_group(Arc::new(SessionGroup::default()));
    let mut session = tokio::time::timeout(CONNECT_TIMEOUT, Session::describe(url.clone(), options))
        .await
        .map_err(|_| "камера не ответила на DESCRIBE".to_string())?
        .map_err(|error| error.to_string())?;
    let index = session
        .streams()
        .iter()
        .position(|stream| stream.media() == "video" && matches!(stream.encoding_name(), "h264" | "h265"))
        .ok_or_else(|| {
            let found: Vec<String> = session
                .streams()
                .iter()
                .map(|stream| format!("{}/{}", stream.media(), stream.encoding_name()))
                .collect();
            format!("нет видеопотока H.264/H.265 (есть: {})", found.join(", "))
        })?;
    tokio::time::timeout(
        CONNECT_TIMEOUT,
        session.setup(index, SetupOptions::default().frame_format(FrameFormat::MP4)),
    )
    .await
    .map_err(|_| "камера не ответила на SETUP".to_string())?
    .map_err(|error| error.to_string())?;
    let mut demuxed = tokio::time::timeout(CONNECT_TIMEOUT, session.play(PlayOptions::default()))
        .await
        .map_err(|_| "камера не ответила на PLAY".to_string())?
        .map_err(|error| error.to_string())?
        .demuxed()
        .map_err(|error| error.to_string())?;
    let clock_rate = demuxed.streams()[index].clock_rate_hz();

    let mut timing = FrameTiming::new();
    let mut configured = false;
    let mut playing = false;
    loop {
        let item = tokio::time::timeout(STALL_TIMEOUT, demuxed.next())
            .await
            .map_err(|_| format!("нет кадров {} с", STALL_TIMEOUT.as_secs()))?;
        let frame = match item {
            None => return Ok(()),
            Some(Err(error)) => return Err(error.to_string()),
            Some(Ok(CodecItem::VideoFrame(frame))) => frame,
            Some(Ok(_)) => continue,
        };
        if !configured || frame.has_new_parameters() {
            match demuxed.streams()[frame.stream_id()].parameters() {
                Some(ParametersRef::Video(params)) => {
                    send(channel, config_message(params))?;
                    configured = true;
                }
                _ => continue,
            }
        }
        // The decoder can start only from a key frame; everything before it is undecodable.
        if !playing {
            if !frame.is_random_access_point() {
                continue;
            }
            send_state(channel, STATE_PLAYING, "")?;
            eprintln!("[video] {url}: поток идёт");
            playing = true;
        }
        let key = frame.is_random_access_point();
        let timestamp_us = (frame.timestamp().elapsed_secs() * 1_000_000.0) as i64;
        let sending = std::time::Instant::now();
        send(channel, frame_message(key, timestamp_us, frame.data()))?;
        timing.frame(url, frame.data().len(), sending.elapsed());

        context.sync_recorder(recorder, clock_rate);
        if let (Some(active), Some(ParametersRef::Video(params))) = (recorder.as_mut(), demuxed.streams()[frame.stream_id()].parameters()) {
            if let Some(event) = active.push(params, key, frame.timestamp().elapsed(), frame.data()) {
                context.emit(event);
            }
        }
    }
}

async fn run(context: StreamContext, channel: Channel<InvokeResponseBody>) {
    let url = context.url.clone();
    loop {
        if send_state(&channel, STATE_CONNECTING, "").is_err() {
            return;
        }
        eprintln!("[video] {url}: подключение");
        // A recording spans one RTSP session: timestamps restart with the next one, so does the file.
        let mut recorder = None;
        let result = play(&context, &channel, &mut recorder).await;
        if let Some(active) = recorder.take() {
            context.emit(active.finish());
        }
        let message = match result {
            Ok(()) => "камера завершила поток".to_string(),
            Err(error) => error,
        };
        // The URL never carries credentials, so it is safe to log.
        eprintln!("[video] {url}: {message}");
        // Retrying a rejected password would lock the camera account (Uniview locks after a few
        // failures): stop here; saving a new password or «Подключить» restarts the stream.
        if is_auth_failure(&message) {
            let _ = send_state(&channel, STATE_ERROR, AUTH_FAILED);
            return;
        }
        if send_state(&channel, STATE_ERROR, &explain(&message)).is_err() {
            return;
        }
        tokio::time::sleep(RETRY_DELAY).await;
    }
}

#[tauri::command]
pub async fn camera_stream_start(
    app: AppHandle,
    streams: State<'_, Arc<Streams>>,
    camera_id: String,
    ip: String,
    port: u16,
    username: String,
    path: String,
    token: u64,
    channel: Channel<InvokeResponseBody>,
) -> Result<(), String> {
    validate_camera(&camera_id)?;
    let url = stream_url(&ip, port, &path)?;
    if username.len() > 64 {
        return Err("Имя пользователя длиннее 64 символов".into());
    }
    let key = camera_id.clone();
    let password = crate::run_blocking(move || match crate::keyring_entry(&key)?.get_password() {
        Ok(password) => Ok(password),
        Err(keyring::Error::NoEntry) => Ok(String::new()),
        Err(error) => Err(error.to_string()),
    })
    .await?;
    let creds = (!username.is_empty()).then_some(Credentials { username, password });
    let context = StreamContext { camera_id: camera_id.clone(), url, creds, recording: Arc::clone(&streams.recording), app };
    let task = tauri::async_runtime::spawn(run(context, channel));
    streams.start(&camera_id, token, task);
    Ok(())
}

/// Starts recording the selected cameras; each running stream opens its file at its next key frame.
/// Without a chosen directory it records into «Videos/MKIS100TEST»; returns the directory used.
#[tauri::command]
pub async fn recording_start(app: AppHandle, streams: State<'_, Arc<Streams>>, mut settings: RecordSettings) -> Result<String, String> {
    settings.directory = crate::record::resolve_directory(&app, &settings.directory)?;
    let checked = settings.clone();
    crate::run_blocking(move || checked.validate()).await?;
    let directory = settings.directory.clone();
    *crate::lock(&streams.recording) = Some(settings);
    Ok(directory)
}

/// Stops recording; each stream closes its file on its next frame.
#[tauri::command]
pub fn recording_stop(streams: State<'_, Arc<Streams>>) {
    *crate::lock(&streams.recording) = None;
}

#[tauri::command]
pub fn camera_stream_stop(streams: State<'_, Arc<Streams>>, camera_id: String, token: u64) -> Result<(), String> {
    validate_camera(&camera_id)?;
    streams.stop(&camera_id, token);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stream_url_never_carries_credentials() {
        let url = stream_url("192.168.1.68", 554, "/media/video1").unwrap();
        assert_eq!(url.as_str(), "rtsp://192.168.1.68:554/media/video1");
        assert!(stream_url("192.168.1.68", 554, "/x@evil").is_err());
        assert!(stream_url("192.168.1.68", 554, "media/video1").is_err());
        assert!(stream_url("192.168.1.68", 554, "/a b").is_err());
        assert!(stream_url("192.168.1.68", 554, "/live?channel=0&subtype=0").is_ok());
    }

    #[test]
    fn a_rejected_path_is_named_in_the_error() {
        assert!(explain("RTSP 404 Not Found").contains("путь потока"));
        assert_eq!(explain("камера не ответила на DESCRIBE"), "камера не ответила на DESCRIBE");
    }

    #[test]
    fn frame_message_layout() {
        let bytes = frame_message(true, -2, &[9, 8]);
        assert_eq!(bytes[0], MSG_FRAME);
        assert_eq!(bytes[1], 1);
        assert_eq!(i64::from_le_bytes(bytes[2..10].try_into().unwrap()), -2);
        assert_eq!(&bytes[10..], &[9, 8]);
    }
}

/// Raw RTP dump of a real camera (`MKIS_RTP=camera2@rtsp://192.168.1.99:554/av0_0`): finds payloads
/// with `00 00 00 xx` inside, which retina rejects. The password comes from the keychain, never printed.
#[cfg(test)]
mod rtp_probe {
    use super::*;

    #[test]
    #[ignore]
    fn dump_raw_rtp() {
        let spec = std::env::var("MKIS_RTP").expect("MKIS_RTP=camera2@rtsp://ip:554/path");
        let (id, url) = spec.split_once('@').unwrap();
        let url = Url::parse(url).unwrap();
        let password = crate::keyring_entry(id).unwrap().get_password().unwrap();
        tauri::async_runtime::block_on(async move {
            let options = SessionOptions::default()
                .creds(Some(Credentials { username: "admin".into(), password }))
                .session_group(Arc::new(SessionGroup::default()));
            let mut session = Session::describe(url, options).await.unwrap();
            for (index, stream) in session.streams().iter().enumerate() {
                println!("stream {index}: {} {} {:?}", stream.media(), stream.encoding_name(), stream.parameters().map(|_| "params"));
            }
            let index = session.streams().iter().position(|stream| stream.media() == "video").unwrap();
            session.setup(index, SetupOptions::default()).await.unwrap();
            let mut playing = session.play(PlayOptions::default()).await.unwrap();
            let mut types: HashMap<u8, usize> = HashMap::new();
            let (mut packets, mut bad) = (0, 0);
            // Tail of the previous FU-A fragment, to catch sequences split across packets.
            let mut tail: Vec<u8> = Vec::new();
            let mut zero_tails = 0;
            let started = std::time::Instant::now();
            while started.elapsed() < Duration::from_secs(60) {
                let Some(item) = playing.next().await else { break };
                let retina::client::PacketItem::Rtp(packet) = item.unwrap() else { continue };
                packets += 1;
                let payload = packet.payload();
                let nal_type = payload[0] & 0x1f;
                *types.entry(nal_type).or_default() += 1;
                // Body to scan: skip the NAL header (single NAL) or NAL + FU header (FU-A).
                let body = if nal_type == 28 { &payload[2..] } else { &payload[1..] };
                if nal_type == 28 {
                    let start = payload[1] >> 7 == 1;
                    if start {
                        tail.clear();
                    }
                    let mut joined = tail.clone();
                    joined.extend_from_slice(&body[..body.len().min(4)]);
                    if let Some(at) = joined.windows(4).position(|w| w[0] == 0 && w[1] == 0 && w[2] == 0 && w[3] > 1) {
                        bad += 1;
                        if bad <= 12 {
                            println!(
                                "СТЫК seq {} len {} FU hdr {:02x}: хвост {:02x?} + начало {:02x?} (at {at})",
                                packet.sequence_number(), payload.len(), payload[1], tail, &body[..body.len().min(6)]
                            );
                        }
                    }
                    if body.ends_with(&[0]) {
                        zero_tails += 1;
                    }
                    tail = body[body.len().saturating_sub(3)..].to_vec();
                }
                if let Some(at) = body.windows(4).position(|w| w[0] == 0 && w[1] == 0 && w[2] == 0 && w[3] > 1) {
                    bad += 1;
                    if bad <= 12 {
                        let fu = if nal_type == 28 { format!(" FU hdr {:02x} (start {} end {} type {})", payload[1], payload[1] >> 7, (payload[1] >> 6) & 1, payload[1] & 0x1f) } else { String::new() };
                        let from = at.saturating_sub(8);
                        let to = (at + 24).min(body.len());
                        println!(
                            "seq {} mark {} len {} nal {}{} | at {}: {:02x?}",
                            packet.sequence_number(), packet.mark(), payload.len(), nal_type, fu, at, &body[from..to]
                        );
                        println!("   head: {:02x?}  tail: {:02x?}", &payload[..payload.len().min(12)], &payload[payload.len().saturating_sub(8)..]);
                    }
                }
            }
            println!("packets {packets}, with 00 00 00 xx: {bad}, FU-A fragments ending in 00: {zero_tails}, NAL types: {types:?}");
        });
    }

    /// The same camera through the (patched) depacketizer: frames and key frames over 90 s, and the
    /// first error if the session still fails.
    #[test]
    #[ignore]
    fn depacketize_real_stream() {
        let spec = std::env::var("MKIS_RTP").expect("MKIS_RTP=camera2@rtsp://ip:554/path");
        let (id, url) = spec.split_once('@').unwrap();
        let url = Url::parse(url).unwrap();
        let password = crate::keyring_entry(id).unwrap().get_password().unwrap();
        tauri::async_runtime::block_on(async move {
            let options = SessionOptions::default()
                .creds(Some(Credentials { username: "admin".into(), password }))
                .session_group(Arc::new(SessionGroup::default()));
            let mut session = Session::describe(url, options).await.unwrap();
            let index = session.streams().iter().position(|stream| stream.media() == "video").unwrap();
            session.setup(index, SetupOptions::default().frame_format(FrameFormat::MP4)).await.unwrap();
            let mut demuxed = session.play(PlayOptions::default()).await.unwrap().demuxed().unwrap();
            let (mut frames, mut keys) = (0, 0);
            let started = std::time::Instant::now();
            while started.elapsed() < Duration::from_secs(90) {
                match demuxed.next().await {
                    Some(Ok(CodecItem::VideoFrame(frame))) => {
                        frames += 1;
                        keys += usize::from(frame.is_random_access_point());
                    }
                    Some(Ok(_)) => {}
                    Some(Err(error)) => {
                        println!("ошибка после {frames} кадров: {error}");
                        break;
                    }
                    None => break,
                }
            }
            println!("кадров {frames}, ключевых {keys} за {:.0} с", started.elapsed().as_secs_f64());
        });
    }
}
