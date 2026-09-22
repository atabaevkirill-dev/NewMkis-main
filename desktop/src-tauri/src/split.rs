//! Split recording: the webview composes both cameras side by side and encodes the result with
//! MediaRecorder; the encoded chunks arrive here and are appended to the file in order.
//! (The pass-through recorder cannot do this: a split picture has to be re-encoded.)

use crate::record::{file_part, local_stamp};
use serde::{Deserialize, Serialize};
use std::{
    collections::HashMap,
    fs::File,
    io::{BufWriter, Write},
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc, Mutex,
    },
};
use tauri::{ipc::InvokeBody, ipc::Request, AppHandle, State};

const MAX_CHUNK_BYTES: usize = 64 * 1024 * 1024;

#[derive(Default)]
pub struct SplitFiles {
    next: AtomicU64,
    open: Mutex<HashMap<u64, (PathBuf, BufWriter<File>, u64)>>,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SplitOpen {
    directory: String,
    title: String,
    camera1_name: String,
    camera2_name: String,
    utc_offset_minutes: i32,
    /// `mp4` or `webm`, whichever the webview's encoder produces.
    extension: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SplitOpened {
    id: u64,
    path: String,
    directory: String,
}

#[tauri::command]
pub async fn split_open(app: AppHandle, files: State<'_, Arc<SplitFiles>>, request: SplitOpen) -> Result<SplitOpened, String> {
    if !matches!(request.extension.as_str(), "mp4" | "webm") {
        return Err("Неизвестный формат сплит-записи".into());
    }
    let directory = crate::record::resolve_directory(&app, &request.directory)?;
    let base = format!(
        "{}_{}+{}_{}",
        file_part(&request.title, "MKIS100TEST"),
        file_part(&request.camera1_name, "CAM 01"),
        file_part(&request.camera2_name, "CAM 02"),
        local_stamp(crate::onvif::now_unix(), request.utc_offset_minutes)
    );
    let folder = Path::new(&directory);
    let mut path = folder.join(format!("{base}.{}", request.extension));
    let mut attempt = 1;
    while path.exists() {
        attempt += 1;
        path = folder.join(format!("{base}_{attempt}.{}", request.extension));
    }
    let file = File::create(&path).map_err(|error| format!("{}: {error}", path.display()))?;
    let id = files.next.fetch_add(1, Ordering::SeqCst) + 1;
    let shown = path.display().to_string();
    crate::lock(&files.open).insert(id, (path, BufWriter::new(file), 0));
    Ok(SplitOpened { id, path: shown, directory })
}

/// Appends one encoded chunk (raw request body); the file id travels in the `x-split-id` header.
#[tauri::command]
pub fn split_chunk(files: State<'_, Arc<SplitFiles>>, request: Request<'_>) -> Result<u64, String> {
    let id = request
        .headers()
        .get("x-split-id")
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.parse::<u64>().ok())
        .ok_or("нет идентификатора сплит-файла")?;
    let InvokeBody::Raw(bytes) = request.body() else { return Err("ожидались двоичные данные".into()) };
    if bytes.len() > MAX_CHUNK_BYTES {
        return Err("слишком большой фрагмент записи".into());
    }
    let mut open = crate::lock(&files.open);
    let (path, writer, total) = open.get_mut(&id).ok_or("сплит-файл уже закрыт")?;
    writer.write_all(bytes).map_err(|error| format!("{}: {error}", path.display()))?;
    writer.flush().map_err(|error| format!("{}: {error}", path.display()))?;
    *total += bytes.len() as u64;
    Ok(*total)
}

#[tauri::command]
pub fn split_close(files: State<'_, Arc<SplitFiles>>, id: u64) -> Result<u64, String> {
    let Some((path, writer, total)) = crate::lock(&files.open).remove(&id) else { return Ok(0) };
    let file = writer.into_inner().map_err(|error| format!("{}: {error}", path.display()))?;
    file.sync_all().map_err(|error| format!("{}: {error}", path.display()))?;
    drop(file);
    // MediaRecorder MP4 is fragmented too: index it so standard players can seek. (WebM stays as is.)
    if path.extension().is_some_and(|extension| extension == "mp4") {
        crate::mp4fix::defragment_later(path);
    }
    Ok(total)
}
