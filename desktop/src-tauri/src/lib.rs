use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    fs,
    io::{Read, Write},
    net::{IpAddr, SocketAddr, TcpStream},
    path::PathBuf,
    sync::{
        atomic::{AtomicU64, Ordering},
        mpsc, Arc,
    },
    thread,
    time::Duration,
};
use tauri::{AppHandle, Manager};

const KEYRING_SERVICE: &str = "ru.oncam.cockpit";

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct DeviceSummary {
    id: String,
    name: String,
    kind: String,
    ip: String,
    port: u16,
    protocol: String,
    connected: bool,
}

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

#[derive(Default)]
struct RockingState {
    generation: Arc<AtomicU64>,
}

fn config_path(app: &AppHandle) -> Result<PathBuf, String> {
    app.path()
        .app_config_dir()
        .map(|directory| directory.join("config.json"))
        .map_err(|error| error.to_string())
}

fn read_config(app: &AppHandle) -> Result<Option<Value>, String> {
    let path = config_path(app)?;
    if !path.exists() {
        return Ok(None);
    }
    let data = fs::read_to_string(path).map_err(|error| error.to_string())?;
    serde_json::from_str(&data)
        .map(Some)
        .map_err(|error| error.to_string())
}

fn value_at(config: &Value, pointer: &str, fallback: &str) -> String {
    config
        .pointer(pointer)
        .and_then(Value::as_str)
        .unwrap_or(fallback)
        .to_owned()
}

fn port_at(config: &Value, pointer: &str, fallback: u16) -> u16 {
    config
        .pointer(pointer)
        .and_then(Value::as_u64)
        .and_then(|port| u16::try_from(port).ok())
        .unwrap_or(fallback)
}

#[tauri::command]
fn get_config(app: AppHandle) -> Result<Option<Value>, String> {
    read_config(&app)
}

#[tauri::command]
fn save_config(app: AppHandle, config: Value) -> Result<(), String> {
    let path = config_path(&app)?;
    let parent = path
        .parent()
        .ok_or_else(|| "Invalid configuration path".to_string())?;
    fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    let encoded = serde_json::to_string_pretty(&config).map_err(|error| error.to_string())?;
    fs::write(path, encoded).map_err(|error| error.to_string())
}

#[tauri::command]
fn get_secret(device_id: String) -> Result<String, String> {
    let entry =
        keyring::Entry::new(KEYRING_SERVICE, &device_id).map_err(|error| error.to_string())?;
    match entry.get_password() {
        Ok(password) => Ok(password),
        Err(keyring::Error::NoEntry) => Ok(String::new()),
        Err(error) => Err(error.to_string()),
    }
}

#[tauri::command]
fn set_secret(device_id: String, password: String) -> Result<(), String> {
    let entry =
        keyring::Entry::new(KEYRING_SERVICE, &device_id).map_err(|error| error.to_string())?;
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
}

fn can_connect(ip: &str, port: u16) -> bool {
    let Ok(address) = ip.parse::<IpAddr>() else {
        return false;
    };
    TcpStream::connect_timeout(&SocketAddr::new(address, port), Duration::from_millis(450)).is_ok()
}

fn validate_target(ip: &str, port: u16) -> Result<SocketAddr, String> {
    if port == 0 {
        return Err("Порт должен быть от 1 до 65535".into());
    }
    let address = ip
        .parse::<IpAddr>()
        .map_err(|_| "Некорректный IP-адрес".to_string())?;
    Ok(SocketAddr::new(address, port))
}

fn send_service_command(ip: &str, port: u16, command: &str) -> Result<String, String> {
    if !command.starts_with('$') || !command.ends_with('#') || command.len() > 64 {
        return Err("Команда сервисного протокола отклонена".into());
    }
    let address = validate_target(ip, port)?;
    let timeout = Duration::from_millis(900);
    let mut stream = TcpStream::connect_timeout(&address, timeout)
        .map_err(|error| format!("{}:{} — {}", ip, port, error))?;
    stream
        .set_read_timeout(Some(timeout))
        .map_err(|error| error.to_string())?;
    stream
        .set_write_timeout(Some(timeout))
        .map_err(|error| error.to_string())?;
    stream
        .write_all(command.as_bytes())
        .map_err(|error| error.to_string())?;

    let mut response = Vec::with_capacity(64);
    let mut buffer = [0_u8; 128];
    loop {
        match stream.read(&mut buffer) {
            Ok(0) => break,
            Ok(count) => {
                response.extend_from_slice(&buffer[..count]);
                if response.contains(&b'#') || response.len() >= 1024 {
                    break;
                }
            }
            Err(error)
                if matches!(
                    error.kind(),
                    std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut
                ) =>
            {
                break
            }
            Err(error) => return Err(error.to_string()),
        }
    }
    if response.is_empty() {
        Ok(format!("{} → отправлено", command))
    } else {
        Ok(String::from_utf8_lossy(&response).trim().to_string())
    }
}

fn validate_speed(speed: f64, max: f64) -> Result<(), String> {
    if speed.is_finite() && speed > 0.0 && speed <= max {
        Ok(())
    } else {
        Err(format!(
            "Скорость должна быть больше 0 и не превышать {max}°/с"
        ))
    }
}

#[tauri::command]
fn platform_jog(ip: String, port: u16, direction: String, speed: f64) -> Result<String, String> {
    let (command, max_speed) = match direction.as_str() {
        "left" => (format!("$w,{:.2}#", -speed), 50.0),
        "right" => (format!("$w,{:.2}#", speed), 50.0),
        "up" => (format!("$W,{:.2}#", speed), 19.0),
        "down" => (format!("$W,{:.2}#", -speed), 19.0),
        _ => return Err("Неизвестное направление".into()),
    };
    validate_speed(speed, max_speed)?;
    send_service_command(&ip, port, &command)
}

#[tauri::command]
fn platform_stop(ip: String, port: u16) -> Result<(), String> {
    let pan = send_service_command(&ip, port, "$u#");
    let tilt = send_service_command(&ip, port, "$U#");
    match (pan, tilt) {
        (Ok(_), Ok(_)) => Ok(()),
        (Err(pan_error), Ok(_)) => Err(format!("PAN: {pan_error}")),
        (Ok(_), Err(tilt_error)) => Err(format!("TILT: {tilt_error}")),
        (Err(pan_error), Err(tilt_error)) => Err(format!("PAN: {pan_error}; TILT: {tilt_error}")),
    }
}

#[tauri::command]
fn platform_self_test(ip: String, port: u16) -> Result<Vec<String>, String> {
    Ok(vec![
        send_service_command(&ip, port, "$m,1#")?,
        send_service_command(&ip, port, "$M,1#")?,
        send_service_command(&ip, port, "$n#")?,
        send_service_command(&ip, port, "$N#")?,
    ])
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

fn validate_profile(profile: &RockingProfile) -> Result<(), String> {
    if !profile.pan_min.is_finite()
        || !profile.pan_max.is_finite()
        || profile.pan_min >= profile.pan_max
        || profile.pan_min < -360.0
        || profile.pan_max > 360.0
    {
        return Err("Некорректный диапазон PAN".into());
    }
    if !profile.tilt_min.is_finite()
        || !profile.tilt_max.is_finite()
        || profile.tilt_min >= profile.tilt_max
        || profile.tilt_min < -90.0
        || profile.tilt_max > 90.0
    {
        return Err("Некорректный диапазон TILT".into());
    }
    validate_speed(profile.pan_speed, 50.0)?;
    validate_speed(profile.tilt_speed, 19.0)?;
    if !(1..=1000).contains(&profile.cycles) {
        return Err("Число циклов должно быть от 1 до 1000".into());
    }
    if !profile.pause_seconds.is_finite() || !(0.0..=300.0).contains(&profile.pause_seconds) {
        return Err("Пауза должна быть от 0 до 300 секунд".into());
    }
    Ok(())
}

fn wait_interruptible(token: &AtomicU64, generation: u64, seconds: f64) -> bool {
    let steps = ((seconds.max(0.0) * 10.0).ceil() as u64).max(1);
    for _ in 0..steps {
        if token.load(Ordering::SeqCst) != generation {
            return false;
        }
        thread::sleep(Duration::from_millis(100));
    }
    true
}

#[tauri::command]
fn start_rocking(
    state: tauri::State<'_, RockingState>,
    ip: String,
    port: u16,
    profile: RockingProfile,
) -> Result<(), String> {
    validate_target(&ip, port)?;
    validate_profile(&profile)?;
    let generation = state.generation.fetch_add(1, Ordering::SeqCst) + 1;
    let token = Arc::clone(&state.generation);
    thread::spawn(move || {
        let travel_seconds = ((profile.pan_max - profile.pan_min).abs() / profile.pan_speed)
            .max((profile.tilt_max - profile.tilt_min).abs() / profile.tilt_speed)
            .clamp(0.25, 60.0);
        for _ in 0..profile.cycles {
            for (pan, tilt) in [
                (profile.pan_min, profile.tilt_min),
                (profile.pan_max, profile.tilt_max),
            ] {
                if token.load(Ordering::SeqCst) != generation {
                    break;
                }
                let pan_command = format!("$x,{pan:.2},{:.2}#", profile.pan_speed);
                let tilt_command = format!("$X,{tilt:.2},{:.2}#", profile.tilt_speed);
                if send_service_command(&ip, port, &pan_command).is_err()
                    || send_service_command(&ip, port, &tilt_command).is_err()
                {
                    token.fetch_add(1, Ordering::SeqCst);
                    break;
                }
                if !wait_interruptible(&token, generation, travel_seconds + profile.pause_seconds) {
                    break;
                }
            }
            if token.load(Ordering::SeqCst) != generation {
                break;
            }
        }
        let _ = send_service_command(&ip, port, "$u#");
        let _ = send_service_command(&ip, port, "$U#");
    });
    Ok(())
}

#[tauri::command]
fn stop_rocking(
    state: tauri::State<'_, RockingState>,
    ip: String,
    port: u16,
) -> Result<(), String> {
    state.generation.fetch_add(1, Ordering::SeqCst);
    platform_stop(ip, port)
}

#[tauri::command]
fn discover_devices(app: AppHandle) -> Result<Vec<DeviceSummary>, String> {
    let config = read_config(&app)?.unwrap_or(Value::Null);
    let devices = vec![
        DeviceSummary {
            id: "camera1".into(),
            name: "CAM 01".into(),
            kind: "camera".into(),
            ip: value_at(&config, "/cameras/0/ip", "192.168.1.68"),
            port: port_at(&config, "/cameras/0/onvifPort", 80),
            protocol: "ONVIF / RTSP".into(),
            connected: false,
        },
        DeviceSummary {
            id: "camera2".into(),
            name: "CAM 02".into(),
            kind: "camera".into(),
            ip: value_at(&config, "/cameras/1/ip", "192.168.1.108"),
            port: port_at(&config, "/cameras/1/onvifPort", 80),
            protocol: "ONVIF / RTSP".into(),
            connected: false,
        },
        DeviceSummary {
            id: "platform".into(),
            name: "TL.0009".into(),
            kind: "platform".into(),
            ip: value_at(&config, "/platformIp", "192.168.1.115"),
            port: port_at(&config, "/platformPort", 9762),
            protocol: "SERVICE TCP".into(),
            connected: false,
        },
        DeviceSummary {
            id: "rangefinder".into(),
            name: "Дальномер".into(),
            kind: "rangefinder".into(),
            ip: value_at(&config, "/rangefinderIp", "192.168.1.7"),
            port: port_at(&config, "/rangefinderPort", 20108),
            protocol: "TCP".into(),
            connected: false,
        },
        DeviceSummary {
            id: "relay".into(),
            name: "Relay X3".into(),
            kind: "relay".into(),
            ip: value_at(&config, "/relayIp", "192.168.127.254"),
            port: port_at(&config, "/relayPort", 9762),
            protocol: "PELCO-D".into(),
            connected: false,
        },
    ];

    let (sender, receiver) = mpsc::channel();
    let count = devices.len();
    for mut device in devices {
        let sender = sender.clone();
        thread::spawn(move || {
            device.connected = can_connect(&device.ip, device.port);
            let _ = sender.send(device);
        });
    }
    drop(sender);

    let mut found = Vec::with_capacity(count);
    for _ in 0..count {
        if let Ok(device) = receiver.recv_timeout(Duration::from_secs(1)) {
            found.push(device);
        }
    }
    found.sort_by_key(|device| match device.id.as_str() {
        "camera1" => 0,
        "camera2" => 1,
        "platform" => 2,
        "rangefinder" => 3,
        _ => 4,
    });
    Ok(found)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(RockingState::default())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            get_config,
            save_config,
            get_secret,
            set_secret,
            discover_devices,
            platform_jog,
            platform_stop,
            platform_self_test,
            camera_lens_step,
            start_rocking,
            stop_rocking
        ])
        .run(tauri::generate_context!())
        .expect("error while running ONCAM cockpit");
}
