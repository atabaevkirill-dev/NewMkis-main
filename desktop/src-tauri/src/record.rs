//! Recording: the encoded access units already received for display are written unchanged into
//! fragmented MP4 (no transcoding, no FFmpeg). Every group of pictures becomes one `moof`+`mdat`
//! fragment, so a crash or power loss costs at most the last fragment; the file stays playable.

use retina::codec::VideoParameters;
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::{
    fs::{self, File},
    io::{BufWriter, Write},
    path::{Path, PathBuf},
    time::{Duration, Instant},
};

/// A fragment is closed at the next key frame, or after this long without one.
const MAX_FRAGMENT_SECONDS: i64 = 2;

#[derive(Clone, Debug, PartialEq, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RecordSettings {
    pub camera1: bool,
    pub camera2: bool,
    pub directory: String,
    pub segment_minutes: u32,
    pub include_metadata: bool,
    /// Full installation name; starts every file name.
    pub title: String,
    pub camera1_name: String,
    pub camera2_name: String,
    /// Operator's local time offset, so file names read in local time.
    pub utc_offset_minutes: i32,
}

/// Keeps a name usable as a file name on Windows, macOS and Linux (Cyrillic stays).
pub(crate) fn file_part(text: &str, fallback: &str) -> String {
    let cleaned: String = text
        .chars()
        .map(|c| if c.is_control() || matches!(c, '<' | '>' | ':' | '"' | '/' | '\\' | '|' | '?' | '*' | '·') { ' ' } else { c })
        .collect();
    let joined = cleaned.split_whitespace().collect::<Vec<_>>().join(" ");
    let trimmed: String = joined.trim_matches(['.', ' ']).chars().take(80).collect();
    let trimmed = trimmed.trim_end_matches(['.', ' ']).to_string();
    if trimmed.is_empty() { fallback.to_string() } else { trimmed }
}

/// The chosen directory, or «Videos/MKIS100TEST» (created) when none was chosen.
pub(crate) fn resolve_directory(app: &tauri::AppHandle, chosen: &str) -> Result<String, String> {
    use tauri::Manager;
    if !chosen.trim().is_empty() {
        return Ok(chosen.to_string());
    }
    let directory = app
        .path()
        .video_dir()
        .map_err(|error| format!("Каталог «Видео» не найден: {error}"))?
        .join("MKIS100TEST");
    fs::create_dir_all(&directory).map_err(|error| format!("{}: {error}", directory.display()))?;
    Ok(directory.display().to_string())
}

/// `2026-09-22_12-55-03` in the operator's local time.
pub(crate) fn local_stamp(unix: i64, utc_offset_minutes: i32) -> String {
    let iso = crate::onvif::iso8601(unix + i64::from(utc_offset_minutes) * 60);
    iso.trim_end_matches('Z').replace('T', "_").replace(':', "-")
}

impl RecordSettings {
    pub fn camera_name(&self, camera_id: &str) -> String {
        let (name, fallback) = if camera_id == "camera1" { (&self.camera1_name, "CAM 01") } else { (&self.camera2_name, "CAM 02") };
        file_part(name, fallback)
    }

    pub fn includes(&self, camera_id: &str) -> bool {
        match camera_id {
            "camera1" => self.camera1,
            "camera2" => self.camera2,
            _ => false,
        }
    }

    pub fn validate(&self) -> Result<(), String> {
        if !self.camera1 && !self.camera2 {
            return Err("Не выбрана ни одна камера для записи".into());
        }
        if !(1..=240).contains(&self.segment_minutes) {
            return Err("Длина сегмента — от 1 до 240 минут".into());
        }
        let directory = Path::new(&self.directory);
        if self.directory.trim().is_empty() || !directory.is_absolute() {
            return Err("Выберите каталог записи".into());
        }
        if !directory.is_dir() {
            return Err(format!("Каталог записи не найден: {}", self.directory));
        }
        // Prove the directory is writable before the operator believes recording has started.
        let probe = directory.join(".mkis100test-write-check");
        File::create(&probe)
            .and_then(|mut file| file.write_all(b"ok"))
            .map_err(|error| format!("Нет доступа на запись в {}: {error}", self.directory))?;
        let _ = fs::remove_file(probe);
        Ok(())
    }
}

/// Where the stream comes from; stored in the metadata sidecar. Never contains credentials.
#[derive(Clone)]
pub struct Source {
    pub camera_id: String,
    pub url: String,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RecordingEvent {
    pub camera_id: String,
    pub state: &'static str,
    pub file: Option<String>,
    pub bytes: u64,
    pub message: Option<String>,
}

// ---------------------------------------------------------------- MP4 boxes

pub(crate) fn mp4_box(out: &mut Vec<u8>, kind: &[u8; 4], body: impl FnOnce(&mut Vec<u8>)) {
    let start = out.len();
    out.extend_from_slice(&[0, 0, 0, 0]);
    out.extend_from_slice(kind);
    body(out);
    let size = (out.len() - start) as u32;
    out[start..start + 4].copy_from_slice(&size.to_be_bytes());
}

pub(crate) fn full_box(out: &mut Vec<u8>, kind: &[u8; 4], version: u8, flags: u32, body: impl FnOnce(&mut Vec<u8>)) {
    mp4_box(out, kind, |out| {
        out.extend_from_slice(&((u32::from(version) << 24) | flags).to_be_bytes());
        body(out);
    });
}

const MATRIX: [u32; 9] = [0x0001_0000, 0, 0, 0, 0x0001_0000, 0, 0, 0, 0x4000_0000];

pub(crate) fn put_matrix(out: &mut Vec<u8>) {
    for value in MATRIX {
        out.extend_from_slice(&value.to_be_bytes());
    }
}

/// `ftyp` + `moov` for one video track; samples follow in fragments.
pub(crate) fn init_segment(sample_entry: &[u8], width: u32, height: u32, timescale: u32) -> Vec<u8> {
    let mut out = Vec::with_capacity(1024 + sample_entry.len());
    mp4_box(&mut out, b"ftyp", |out| {
        out.extend_from_slice(b"isom");
        out.extend_from_slice(&0x200_u32.to_be_bytes());
        for brand in [b"isom", b"iso6", b"mp41"] {
            out.extend_from_slice(brand);
        }
    });
    mp4_box(&mut out, b"moov", |out| {
        full_box(out, b"mvhd", 0, 0, |out| {
            out.extend_from_slice(&[0; 8]); // creation, modification
            out.extend_from_slice(&1000_u32.to_be_bytes());
            out.extend_from_slice(&0_u32.to_be_bytes()); // duration: unknown, fragments carry it
            out.extend_from_slice(&0x0001_0000_u32.to_be_bytes()); // rate 1.0
            out.extend_from_slice(&0x0100_u16.to_be_bytes()); // volume 1.0
            out.extend_from_slice(&[0; 10]);
            put_matrix(out);
            out.extend_from_slice(&[0; 24]);
            out.extend_from_slice(&2_u32.to_be_bytes()); // next track id
        });
        mp4_box(out, b"trak", |out| {
            full_box(out, b"tkhd", 0, 3, |out| {
                out.extend_from_slice(&[0; 8]);
                out.extend_from_slice(&1_u32.to_be_bytes()); // track id
                out.extend_from_slice(&[0; 4]);
                out.extend_from_slice(&0_u32.to_be_bytes()); // duration
                out.extend_from_slice(&[0; 8]);
                out.extend_from_slice(&[0; 4]); // layer, alternate group
                out.extend_from_slice(&[0; 4]); // volume, reserved
                put_matrix(out);
                out.extend_from_slice(&(width << 16).to_be_bytes());
                out.extend_from_slice(&(height << 16).to_be_bytes());
            });
            mp4_box(out, b"mdia", |out| {
                full_box(out, b"mdhd", 0, 0, |out| {
                    out.extend_from_slice(&[0; 8]);
                    out.extend_from_slice(&timescale.to_be_bytes());
                    out.extend_from_slice(&0_u32.to_be_bytes());
                    out.extend_from_slice(&0x55c4_u16.to_be_bytes()); // language "und"
                    out.extend_from_slice(&[0; 2]);
                });
                full_box(out, b"hdlr", 0, 0, |out| {
                    out.extend_from_slice(&[0; 4]);
                    out.extend_from_slice(b"vide");
                    out.extend_from_slice(&[0; 12]);
                    out.extend_from_slice(b"MKIS100TEST video\0");
                });
                mp4_box(out, b"minf", |out| {
                    full_box(out, b"vmhd", 0, 1, |out| out.extend_from_slice(&[0; 8]));
                    mp4_box(out, b"dinf", |out| {
                        full_box(out, b"dref", 0, 0, |out| {
                            out.extend_from_slice(&1_u32.to_be_bytes());
                            full_box(out, b"url ", 0, 1, |_| {});
                        });
                    });
                    mp4_box(out, b"stbl", |out| {
                        full_box(out, b"stsd", 0, 0, |out| {
                            out.extend_from_slice(&1_u32.to_be_bytes());
                            out.extend_from_slice(sample_entry);
                        });
                        full_box(out, b"stts", 0, 0, |out| out.extend_from_slice(&[0; 4]));
                        full_box(out, b"stsc", 0, 0, |out| out.extend_from_slice(&[0; 4]));
                        full_box(out, b"stsz", 0, 0, |out| out.extend_from_slice(&[0; 8]));
                        full_box(out, b"stco", 0, 0, |out| out.extend_from_slice(&[0; 4]));
                    });
                });
            });
        });
        mp4_box(out, b"mvex", |out| {
            full_box(out, b"trex", 0, 0, |out| {
                out.extend_from_slice(&1_u32.to_be_bytes()); // track id
                out.extend_from_slice(&1_u32.to_be_bytes()); // sample description index
                out.extend_from_slice(&[0; 12]);
            });
        });
    });
    out
}

pub(crate) struct Sample {
    pub timestamp: i64,
    pub key: bool,
    pub data: Vec<u8>,
}

const SAMPLE_KEY: u32 = 0x0200_0000; // depends on no other sample
const SAMPLE_DELTA: u32 = 0x0101_0000; // depends on others, not a sync sample

/// One `moof` + `mdat` for `samples`; `next_timestamp` gives the duration of the last one.
pub(crate) fn fragment(sequence: u32, decode_time: u64, samples: &[Sample], next_timestamp: i64) -> Vec<u8> {
    let payload: usize = samples.iter().map(|sample| sample.data.len()).sum();
    let mut out = Vec::with_capacity(payload + 128 + samples.len() * 12);
    let mut data_offset_at = 0;
    mp4_box(&mut out, b"moof", |out| {
        full_box(out, b"mfhd", 0, 0, |out| out.extend_from_slice(&sequence.to_be_bytes()));
        mp4_box(out, b"traf", |out| {
            full_box(out, b"tfhd", 0, 0x02_0000, |out| out.extend_from_slice(&1_u32.to_be_bytes()));
            full_box(out, b"tfdt", 1, 0, |out| out.extend_from_slice(&decode_time.to_be_bytes()));
            // data-offset, sample-duration, sample-size, sample-flags present
            full_box(out, b"trun", 0, 0x0701, |out| {
                out.extend_from_slice(&(samples.len() as u32).to_be_bytes());
                data_offset_at = out.len();
                out.extend_from_slice(&[0; 4]);
                for (index, sample) in samples.iter().enumerate() {
                    let next = samples.get(index + 1).map_or(next_timestamp, |next| next.timestamp);
                    let duration = u32::try_from(next - sample.timestamp).unwrap_or(0).max(1);
                    out.extend_from_slice(&duration.to_be_bytes());
                    out.extend_from_slice(&(sample.data.len() as u32).to_be_bytes());
                    out.extend_from_slice(&(if sample.key { SAMPLE_KEY } else { SAMPLE_DELTA }).to_be_bytes());
                }
            });
        });
    });
    // With default-base-is-moof the data offset counts from the start of `moof`.
    let data_offset = (out.len() + 8) as u32;
    out[data_offset_at..data_offset_at + 4].copy_from_slice(&data_offset.to_be_bytes());
    mp4_box(&mut out, b"mdat", |out| {
        for sample in samples {
            out.extend_from_slice(&sample.data);
        }
    });
    out
}

// ---------------------------------------------------------------- files and segments

struct Segment {
    path: PathBuf,
    file: BufWriter<File>,
    opened: Instant,
    started_utc: String,
    bytes: u64,
    sequence: u32,
    first_timestamp: i64,
    gop: Vec<Sample>,
    last_duration: i64,
}

impl Segment {
    fn flush_gop(&mut self, next_timestamp: i64) -> std::io::Result<()> {
        if self.gop.is_empty() {
            return Ok(());
        }
        self.sequence += 1;
        let decode_time = u64::try_from(self.gop[0].timestamp - self.first_timestamp).unwrap_or(0);
        let bytes = fragment(self.sequence, decode_time, &self.gop, next_timestamp);
        if let Some(last) = self.gop.last() {
            self.last_duration = (next_timestamp - last.timestamp).max(1);
        }
        self.gop.clear();
        self.file.write_all(&bytes)?;
        self.file.flush()?;
        self.bytes += bytes.len() as u64;
        Ok(())
    }

    fn finish(mut self) -> std::io::Result<(PathBuf, u64)> {
        let next = self.gop.last().map_or(0, |last| last.timestamp + self.last_duration);
        self.flush_gop(next)?;
        self.file.get_ref().sync_all()?;
        Ok((self.path, self.bytes))
    }
}

/// Records one camera for as long as its settings stay the same.
pub struct CameraRecorder {
    pub settings: RecordSettings,
    source: Source,
    segment: Option<Segment>,
    sample_entry: Option<(Vec<u8>, VideoParameters)>,
    clock_rate: u32,
    last_report: Instant,
    failed: bool,
}

impl CameraRecorder {
    pub fn new(settings: RecordSettings, source: Source, clock_rate: u32) -> Self {
        Self { settings, source, segment: None, sample_entry: None, clock_rate, last_report: Instant::now(), failed: false }
    }

    fn event(&self, state: &'static str, message: Option<String>) -> RecordingEvent {
        RecordingEvent {
            camera_id: self.source.camera_id.clone(),
            state,
            file: self.segment.as_ref().map(|segment| segment.path.display().to_string()),
            bytes: self.segment.as_ref().map_or(0, |segment| segment.bytes),
            message,
        }
    }

    fn write_metadata(&self, video: &Path, started_utc: &str, ended_utc: Option<String>) {
        if !self.settings.include_metadata {
            return;
        }
        let Some((_, params)) = &self.sample_entry else { return };
        let (width, height) = params.pixel_dimensions();
        let metadata = json!({
            "software": format!("MKIS100TEST {}", env!("CARGO_PKG_VERSION")),
            "product": self.settings.title,
            "camera": self.source.camera_id,
            "cameraName": self.settings.camera_name(&self.source.camera_id),
            "source": self.source.url,
            "codec": params.rfc6381_codec(),
            "width": width,
            "height": height,
            "startedUtc": started_utc,
            "endedUtc": ended_utc,
            "segmentMinutes": self.settings.segment_minutes,
            "note": "Телеметрия поворотки и дальномера в метаданные пока не пишется.",
        });
        let path = video.with_extension("json");
        if let Err(error) = fs::write(&path, serde_json::to_vec_pretty(&metadata).unwrap_or_default()) {
            eprintln!("[record] {}: метаданные не записаны: {error}", path.display());
        }
    }

    fn open_segment(&mut self, timestamp: i64) -> std::io::Result<()> {
        let Some((entry, params)) = &self.sample_entry else { return Ok(()) };
        let now = crate::onvif::now_unix();
        let base = format!(
            "{}_{}_{}",
            file_part(&self.settings.title, "MKIS100TEST"),
            self.settings.camera_name(&self.source.camera_id),
            local_stamp(now, self.settings.utc_offset_minutes)
        );
        let directory = Path::new(&self.settings.directory);
        let mut path = directory.join(format!("{base}.mp4"));
        let mut attempt = 1;
        while path.exists() {
            attempt += 1;
            path = directory.join(format!("{base}_{attempt}.mp4"));
        }
        let (width, height) = params.pixel_dimensions();
        let init = init_segment(entry, width, height, self.clock_rate);
        let mut file = BufWriter::new(File::create(&path)?);
        file.write_all(&init)?;
        file.flush()?;
        let segment = Segment {
            path,
            file,
            opened: Instant::now(),
            started_utc: crate::onvif::iso8601(now),
            bytes: init.len() as u64,
            sequence: 0,
            first_timestamp: timestamp,
            gop: Vec::new(),
            last_duration: i64::from(self.clock_rate / 25),
        };
        self.write_metadata(&segment.path, &segment.started_utc, None);
        self.segment = Some(segment);
        Ok(())
    }

    fn close_segment(&mut self) -> std::io::Result<Option<(PathBuf, u64)>> {
        let Some(segment) = self.segment.take() else { return Ok(None) };
        let started = segment.started_utc.clone();
        let result = segment.finish()?;
        // Fragmented while recording (crash-safe); indexed once closed so standard players can seek.
        crate::mp4fix::defragment_later(result.0.clone());
        self.write_metadata(&result.0, &started, Some(crate::onvif::iso8601(crate::onvif::now_unix())));
        Ok(Some(result))
    }

    /// Feeds one access unit. Returns an event for the UI when something changed or once a second.
    pub fn push(&mut self, params: &VideoParameters, key: bool, timestamp: i64, data: &[u8]) -> Option<RecordingEvent> {
        if self.failed {
            return None;
        }
        match self.try_push(params, key, timestamp, data) {
            Ok(changed) => {
                if changed || self.last_report.elapsed() >= Duration::from_secs(1) {
                    self.last_report = Instant::now();
                    Some(self.event("recording", None))
                } else {
                    None
                }
            }
            Err(error) => {
                self.failed = true;
                let event = self.event("error", Some(format!("запись остановлена: {error}")));
                let _ = self.close_segment();
                Some(event)
            }
        }
    }

    fn try_push(&mut self, params: &VideoParameters, key: bool, timestamp: i64, data: &[u8]) -> std::io::Result<bool> {
        let mut changed = false;
        let params_changed = self.sample_entry.as_ref().is_none_or(|(_, current)| current != params);
        let segment_full = self.segment.as_ref().is_some_and(|segment| {
            segment.opened.elapsed() >= Duration::from_secs(u64::from(self.settings.segment_minutes) * 60)
        });
        if key && (params_changed || segment_full || self.segment.is_none()) {
            // New parameters need a new init segment, so they start a new file too.
            if let Some(segment) = self.segment.as_mut() {
                segment.flush_gop(timestamp)?;
            }
            self.close_segment()?;
            if params_changed {
                let entry = params
                    .mp4_sample_entry()
                    .build()
                    .map_err(|error| std::io::Error::other(error.to_string()))?;
                self.sample_entry = Some((entry, params.clone()));
            }
            self.open_segment(timestamp)?;
            changed = true;
        }
        let Some(segment) = self.segment.as_mut() else { return Ok(changed) };
        let long = segment
            .gop
            .first()
            .is_some_and(|first| timestamp - first.timestamp >= MAX_FRAGMENT_SECONDS * i64::from(self.clock_rate));
        if key || long {
            segment.flush_gop(timestamp)?;
        }
        segment.gop.push(Sample { timestamp, key, data: data.to_vec() });
        Ok(changed)
    }

    /// Closes the current file; returns the final event for the UI.
    pub fn finish(mut self) -> RecordingEvent {
        let file = self.segment.as_ref().map(|segment| segment.path.display().to_string());
        match self.close_segment() {
            Ok(result) => RecordingEvent {
                camera_id: self.source.camera_id.clone(),
                state: "stopped",
                file: file.or_else(|| result.as_ref().map(|(path, _)| path.display().to_string())),
                bytes: result.map_or(0, |(_, bytes)| bytes),
                message: None,
            },
            Err(error) => RecordingEvent {
                camera_id: self.source.camera_id.clone(),
                state: "error",
                file,
                bytes: 0,
                message: Some(format!("файл не закрыт: {error}")),
            },
        }
    }
}

impl Drop for CameraRecorder {
    /// An aborted stream task (camera restarted or removed) still closes its file properly.
    fn drop(&mut self) {
        if let Err(error) = self.close_segment() {
            eprintln!("[record] {}: файл не закрыт: {error}", self.source.camera_id);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn read_u32(bytes: &[u8], at: usize) -> u32 {
        u32::from_be_bytes(bytes[at..at + 4].try_into().unwrap())
    }

    /// Walks top-level boxes and returns their types, checking that sizes tile the buffer exactly.
    fn box_types(bytes: &[u8]) -> Vec<String> {
        let mut types = Vec::new();
        let mut at = 0;
        while at < bytes.len() {
            let size = read_u32(bytes, at) as usize;
            assert!(size >= 8 && at + size <= bytes.len(), "bad box size at {at}");
            types.push(String::from_utf8_lossy(&bytes[at + 4..at + 8]).to_string());
            at += size;
        }
        types
    }

    #[test]
    fn init_segment_is_well_formed() {
        let entry = [0, 0, 0, 8, b'a', b'v', b'c', b'1'];
        let init = init_segment(&entry, 1920, 1080, 90_000);
        assert_eq!(box_types(&init), ["ftyp", "moov"]);
    }

    #[test]
    fn fragment_points_at_its_samples() {
        let samples = vec![
            Sample { timestamp: 1000, key: true, data: vec![1, 2, 3] },
            Sample { timestamp: 4600, key: false, data: vec![4, 5] },
        ];
        let bytes = fragment(1, 0, &samples, 8200);
        assert_eq!(box_types(&bytes), ["moof", "mdat"]);
        let moof_size = read_u32(&bytes, 0) as usize;
        // trun: size, 'trun', version/flags, sample_count, data_offset, then 3 u32 per sample.
        let trun = bytes.windows(4).position(|window| window == b"trun").unwrap() - 4;
        assert_eq!(read_u32(&bytes, trun + 12), 2);
        let data_offset = read_u32(&bytes, trun + 16) as usize;
        assert_eq!(&bytes[data_offset..data_offset + 5], &[1, 2, 3, 4, 5]);
        assert_eq!(data_offset, moof_size + 8);
        // Durations come from consecutive timestamps; the last one from `next_timestamp`.
        assert_eq!(read_u32(&bytes, trun + 20), 3600);
        assert_eq!(read_u32(&bytes, trun + 32), 3600);
        assert_eq!(read_u32(&bytes, trun + 28), SAMPLE_KEY);
        assert_eq!(read_u32(&bytes, trun + 40), SAMPLE_DELTA);
    }

    #[test]
    fn file_names_use_product_camera_and_local_time() {
        assert_eq!(file_part("Изделие «А-1»: стенд/2", "X"), "Изделие «А-1» стенд 2");
        assert_eq!(file_part("CAM 01 · OPTICAL", "X"), "CAM 01 OPTICAL");
        assert_eq!(file_part("  ..  ", "MKIS100TEST"), "MKIS100TEST");
        assert_eq!(local_stamp(0, 180), "1970-01-01_03-00-00");
    }

    #[test]
    fn settings_require_camera_and_directory() {
        let mut settings = RecordSettings {
            camera1: false,
            camera2: false,
            directory: std::env::temp_dir().display().to_string(),
            segment_minutes: 30,
            include_metadata: true,
            title: String::new(),
            camera1_name: String::new(),
            camera2_name: String::new(),
            utc_offset_minutes: 180,
        };
        assert!(settings.validate().is_err());
        settings.camera1 = true;
        assert!(settings.validate().is_ok());
        settings.directory = "relative/dir".into();
        assert!(settings.validate().is_err());
    }
}
