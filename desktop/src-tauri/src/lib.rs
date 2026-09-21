use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    fs,
    io::{ErrorKind, Read, Write},
    net::{IpAddr, SocketAddr, TcpStream},
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        Arc, Mutex, MutexGuard,
    },
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
use tauri::{AppHandle, Emitter, Manager, State};

const KEYRING_SERVICE: &str = "ru.oncam.cockpit";
const CONNECT_TIMEOUT: Duration = Duration::from_millis(700);
const WRITE_TIMEOUT: Duration = Duration::from_millis(500);
const REPLY_TIMEOUT: Duration = Duration::from_millis(300);
const PROBE_TIMEOUT: Duration = Duration::from_millis(600);
/// A held jog button must be confirmed by the UI at least this often, otherwise the axes are stopped.
const JOG_LEASE: Duration = Duration::from_millis(900);
const MAX_PROBE_TARGETS: usize = 32;
const MAX_CONFIG_BYTES: usize = 512 * 1024;
const PAN_MAX_SPEED: f64 = 50.0;
const TILT_MAX_SPEED: f64 = 19.0;
const PAN_LIMIT: f64 = 180.0;
/// `$8` accepts a lower tilt limit no further than 315.00° (−45°) and an upper one up to 90°.
const TILT_MIN: f64 = -45.0;
const TILT_MAX: f64 = 90.0;
const SECRET_KEYS: [&str; 6] = ["password", "passwd", "secret", "token", "apikey", "api_key"];

static CONFIG_WRITE: Mutex<()> = Mutex::new(());

fn lock<T>(mutex: &Mutex<T>) -> MutexGuard<'_, T> {
    // A panic in one worker must not leave the platform uncontrollable.
    mutex
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
}

async fn run_blocking<T, F>(task: F) -> Result<T, String>
where
    F: FnOnce() -> Result<T, String> + Send + 'static,
    T: Send + 'static,
{
    tauri::async_runtime::spawn_blocking(task)
        .await
        .map_err(|error| error.to_string())?
}

fn unix_seconds() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|elapsed| elapsed.as_secs())
        .unwrap_or(0)
}

fn validate_target(ip: &str, port: u16) -> Result<SocketAddr, String> {
    if port == 0 {
        return Err("Порт должен быть от 1 до 65535".into());
    }
    let address = ip
        .trim()
        .parse::<IpAddr>()
        .map_err(|_| format!("Некорректный IP-адрес: {ip}"))?;
    Ok(SocketAddr::new(address, port))
}

// ---------------------------------------------------------------- configuration

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct ConfigLoad {
    config: Option<Value>,
    /// Set when a damaged config.json was moved aside and defaults are used instead.
    recovered_from: Option<String>,
}

fn config_path(app: &AppHandle) -> Result<PathBuf, String> {
    app.path()
        .app_config_dir()
        .map(|directory| directory.join("config.json"))
        .map_err(|error| error.to_string())
}

fn load_config_file(path: &Path) -> Result<ConfigLoad, String> {
    let data = match fs::read_to_string(path) {
        Ok(data) => data,
        Err(error) if error.kind() == ErrorKind::NotFound => {
            return Ok(ConfigLoad {
                config: None,
                recovered_from: None,
            })
        }
        Err(error) => return Err(format!("Не удалось прочитать конфигурацию: {error}")),
    };
    match serde_json::from_str::<Value>(&data) {
        Ok(config) if config.is_object() => Ok(ConfigLoad {
            config: Some(config),
            recovered_from: None,
        }),
        _ => {
            // Keep the damaged file for diagnosis and start with defaults instead of refusing to run.
            let backup = path.with_extension(format!("corrupt-{}.json", unix_seconds()));
            fs::rename(path, &backup)
                .map_err(|error| format!("Конфигурация повреждена и не перемещена: {error}"))?;
            Ok(ConfigLoad {
                config: None,
                recovered_from: Some(backup.display().to_string()),
            })
        }
    }
}

/// Passwords live in the OS keychain; never let one reach config.json, even by mistake.
fn strip_secrets(value: &mut Value) {
    match value {
        Value::Object(map) => {
            map.retain(|key, _| !SECRET_KEYS.contains(&key.to_ascii_lowercase().as_str()));
            map.values_mut().for_each(strip_secrets);
        }
        Value::Array(items) => items.iter_mut().for_each(strip_secrets),
        _ => {}
    }
}

fn create_private_file(path: &Path) -> std::io::Result<fs::File> {
    let mut options = fs::OpenOptions::new();
    options.write(true).create(true).truncate(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    options.open(path)
}

fn write_config_file(path: &Path, mut config: Value) -> Result<(), String> {
    if !config.is_object() {
        return Err("Конфигурация должна быть JSON-объектом".into());
    }
    strip_secrets(&mut config);
    let encoded = serde_json::to_vec_pretty(&config).map_err(|error| error.to_string())?;
    if encoded.len() > MAX_CONFIG_BYTES {
        return Err("Конфигурация превышает допустимый размер".into());
    }
    let parent = path
        .parent()
        .ok_or_else(|| "Некорректный путь конфигурации".to_string())?;
    fs::create_dir_all(parent).map_err(|error| error.to_string())?;

    let _guard = lock(&CONFIG_WRITE);
    // Write a sibling file and rename it over the old one: a crash never leaves a truncated config.
    let temporary = path.with_extension("json.tmp");
    let mut file = create_private_file(&temporary).map_err(|error| error.to_string())?;
    file.write_all(&encoded)
        .map_err(|error| error.to_string())?;
    file.sync_all().map_err(|error| error.to_string())?;
    drop(file);
    fs::rename(&temporary, path).map_err(|error| error.to_string())
}

#[tauri::command]
async fn get_config(app: AppHandle) -> Result<ConfigLoad, String> {
    let path = config_path(&app)?;
    run_blocking(move || load_config_file(&path)).await
}

#[tauri::command]
async fn save_config(app: AppHandle, config: Value) -> Result<(), String> {
    let path = config_path(&app)?;
    run_blocking(move || write_config_file(&path, config)).await
}

// ---------------------------------------------------------------- keychain

fn keyring_entry(device_id: &str) -> Result<keyring::Entry, String> {
    let valid = (1..=48).contains(&device_id.len())
        && !device_id.starts_with('-')
        && device_id
            .bytes()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'-');
    if !valid {
        return Err("Некорректный идентификатор устройства".into());
    }
    keyring::Entry::new(KEYRING_SERVICE, device_id).map_err(|error| error.to_string())
}

#[tauri::command]
async fn has_secret(device_id: String) -> Result<bool, String> {
    run_blocking(move || match keyring_entry(&device_id)?.get_password() {
        Ok(_) => Ok(true),
        Err(keyring::Error::NoEntry) => Ok(false),
        Err(error) => Err(error.to_string()),
    })
    .await
}

#[tauri::command]
async fn get_secret(device_id: String) -> Result<String, String> {
    run_blocking(move || match keyring_entry(&device_id)?.get_password() {
        Ok(password) => Ok(password),
        Err(keyring::Error::NoEntry) => Ok(String::new()),
        Err(error) => Err(error.to_string()),
    })
    .await
}

#[tauri::command]
async fn set_secret(device_id: String, password: String) -> Result<(), String> {
    if password.len() > 256 {
        return Err("Пароль длиннее 256 символов".into());
    }
    run_blocking(move || {
        let entry = keyring_entry(&device_id)?;
        if password.is_empty() {
            match entry.delete_credential() {
                Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
                Err(error) => Err(error.to_string()),
            }
        } else {
            entry
                .set_password(&password)
                .map_err(|error| error.to_string())
        }
    })
    .await
}

// ---------------------------------------------------------------- TL.0009 service link

fn validate_command(command: &str) -> Result<(), String> {
    let framed = (3..=64).contains(&command.len())
        && command.starts_with('$')
        && command.ends_with('#')
        && command[1..command.len() - 1]
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b',' | b'.' | b'-'));
    if framed {
        Ok(())
    } else {
        Err("Команда сервисного протокола отклонена".into())
    }
}

struct Reply {
    text: String,
    open: bool,
}

/// Drops late answers to earlier commands so they are never read as the reply to this one.
fn discard_pending(stream: &mut TcpStream) -> Result<(), String> {
    stream
        .set_nonblocking(true)
        .map_err(|error| error.to_string())?;
    let mut buffer = [0_u8; 256];
    let mut outcome = Ok(());
    for _ in 0..64 {
        match stream.read(&mut buffer) {
            Ok(0) => {
                outcome = Err("соединение закрыто устройством".to_string());
                break;
            }
            Ok(_) => {}
            Err(error) if error.kind() == ErrorKind::WouldBlock => break,
            Err(error) => {
                outcome = Err(error.to_string());
                break;
            }
        }
    }
    stream
        .set_nonblocking(false)
        .map_err(|error| error.to_string())?;
    outcome
}

fn read_reply(stream: &mut TcpStream) -> Result<Reply, String> {
    let mut reply = Vec::with_capacity(64);
    let mut buffer = [0_u8; 128];
    let mut open = true;
    loop {
        match stream.read(&mut buffer) {
            Ok(0) => {
                open = false;
                break;
            }
            Ok(count) => {
                reply.extend_from_slice(&buffer[..count]);
                if reply.contains(&b'#') || reply.len() >= 1024 {
                    break;
                }
            }
            // Set-commands are often not acknowledged: silence after a successful write is not an error.
            Err(error) if matches!(error.kind(), ErrorKind::WouldBlock | ErrorKind::TimedOut) => {
                break
            }
            Err(error) => return Err(error.to_string()),
        }
    }
    Ok(Reply {
        text: String::from_utf8_lossy(&reply).trim().to_string(),
        open,
    })
}

fn transact(stream: &mut TcpStream, command: &str) -> Result<Reply, String> {
    discard_pending(stream)?;
    stream
        .write_all(command.as_bytes())
        .map_err(|error| error.to_string())?;
    read_reply(stream)
}

/// One persistent connection to the platform; reopened transparently when the device drops it.
#[derive(Default)]
struct Link {
    address: Option<SocketAddr>,
    stream: Option<TcpStream>,
}

impl Link {
    /// Sends one service command and returns the reply (empty when the device stays silent).
    fn exchange(&mut self, address: SocketAddr, command: &str) -> Result<String, String> {
        validate_command(command)?;
        let reused = self.address == Some(address) && self.stream.is_some();
        let result = match self.try_exchange(address, command) {
            // The idle connection went stale; every service command is idempotent, so retry once.
            Err(_) if reused => self.try_exchange(address, command),
            other => other,
        };
        result.map_err(|error| format!("{address} — {error}"))
    }

    fn try_exchange(&mut self, address: SocketAddr, command: &str) -> Result<String, String> {
        match self
            .stream_for(address)
            .and_then(|stream| transact(stream, command))
        {
            Ok(reply) => {
                if !reply.open {
                    self.stream = None;
                }
                Ok(reply.text)
            }
            Err(error) => {
                self.stream = None;
                Err(error)
            }
        }
    }

    fn stream_for(&mut self, address: SocketAddr) -> Result<&mut TcpStream, String> {
        if self.address != Some(address) {
            self.stream = None;
            self.address = Some(address);
        }
        if self.stream.is_none() {
            let stream = TcpStream::connect_timeout(&address, CONNECT_TIMEOUT)
                .map_err(|error| error.to_string())?;
            stream
                .set_nodelay(true)
                .map_err(|error| error.to_string())?;
            stream
                .set_write_timeout(Some(WRITE_TIMEOUT))
                .map_err(|error| error.to_string())?;
            stream
                .set_read_timeout(Some(REPLY_TIMEOUT))
                .map_err(|error| error.to_string())?;
            self.stream = Some(stream);
        }
        self.stream
            .as_mut()
            .ok_or_else(|| "нет соединения".to_string())
    }
}

struct JogLease {
    address: SocketAddr,
    deadline: Instant,
}

#[derive(Default)]
struct Platform {
    /// Serialises all traffic to the device so commands and replies never interleave.
    link: Mutex<Link>,
    /// Mirror of the open link address, readable while a command is in flight.
    linked: Mutex<Option<SocketAddr>>,
    /// Highest UI sequence number of a stop; motion requests issued before it are dropped.
    last_stop_seq: AtomicU64,
    /// Bumped by every stop, jog, self-test or new profile; a running profile exits when it changes.
    rocking: AtomicU64,
    jog_lease: Mutex<Option<JogLease>>,
    watchdog: AtomicBool,
}

impl Platform {
    fn with_link<T>(&self, action: impl FnOnce(&mut Link) -> T) -> T {
        let mut link = lock(&self.link);
        let result = action(&mut link);
        let open = link.address.filter(|_| link.stream.is_some());
        *lock(&self.linked) = open;
        result
    }

    fn is_linked_to(&self, address: SocketAddr) -> bool {
        *lock(&self.linked) == Some(address)
    }

    fn is_superseded(&self, seq: u64) -> bool {
        seq <= self.last_stop_seq.load(Ordering::SeqCst)
    }

    /// Cancels every motion source before the stop itself waits behind in-flight traffic.
    fn cancel_motion(&self, seq: u64) {
        self.last_stop_seq.fetch_max(seq, Ordering::SeqCst);
        self.rocking.fetch_add(1, Ordering::SeqCst);
        *lock(&self.jog_lease) = None;
    }

    fn stop_axes(&self, address: SocketAddr) -> Result<(), String> {
        let (pan, tilt) =
            self.with_link(|link| (link.exchange(address, "$u#"), link.exchange(address, "$U#")));
        match (pan, tilt) {
            (Ok(_), Ok(_)) => Ok(()),
            (Err(pan), Ok(_)) => Err(format!("PAN: {pan}")),
            (Ok(_), Err(tilt)) => Err(format!("TILT: {tilt}")),
            (Err(pan), Err(tilt)) => Err(format!("PAN: {pan}; TILT: {tilt}")),
        }
    }

    fn jog(&self, address: SocketAddr, seq: u64, command: &str) -> Result<String, String> {
        if !self.watchdog.load(Ordering::SeqCst) {
            return Err("Сторожевой таймер не запущен — ручное движение запрещено".into());
        }
        self.with_link(|link| {
            if self.is_superseded(seq) {
                return Ok("пропущено: уже получена команда стоп".to_string());
            }
            // Manual control always overrides a running profile.
            self.rocking.fetch_add(1, Ordering::SeqCst);
            let reply = link.exchange(address, command)?;
            if !self.is_superseded(seq) {
                *lock(&self.jog_lease) = Some(JogLease {
                    address,
                    deadline: Instant::now() + JOG_LEASE,
                });
            }
            Ok(describe(command, reply))
        })
    }

    fn keep_jog_alive(&self) {
        if let Some(lease) = lock(&self.jog_lease).as_mut() {
            lease.deadline = Instant::now() + JOG_LEASE;
        }
    }

    fn take_expired_lease(&self) -> Option<SocketAddr> {
        let mut lease = lock(&self.jog_lease);
        match lease.as_ref() {
            Some(held) if Instant::now() >= held.deadline => lease.take().map(|held| held.address),
            _ => None,
        }
    }
}

fn spawn_jog_watchdog(platform: Arc<Platform>) {
    let worker = Arc::clone(&platform);
    let spawned = thread::Builder::new()
        .name("tl0009-jog-watchdog".into())
        .spawn(move || loop {
            thread::sleep(Duration::from_millis(100));
            if let Some(address) = worker.take_expired_lease() {
                // The UI stopped confirming the held button (crash, lost pointer, frozen view).
                let _ = worker.stop_axes(address);
            }
        });
    match spawned {
        Ok(_) => platform.watchdog.store(true, Ordering::SeqCst),
        Err(error) => eprintln!("TL.0009 jog watchdog was not started: {error}"),
    }
}

fn describe(command: &str, reply: String) -> String {
    if reply.is_empty() {
        format!("{command} → отправлено")
    } else {
        reply
    }
}

fn validate_speed(axis: &str, speed: f64, max: f64) -> Result<(), String> {
    if speed.is_finite() && speed > 0.0 && speed <= max {
        Ok(())
    } else {
        Err(format!(
            "{axis}: скорость должна быть больше 0 и не выше {max}°/с"
        ))
    }
}

fn jog_command(direction: &str, speed: f64) -> Result<String, String> {
    let (axis, sign, max) = match direction {
        "left" => ('w', -1.0, PAN_MAX_SPEED),
        "right" => ('w', 1.0, PAN_MAX_SPEED),
        "up" => ('W', 1.0, TILT_MAX_SPEED),
        "down" => ('W', -1.0, TILT_MAX_SPEED),
        _ => return Err("Неизвестное направление".into()),
    };
    validate_speed(if axis == 'w' { "PAN" } else { "TILT" }, speed, max)?;
    Ok(format!("${axis},{:.2}#", sign * speed))
}

/// The service protocol addresses absolute positions as 0.00..359.99°; profiles use signed angles.
fn device_angle(angle: f64) -> f64 {
    let hundredths = (angle * 100.0).round() as i64;
    hundredths.rem_euclid(36_000) as f64 / 100.0
}

fn position_command(axis: char, angle: f64, speed: f64) -> String {
    format!("${axis},{:.2},{speed:.2}#", device_angle(angle))
}

// ---------------------------------------------------------------- rocking profiles

#[derive(Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct RockingProfile {
    pan_min: f64,
    pan_max: f64,
    tilt_min: f64,
    tilt_max: f64,
    pan_speed: f64,
    tilt_speed: f64,
    cycles: u32,
    pause_seconds: f64,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct RockingEvent {
    state: &'static str,
    cycle: u32,
    cycles: u32,
    message: Option<String>,
}

enum RockingOutcome {
    Completed,
    Cancelled,
    Failed(String),
}

fn validate_profile(profile: &RockingProfile) -> Result<(), String> {
    let pan_ok = profile.pan_min.is_finite()
        && profile.pan_max.is_finite()
        && profile.pan_min < profile.pan_max
        && profile.pan_min >= -PAN_LIMIT
        && profile.pan_max <= PAN_LIMIT;
    if !pan_ok {
        return Err(format!(
            "PAN: нужен диапазон min < max в пределах ±{PAN_LIMIT}°"
        ));
    }
    let tilt_ok = profile.tilt_min.is_finite()
        && profile.tilt_max.is_finite()
        && profile.tilt_min < profile.tilt_max
        && profile.tilt_min >= TILT_MIN
        && profile.tilt_max <= TILT_MAX;
    if !tilt_ok {
        return Err(format!(
            "TILT: нужен диапазон min < max в пределах {TILT_MIN}…{TILT_MAX}°"
        ));
    }
    validate_speed("PAN", profile.pan_speed, PAN_MAX_SPEED)?;
    validate_speed("TILT", profile.tilt_speed, TILT_MAX_SPEED)?;
    if !(1..=1000).contains(&profile.cycles) {
        return Err("Число циклов должно быть от 1 до 1000".into());
    }
    if !profile.pause_seconds.is_finite() || !(0.0..=300.0).contains(&profile.pause_seconds) {
        return Err("Пауза должна быть от 0 до 300 секунд".into());
    }
    Ok(())
}

fn travel_seconds(profile: &RockingProfile) -> f64 {
    ((profile.pan_max - profile.pan_min).abs() / profile.pan_speed)
        .max((profile.tilt_max - profile.tilt_min).abs() / profile.tilt_speed)
        .clamp(0.25, 60.0)
}

fn wait_while(still_current: &impl Fn() -> bool, seconds: f64) -> bool {
    let deadline = Instant::now() + Duration::from_secs_f64(seconds.max(0.0));
    loop {
        if !still_current() {
            return false;
        }
        let now = Instant::now();
        if now >= deadline {
            return true;
        }
        thread::sleep((deadline - now).min(Duration::from_millis(50)));
    }
}

fn run_rocking(
    platform: &Platform,
    address: SocketAddr,
    profile: &RockingProfile,
    generation: u64,
    mut report: impl FnMut(RockingEvent),
) {
    let current = || platform.rocking.load(Ordering::SeqCst) == generation;
    let dwell = travel_seconds(profile) + profile.pause_seconds;
    let targets = [
        (profile.pan_min, profile.tilt_min),
        (profile.pan_max, profile.tilt_max),
    ];
    let event = |state, cycle, message| RockingEvent {
        state,
        cycle,
        cycles: profile.cycles,
        message,
    };
    report(event("running", 0, None));

    let outcome = 'run: {
        for cycle in 1..=profile.cycles {
            for (pan, tilt) in targets {
                let pan_command = position_command('x', pan, profile.pan_speed);
                let tilt_command = position_command('X', tilt, profile.tilt_speed);
                let sent = platform.with_link(|link| {
                    // Checked under the link lock, so a stop can never be followed by a stale target.
                    if !current() {
                        return None;
                    }
                    Some(
                        link.exchange(address, &pan_command)
                            .and_then(|_| link.exchange(address, &tilt_command)),
                    )
                });
                match sent {
                    None => break 'run RockingOutcome::Cancelled,
                    Some(Err(error)) => break 'run RockingOutcome::Failed(error),
                    Some(Ok(_)) => {}
                }
                if !wait_while(&current, dwell) {
                    break 'run RockingOutcome::Cancelled;
                }
            }
            report(event("running", cycle, None));
        }
        RockingOutcome::Completed
    };

    let final_event = match outcome {
        // Whoever cancelled (stop, jog, self-test or a new profile) owns the axes now.
        RockingOutcome::Cancelled => event("cancelled", 0, None),
        RockingOutcome::Completed => {
            let stop_error = if current() {
                platform.stop_axes(address).err()
            } else {
                None
            };
            event("completed", profile.cycles, stop_error)
        }
        RockingOutcome::Failed(error) => {
            let stop_error = if current() {
                platform.stop_axes(address).err()
            } else {
                None
            };
            let message = match stop_error {
                Some(stop) => format!("{error}; стоп: {stop}"),
                None => error,
            };
            event("failed", 0, Some(message))
        }
    };
    report(final_event);
}

// ---------------------------------------------------------------- platform commands

#[tauri::command]
async fn platform_jog(
    platform: State<'_, Arc<Platform>>,
    ip: String,
    port: u16,
    direction: String,
    speed: f64,
    seq: u64,
) -> Result<String, String> {
    let address = validate_target(&ip, port)?;
    let command = jog_command(&direction, speed)?;
    let platform = Arc::clone(platform.inner());
    run_blocking(move || platform.jog(address, seq, &command)).await
}

#[tauri::command]
fn platform_jog_keepalive(platform: State<'_, Arc<Platform>>) {
    platform.keep_jog_alive();
}

#[tauri::command]
async fn platform_stop(
    platform: State<'_, Arc<Platform>>,
    ip: String,
    port: u16,
    seq: u64,
) -> Result<(), String> {
    // Cancel first: even an invalid address must not leave a profile or a held jog running.
    platform.cancel_motion(seq);
    let address = validate_target(&ip, port)?;
    let platform = Arc::clone(platform.inner());
    run_blocking(move || platform.stop_axes(address)).await
}

#[tauri::command]
async fn platform_self_test(
    platform: State<'_, Arc<Platform>>,
    ip: String,
    port: u16,
    seq: u64,
) -> Result<Vec<String>, String> {
    let address = validate_target(&ip, port)?;
    let platform = Arc::clone(platform.inner());
    run_blocking(move || {
        platform.with_link(|link| {
            if platform.is_superseded(seq) {
                return Err("Отменено командой стоп".to_string());
            }
            platform.rocking.fetch_add(1, Ordering::SeqCst);
            *lock(&platform.jog_lease) = None;
            ["$m,1#", "$M,1#", "$n#", "$N#"]
                .iter()
                .map(|command| {
                    link.exchange(address, command)
                        .map(|reply| describe(command, reply))
                })
                .collect()
        })
    })
    .await
}

#[tauri::command]
fn start_rocking(
    app: AppHandle,
    platform: State<'_, Arc<Platform>>,
    ip: String,
    port: u16,
    profile: RockingProfile,
    seq: u64,
) -> Result<(), String> {
    let address = validate_target(&ip, port)?;
    validate_profile(&profile)?;
    if platform.is_superseded(seq) {
        return Err("Отменено командой стоп".into());
    }
    let generation = platform.rocking.fetch_add(1, Ordering::SeqCst) + 1;
    *lock(&platform.jog_lease) = None;
    let platform = Arc::clone(platform.inner());
    thread::Builder::new()
        .name("tl0009-rocking".into())
        .spawn(move || {
            run_rocking(&platform, address, &profile, generation, |event| {
                let _ = app.emit("rocking-state", event);
            });
        })
        .map(|_| ())
        .map_err(|error| error.to_string())
}

#[tauri::command]
async fn stop_rocking(
    platform: State<'_, Arc<Platform>>,
    ip: String,
    port: u16,
    seq: u64,
) -> Result<(), String> {
    platform_stop(platform, ip, port, seq).await
}

/// WKWebView ignores `window.print()`, so on macOS the native print panel is opened from here.
/// Returns false where the page should call `window.print()` itself. Runs on the main thread (AppKit).
#[tauri::command]
fn print_page(webview: tauri::Webview) -> Result<bool, String> {
    if cfg!(target_os = "macos") {
        webview.print().map_err(|error| error.to_string())?;
        Ok(true)
    } else {
        Ok(false)
    }
}

#[tauri::command]
fn camera_lens_step(camera_id: String, mode: String, direction: i8) -> Result<(), String> {
    if !matches!(camera_id.as_str(), "camera1" | "camera2") {
        return Err("Неизвестная камера".into());
    }
    if !matches!(mode.as_str(), "zoom" | "focus") || !matches!(direction, -1 | 1) {
        return Err("Некорректная команда объектива".into());
    }
    Err("ONVIF-адаптер объектива ещё не подключён к новому клиенту".into())
}

// ---------------------------------------------------------------- device probing

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct ProbeTarget {
    id: String,
    ip: String,
    port: u16,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ProbeResult {
    id: String,
    connected: bool,
    latency_ms: Option<u64>,
    error: Option<String>,
}

fn probe_one(platform: &Platform, target: ProbeTarget) -> ProbeResult {
    let ProbeTarget { id, ip, port } = target;
    let address = match validate_target(&ip, port) {
        Ok(address) => address,
        Err(error) => {
            return ProbeResult {
                id,
                connected: false,
                latency_ms: None,
                error: Some(error),
            }
        }
    };
    if platform.is_linked_to(address) {
        // The control link is already open; a second connection may be refused by the device.
        return ProbeResult {
            id,
            connected: true,
            latency_ms: None,
            error: None,
        };
    }
    let started = Instant::now();
    match TcpStream::connect_timeout(&address, PROBE_TIMEOUT) {
        Ok(_) => ProbeResult {
            id,
            connected: true,
            latency_ms: Some(started.elapsed().as_millis() as u64),
            error: None,
        },
        Err(error) => ProbeResult {
            id,
            connected: false,
            latency_ms: None,
            error: Some(error.to_string()),
        },
    }
}

fn probe_all(platform: &Platform, targets: Vec<ProbeTarget>) -> Vec<ProbeResult> {
    thread::scope(|scope| {
        let workers: Vec<_> = targets
            .into_iter()
            .map(|target| scope.spawn(move || probe_one(platform, target)))
            .collect();
        workers
            .into_iter()
            .filter_map(|worker| worker.join().ok())
            .collect()
    })
}

#[tauri::command]
async fn probe_devices(
    platform: State<'_, Arc<Platform>>,
    targets: Vec<ProbeTarget>,
) -> Result<Vec<ProbeResult>, String> {
    if targets.len() > MAX_PROBE_TARGETS {
        return Err(format!(
            "Не более {MAX_PROBE_TARGETS} модулей за один опрос"
        ));
    }
    let platform = Arc::clone(platform.inner());
    run_blocking(move || Ok(probe_all(&platform, targets))).await
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let platform = Arc::new(Platform::default());
    let watchdog = Arc::clone(&platform);
    tauri::Builder::default()
        .manage(platform)
        .plugin(tauri_plugin_dialog::init())
        .setup(move |_app| {
            spawn_jog_watchdog(watchdog);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_config,
            save_config,
            has_secret,
            get_secret,
            set_secret,
            probe_devices,
            platform_jog,
            platform_jog_keepalive,
            platform_stop,
            platform_self_test,
            print_page,
            camera_lens_step,
            start_rocking,
            stop_rocking
        ])
        .run(tauri::generate_context!())
        .expect("error while running MKIS100TEST");
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{net::TcpListener, sync::mpsc};

    fn profile() -> RockingProfile {
        RockingProfile {
            pan_min: -45.0,
            pan_max: 45.0,
            tilt_min: -15.0,
            tilt_max: 20.0,
            pan_speed: 20.0,
            tilt_speed: 8.0,
            cycles: 10,
            pause_seconds: 1.0,
        }
    }

    /// Minimal TL.0009 stand-in: echoes every command, stays silent on stops,
    /// and optionally closes the connection after `close_after` commands.
    fn mock_device(
        close_after: Option<usize>,
    ) -> (SocketAddr, mpsc::Receiver<String>, Arc<AtomicU64>) {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let (sender, receiver) = mpsc::channel();
        let connections = Arc::new(AtomicU64::new(0));
        let counter = Arc::clone(&connections);
        thread::spawn(move || {
            for stream in listener.incoming() {
                let Ok(mut stream) = stream else { break };
                counter.fetch_add(1, Ordering::SeqCst);
                let sender = sender.clone();
                thread::spawn(move || {
                    let mut pending = Vec::new();
                    let mut handled = 0;
                    let mut buffer = [0_u8; 64];
                    while let Ok(count) = stream.read(&mut buffer) {
                        if count == 0 {
                            break;
                        }
                        pending.extend_from_slice(&buffer[..count]);
                        while let Some(end) = pending.iter().position(|byte| *byte == b'#') {
                            let command = String::from_utf8_lossy(&pending[..=end]).into_owned();
                            pending.drain(..=end);
                            if command != "$u#" && command != "$U#" {
                                let _ = stream.write_all(command.as_bytes());
                            }
                            let _ = sender.send(command);
                            handled += 1;
                            if Some(handled) == close_after {
                                return;
                            }
                        }
                    }
                });
            }
        });
        (address, receiver, connections)
    }

    fn next(commands: &mpsc::Receiver<String>) -> String {
        commands
            .recv_timeout(Duration::from_secs(3))
            .expect("device received no command")
    }

    #[test]
    fn signed_angles_map_to_protocol_range() {
        assert_eq!(device_angle(-45.0), 315.0);
        assert_eq!(device_angle(45.0), 45.0);
        assert_eq!(device_angle(-0.001), 0.0);
        assert_eq!(device_angle(359.999), 0.0);
        assert_eq!(position_command('x', -45.0, 20.0), "$x,315.00,20.00#");
        assert_eq!(position_command('X', -15.0, 8.0), "$X,345.00,8.00#");
    }

    #[test]
    fn jog_commands_are_signed_and_bounded() {
        assert_eq!(jog_command("left", 12.5).unwrap(), "$w,-12.50#");
        assert_eq!(jog_command("up", 5.0).unwrap(), "$W,5.00#");
        assert!(jog_command("right", 50.5).is_err());
        assert!(jog_command("down", 19.5).is_err());
        assert!(jog_command("left", f64::NAN).is_err());
        assert!(jog_command("north", 1.0).is_err());
    }

    #[test]
    fn profile_limits_follow_hardware_ranges() {
        assert!(validate_profile(&profile()).is_ok());
        assert!(validate_profile(&RockingProfile {
            tilt_min: -60.0,
            ..profile()
        })
        .is_err());
        assert!(validate_profile(&RockingProfile {
            pan_max: 200.0,
            ..profile()
        })
        .is_err());
        assert!(validate_profile(&RockingProfile {
            pan_min: 50.0,
            ..profile()
        })
        .is_err());
        assert!(validate_profile(&RockingProfile {
            cycles: 0,
            ..profile()
        })
        .is_err());
    }

    #[test]
    fn service_commands_are_strictly_framed() {
        assert!(validate_command("$x,315.00,20.00#").is_ok());
        assert!(validate_command("$u#").is_ok());
        assert!(validate_command("u#").is_err());
        assert!(validate_command("$u;reboot#").is_err());
        assert!(validate_command("$#").is_err());
    }

    #[test]
    fn secrets_never_reach_config_json() {
        let mut config = serde_json::json!({
            "cameras": [{ "ip": "1.2.3.4", "password": "x", "Password": "y" }],
            "recording": { "includeEncryptedSecrets": false },
            "token": "t"
        });
        strip_secrets(&mut config);
        assert_eq!(
            config,
            serde_json::json!({
                "cameras": [{ "ip": "1.2.3.4" }],
                "recording": { "includeEncryptedSecrets": false }
            })
        );
    }

    #[test]
    fn config_is_written_atomically_and_recovered_when_damaged() {
        let directory =
            std::env::temp_dir().join(format!("oncam-config-test-{}", std::process::id()));
        let path = directory.join("config.json");
        write_config_file(
            &path,
            serde_json::json!({ "platformPort": 9762, "password": "x" }),
        )
        .unwrap();
        let loaded = load_config_file(&path).unwrap();
        assert_eq!(
            loaded.config,
            Some(serde_json::json!({ "platformPort": 9762 }))
        );
        assert!(!path.with_extension("json.tmp").exists());

        fs::write(&path, "{ broken").unwrap();
        let recovered = load_config_file(&path).unwrap();
        assert!(recovered.config.is_none());
        assert!(recovered.recovered_from.is_some());
        assert!(!path.exists());
        let _ = fs::remove_dir_all(&directory);
    }

    #[test]
    fn link_reuses_connection_and_tolerates_silent_commands() {
        let (address, commands, connections) = mock_device(None);
        let mut link = Link::default();
        assert_eq!(link.exchange(address, "$m#").unwrap(), "$m#");
        assert_eq!(link.exchange(address, "$u#").unwrap(), "");
        assert_eq!(link.exchange(address, "$o#").unwrap(), "$o#");
        assert_eq!(
            [next(&commands), next(&commands), next(&commands)],
            ["$m#", "$u#", "$o#"]
        );
        assert_eq!(connections.load(Ordering::SeqCst), 1);
    }

    #[test]
    fn link_reconnects_after_device_drops_idle_connection() {
        let (address, _commands, connections) = mock_device(Some(1));
        let mut link = Link::default();
        assert_eq!(link.exchange(address, "$m#").unwrap(), "$m#");
        thread::sleep(Duration::from_millis(50));
        assert_eq!(link.exchange(address, "$M#").unwrap(), "$M#");
        assert_eq!(connections.load(Ordering::SeqCst), 2);
    }

    #[test]
    fn jog_older_than_stop_is_dropped_without_traffic() {
        let platform = Platform::default();
        platform.watchdog.store(true, Ordering::SeqCst);
        platform.cancel_motion(10);
        let unreachable = SocketAddr::from(([127, 0, 0, 1], 9));
        assert!(platform
            .jog(unreachable, 9, "$w,5.00#")
            .unwrap()
            .starts_with("пропущено"));
    }

    #[test]
    fn jog_is_refused_without_watchdog() {
        let platform = Platform::default();
        let unreachable = SocketAddr::from(([127, 0, 0, 1], 9));
        assert!(platform.jog(unreachable, 1, "$w,5.00#").is_err());
    }

    #[test]
    fn watchdog_stops_axes_when_jog_is_not_confirmed() {
        let (address, commands, _) = mock_device(None);
        let platform = Arc::new(Platform::default());
        spawn_jog_watchdog(Arc::clone(&platform));
        platform.jog(address, 1, "$w,5.00#").unwrap();
        assert_eq!(next(&commands), "$w,5.00#");

        // Confirmed for longer than one lease: no stop yet.
        for _ in 0..6 {
            thread::sleep(Duration::from_millis(200));
            platform.keep_jog_alive();
        }
        assert!(commands.try_recv().is_err());

        // Confirmation stops: both axes must be stopped once the lease expires.
        assert_eq!(next(&commands), "$u#");
        assert_eq!(next(&commands), "$U#");
    }

    #[test]
    fn stop_cancels_running_profile_before_next_target() {
        let (address, commands, _) = mock_device(None);
        let platform = Arc::new(Platform::default());
        let profile = RockingProfile {
            pan_min: -10.0,
            pan_max: 10.0,
            tilt_min: -5.0,
            tilt_max: 5.0,
            pan_speed: 50.0,
            tilt_speed: 19.0,
            cycles: 3,
            pause_seconds: 0.0,
        };
        let generation = platform.rocking.fetch_add(1, Ordering::SeqCst) + 1;
        let (events_tx, events) = mpsc::channel();
        let runner = {
            let platform = Arc::clone(&platform);
            thread::spawn(move || {
                run_rocking(&platform, address, &profile, generation, |event| {
                    let _ = events_tx.send(event.state);
                })
            })
        };
        assert_eq!(next(&commands), "$x,350.00,50.00#");
        assert_eq!(next(&commands), "$X,355.00,19.00#");
        platform.cancel_motion(1);
        runner.join().unwrap();
        assert!(commands.recv_timeout(Duration::from_millis(300)).is_err());
        assert_eq!(events.try_iter().last(), Some("cancelled"));
    }

    #[test]
    fn completed_profile_visits_both_targets_and_stops() {
        let (address, commands, _) = mock_device(None);
        let platform = Arc::new(Platform::default());
        let profile = RockingProfile {
            pan_min: 0.0,
            pan_max: 5.0,
            tilt_min: 0.0,
            tilt_max: 2.0,
            pan_speed: 50.0,
            tilt_speed: 19.0,
            cycles: 1,
            pause_seconds: 0.0,
        };
        let generation = platform.rocking.fetch_add(1, Ordering::SeqCst) + 1;
        let mut states = Vec::new();
        run_rocking(&platform, address, &profile, generation, |event| {
            states.push(event.state)
        });
        let sent: Vec<_> = (0..6).map(|_| next(&commands)).collect();
        assert_eq!(
            sent,
            [
                "$x,0.00,50.00#",
                "$X,0.00,19.00#",
                "$x,5.00,50.00#",
                "$X,2.00,19.00#",
                "$u#",
                "$U#"
            ]
        );
        assert_eq!(states.last(), Some(&"completed"));
    }
}
