//! Radiometric temperatures read from the thermal camera itself.
//!
//! The H.264 picture carries no temperatures: it is an 8-bit image after the camera's automatic gain,
//! so a pixel brightness says nothing about degrees. Temperatures come only from a radiometric camera
//! over its HTTP API (Dahua family: `RadiometryManager.cgi`). A camera without it gets no numbers.
//!
//! Verified on the stand's thermal camera (OEM «General IP Camera», iRay FT640 core, firmware
//! 1.030 build 2022-08-03): `getRandomPointTemper` answers in 30–60 ms with 0.1° resolution. Its
//! answer is labelled `Centigrade`, yet a 19–20 °C room reads 66–68: the values look like °F, so the
//! unit can be overridden per camera (`unit`).
//!
//! The HTTP API checks the camera's web accounts, which this firmware keeps apart from its ONVIF
//! users: the web password is stored as «<camera>-web» and falls back to the camera password.
//! Requests go over a plain TCP socket (system proxies must not see camera traffic) with HTTP Digest
//! authentication. A refused password is never retried: these cameras lock the account after a few
//! failures, so measuring stays stopped until the operator saves a password (`thermal_reset`).

use crate::onvif::{dechunk, response_complete};
use std::{
    collections::HashMap,
    io::{Read, Write},
    net::{SocketAddr, TcpStream},
    sync::{Arc, Mutex},
    time::Duration,
};
use tauri::State;

const HTTP_TIMEOUT: Duration = Duration::from_secs(3);
const MAX_RESPONSE_BYTES: usize = 2 * 1024 * 1024;
/// The single-sensor thermal camera measures on channel 1.
const CHANNEL: u32 = 1;
/// The API addresses the frame in relative coordinates 0…8191 on both axes.
const COORDINATE_MAX: f64 = 8191.0;
/// Three spots plus the hottest and the coldest point, with room to spare.
const MAX_POINTS: usize = 8;

pub(crate) struct Response {
    pub status: u16,
    pub head: String,
    pub body: String,
    #[cfg_attr(not(test), allow(dead_code))]
    pub raw: Vec<u8>,
}

fn exchange(address: SocketAddr, path: &str, authorization: Option<&str>) -> Result<Response, String> {
    let mut stream = TcpStream::connect_timeout(&address, HTTP_TIMEOUT).map_err(|error| format!("{address}: {error}"))?;
    stream.set_read_timeout(Some(HTTP_TIMEOUT)).map_err(|error| error.to_string())?;
    stream.set_write_timeout(Some(HTTP_TIMEOUT)).map_err(|error| error.to_string())?;
    let auth = authorization.map(|value| format!("Authorization: {value}\r\n")).unwrap_or_default();
    let request = format!("GET {path} HTTP/1.1\r\nHost: {address}\r\n{auth}Connection: close\r\n\r\n");
    stream.write_all(request.as_bytes()).map_err(|error| error.to_string())?;
    let mut response = Vec::new();
    let mut buffer = [0_u8; 8192];
    loop {
        match stream.read(&mut buffer) {
            Ok(0) => break,
            Ok(count) => {
                response.extend_from_slice(&buffer[..count]);
                if response.len() > MAX_RESPONSE_BYTES {
                    return Err("слишком большой ответ камеры".into());
                }
                if response_complete(&response) {
                    break;
                }
            }
            Err(error) if !response.is_empty() && matches!(error.kind(), std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut) => break,
            Err(error) => return Err(format!("{address}: {error}")),
        }
    }
    let split = response.windows(4).position(|window| window == b"\r\n\r\n").ok_or("некорректный HTTP-ответ камеры")?;
    let head = String::from_utf8_lossy(&response[..split]).to_string();
    let status = head.split_whitespace().nth(1).and_then(|code| code.parse::<u16>().ok()).ok_or("некорректный HTTP-ответ камеры")?;
    let raw = &response[split + 4..];
    let body = if head.to_ascii_lowercase().contains("transfer-encoding: chunked") { dechunk(raw) } else { raw.to_vec() };
    Ok(Response { status, head, body: String::from_utf8_lossy(&body).to_string(), raw: body })
}

fn header<'a>(head: &'a str, name: &str) -> Option<&'a str> {
    head.lines().find_map(|line| {
        let (key, value) = line.split_once(':')?;
        key.trim().eq_ignore_ascii_case(name).then(|| value.trim())
    })
}

/// One camera's HTTP session: the digest challenge is kept, so a poll costs one round trip.
pub(crate) struct Session {
    address: SocketAddr,
    username: String,
    password: String,
    client: Option<http_auth::PasswordClient>,
}

#[derive(Debug)]
pub(crate) enum HttpError {
    Unauthorized,
    Other(String),
}

impl Session {
    pub fn new(address: SocketAddr, username: String, password: String) -> Session {
        Session { address, username, password, client: None }
    }

    fn authorization(&mut self, path: &str) -> Result<Option<String>, HttpError> {
        let Some(client) = self.client.as_mut() else { return Ok(None) };
        client
            .respond(&http_auth::PasswordParams { username: &self.username, password: &self.password, uri: path, method: "GET", body: Some(&[]) })
            .map(Some)
            .map_err(HttpError::Other)
    }

    /// GET with digest authentication. A cached challenge that expired is renewed; a request refused
    /// with a fresh challenge means the password is wrong and is reported without another attempt.
    pub fn get(&mut self, path: &str) -> Result<Response, HttpError> {
        let mut fresh = false;
        loop {
            let authorization = self.authorization(path)?;
            let response = exchange(self.address, path, authorization.as_deref()).map_err(HttpError::Other)?;
            // This firmware refuses a wrong web password with 200 «Invalid Authority!» (a malformed
            // request gets the same answer); with a wrong password every such answer counts towards
            // the lockout, so it ends the session as well.
            if response.status != 401 && !response.body.contains("Invalid Authority") {
                return Ok(response);
            }
            if response.status != 401 || fresh {
                self.client = None;
                return Err(HttpError::Unauthorized);
            }
            let challenge = header(&response.head, "WWW-Authenticate").ok_or_else(|| HttpError::Other("камера требует авторизацию без WWW-Authenticate".into()))?;
            self.client = Some(http_auth::PasswordClient::try_from(challenge).map_err(HttpError::Other)?);
            fresh = true;
        }
    }
}

/// `key=value` lines of a Dahua CGI answer.
pub(crate) fn key_values(body: &str) -> Vec<(&str, &str)> {
    body.lines().filter_map(|line| line.split_once('=')).map(|(key, value)| (key.trim(), value.trim())).collect()
}

/// How to read the camera's numbers: as labelled, or as °C / °F whatever the label says.
#[derive(Clone, Copy, Debug, PartialEq, Eq, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub enum Unit {
    Camera,
    Celsius,
    Fahrenheit,
}

/// Value and unit label of a `getRandomPointTemper` answer, e.g.
/// `pointTempInfo.TemperAver=67.699997` and `pointTempInfo.TemperatureUnit=Centigrade`.
fn parse_point(body: &str) -> Result<(f64, String), String> {
    let pairs = key_values(body);
    let field = |suffix: &str| pairs.iter().find(|(key, _)| key.to_ascii_lowercase().ends_with(suffix)).map(|(_, value)| *value);
    match field(".temperaver").and_then(|value| value.parse::<f64>().ok()).filter(|value| value.is_finite()) {
        Some(value) => Ok((value, field(".temperatureunit").unwrap_or("Centigrade").to_string())),
        None => Err(body.lines().map(str::trim).find(|line| !line.is_empty() && *line != "Error").unwrap_or("пустой ответ").chars().take(120).collect()),
    }
}

fn to_celsius(value: f64, label: &str, unit: Unit) -> Result<f64, String> {
    let celsius = match unit {
        Unit::Celsius => value,
        Unit::Fahrenheit => (value - 32.0) * 5.0 / 9.0,
        Unit::Camera => match label.to_ascii_lowercase().as_str() {
            "centigrade" | "celsius" => value,
            "fahrenheit" => (value - 32.0) * 5.0 / 9.0,
            "kelvin" => value - 273.15,
            other => return Err(format!("неизвестная единица температуры «{other}»")),
        },
    };
    Ok((celsius * 10.0).round() / 10.0)
}

/// Relative API coordinate of a point given as a fraction of the frame (0…1).
fn coordinate(fraction: f64) -> u32 {
    (fraction.clamp(0.0, 1.0) * COORDINATE_MAX).round() as u32
}

#[derive(Default)]
struct CameraThermal {
    target: Option<(SocketAddr, String)>,
    session: Option<Session>,
    /// Why measuring stopped (password refused, no radiometry): kept until `thermal_reset`.
    blocked: Option<String>,
}

#[derive(Default)]
pub struct Thermal {
    cameras: Mutex<HashMap<String, Arc<Mutex<CameraThermal>>>>,
}

impl Thermal {
    fn camera(&self, camera_id: &str) -> Arc<Mutex<CameraThermal>> {
        let mut cameras = self.cameras.lock().unwrap_or_else(|poison| poison.into_inner());
        Arc::clone(cameras.entry(camera_id.to_string()).or_default())
    }
}

enum Failure {
    /// The camera must not be asked again until the operator acts.
    Block(String),
    /// Network trouble or a refused request: the next call tries again.
    Transient(String),
}

const REFUSED: &str = "камера отклонила пароль веб-интерфейса: обращения к камере остановлены до сохранения пароля";

/// Runs `work` with the camera's HTTP session. A refused password (or any other `Block`) is kept:
/// later calls fail at once without contacting the camera until `thermal_reset`.
fn with_session<T>(
    state: &mut CameraThermal,
    address: SocketAddr,
    username: &str,
    password: &dyn Fn() -> Result<String, String>,
    work: impl FnOnce(&mut Session) -> Result<T, Failure>,
) -> Result<T, String> {
    let target = (address, username.to_string());
    if state.target.as_ref() != Some(&target) {
        *state = CameraThermal { target: Some(target), ..CameraThermal::default() };
    }
    if let Some(reason) = &state.blocked {
        return Err(reason.clone());
    }
    if state.session.is_none() {
        state.session = Some(Session::new(address, username.to_string(), password()?));
    }
    match work(state.session.as_mut().expect("session was just created")) {
        Ok(value) => Ok(value),
        Err(Failure::Transient(error)) => Err(error),
        Err(Failure::Block(reason)) => {
            eprintln!("[thermal] {address}: {reason}");
            state.session = None;
            state.blocked = Some(reason.clone());
            Err(reason)
        }
    }
}

/// GET that must answer 200; a refused password blocks the camera.
fn get_ok(session: &mut Session, path: &str) -> Result<String, Failure> {
    match session.get(path) {
        Ok(response) if response.status == 200 => Ok(response.body),
        Ok(response) => Err(Failure::Transient(format!("HTTP {}", response.status))),
        Err(HttpError::Unauthorized) => Err(Failure::Block(REFUSED.into())),
        Err(HttpError::Other(error)) => Err(Failure::Transient(error)),
    }
}

/// Temperatures (°C) of `points` (fractions of the frame), one request per point.
fn measure(state: &mut CameraThermal, address: SocketAddr, username: &str, points: &[[f64; 2]], unit: Unit, password: &dyn Fn() -> Result<String, String>) -> Result<Vec<f64>, String> {
    with_session(state, address, username, password, |session| {
        points
            .iter()
            .map(|&[x, y]| {
                let path = format!("/cgi-bin/RadiometryManager.cgi?action=getRandomPointTemper&channel={CHANNEL}&coordinate[0]={}&coordinate[1]={}", coordinate(x), coordinate(y));
                match session.get(&path) {
                    Ok(response) if response.status == 200 => parse_point(&response.body)
                        .map_err(|detail| Failure::Block(format!("камера не отдаёт температуру точки ({detail})")))
                        .and_then(|(value, label)| to_celsius(value, &label, unit).map_err(Failure::Block)),
                    Ok(response) => Err(Failure::Block(format!("камера не отдаёт температуру точки (HTTP {})", response.status))),
                    Err(HttpError::Unauthorized) => Err(Failure::Block(REFUSED.into())),
                    Err(HttpError::Other(error)) => Err(Failure::Transient(error)),
                }
            })
            .collect()
    })
}

/// Measuring parameters kept by the camera (`HeatImagingThermometry`); `None` where the camera has
/// no such field. Temperatures are in the camera's unit (it reports `Centigrade`).
#[derive(Clone, Debug, Default, PartialEq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct MeasureParams {
    pub emissivity: Option<f64>,
    /// Metres; the camera keeps it as `ObjectDistance` (whole metres) + `DistanceDecimalPart`.
    pub distance: Option<f64>,
    pub reflected_temperature: Option<f64>,
    pub atmospheric_temperature: Option<f64>,
    pub transmissivity: Option<f64>,
    /// Percent.
    pub humidity: Option<f64>,
}

const PARAMS_CONFIG: &str = "HeatImagingThermometry";

/// Fields, their camera keys and the ranges the camera advertises (`RadiometryManager getCaps`).
const PARAM_FIELDS: [(&str, &str, f64, f64); 5] = [
    ("emissivity", "ObjectEmissivity", 0.01, 1.0),
    ("reflectedTemperature", "ReflectedTemperature", -50.0, 327.7),
    ("atmosphericTemperature", "AtmosphericTemperature", -50.0, 327.7),
    ("transmissivity", "AtmosphericTransmissivity", 0.0, 1.0),
    ("humidity", "RelativeHumidity", 0.0, 100.0),
];
const DISTANCE_RANGE: (f64, f64) = (0.0, 10_000.0);

fn parse_params(body: &str) -> MeasureParams {
    let pairs = key_values(body);
    let field = |key: &str| {
        let suffix = format!(".{PARAMS_CONFIG}.{key}").to_ascii_lowercase();
        pairs.iter().find(|(name, _)| name.to_ascii_lowercase().ends_with(&suffix)).and_then(|(_, value)| value.parse::<f64>().ok()).filter(|value| value.is_finite())
    };
    let round = |value: f64, digits: i32| (value * 10_f64.powi(digits)).round() / 10_f64.powi(digits);
    MeasureParams {
        emissivity: field("ObjectEmissivity").map(|value| round(value, 2)),
        distance: field("ObjectDistance").map(|whole| round(whole + field("DistanceDecimalPart").unwrap_or(0.0), 1)),
        reflected_temperature: field("ReflectedTemperature").map(|value| round(value, 1)),
        atmospheric_temperature: field("AtmosphericTemperature").map(|value| round(value, 1)),
        transmissivity: field("AtmosphericTransmissivity").map(|value| round(value, 2)),
        humidity: field("RelativeHumidity").map(|value| round(value, 0)),
    }
}

/// Query of a `configManager setConfig` call for the given fields; ranges are checked first.
fn params_query(params: &MeasureParams) -> Result<String, String> {
    let values = [params.emissivity, params.reflected_temperature, params.atmospheric_temperature, params.transmissivity, params.humidity];
    let mut parts = Vec::new();
    for ((name, key, min, max), value) in PARAM_FIELDS.iter().zip(values) {
        let Some(value) = value else { continue };
        if !value.is_finite() || value < *min || value > *max {
            return Err(format!("{name}: допустимо от {min} до {max}"));
        }
        parts.push(format!("{PARAMS_CONFIG}.{key}={value}"));
    }
    if let Some(distance) = params.distance {
        if !distance.is_finite() || distance < DISTANCE_RANGE.0 || distance > DISTANCE_RANGE.1 {
            return Err(format!("distance: допустимо от {} до {} м", DISTANCE_RANGE.0, DISTANCE_RANGE.1));
        }
        // As the camera's own web page writes it: whole metres and the tenths apart.
        let tenths = (distance * 10.0).round() as i64;
        parts.push(format!("{PARAMS_CONFIG}.ObjectDistance={}", tenths / 10));
        parts.push(format!("{PARAMS_CONFIG}.DistanceDecimalPart={}", (tenths % 10) as f64 / 10.0));
    }
    if parts.is_empty() {
        return Err("нечего записывать".into());
    }
    Ok(format!("/cgi-bin/configManager.cgi?action=setConfig&{}", parts.join("&")))
}

fn read_params(session: &mut Session) -> Result<MeasureParams, Failure> {
    let body = get_ok(session, &format!("/cgi-bin/configManager.cgi?action=getConfig&name={PARAMS_CONFIG}"))?;
    let params = parse_params(&body);
    if params == MeasureParams::default() {
        return Err(Failure::Transient(format!("камера не сообщает параметры измерения ({})", body.lines().map(str::trim).find(|line| !line.is_empty() && *line != "Error").unwrap_or("пустой ответ"))));
    }
    Ok(params)
}

/// The web password («<camera>-web»), or the camera password when no separate one is stored.
fn web_password(camera_id: &str) -> Result<String, String> {
    for id in [format!("{camera_id}-web"), camera_id.to_string()] {
        match crate::keyring_entry(&id)?.get_password() {
            Ok(password) => return Ok(password),
            Err(keyring::Error::NoEntry) => continue,
            Err(error) => return Err(error.to_string()),
        }
    }
    Err("пароль камеры не задан".into())
}

fn check_camera(camera_id: &str, username: &str, ip: &str, port: u16) -> Result<SocketAddr, String> {
    if !matches!(camera_id, "camera1" | "camera2") {
        return Err("Неизвестная камера".into());
    }
    if username.is_empty() || username.len() > 64 {
        return Err("Задайте логин камеры".into());
    }
    crate::validate_target(ip, port)
}

#[tauri::command]
pub async fn thermal_measure(
    thermal: State<'_, Arc<Thermal>>,
    camera_id: String,
    ip: String,
    port: u16,
    username: String,
    points: Vec<[f64; 2]>,
    unit: Unit,
) -> Result<Vec<f64>, String> {
    let address = check_camera(&camera_id, &username, &ip, port)?;
    if points.len() > MAX_POINTS || points.iter().flatten().any(|value| !(0.0..=1.0).contains(value)) {
        return Err("Некорректные точки измерения".into());
    }
    let camera = thermal.camera(&camera_id);
    crate::run_blocking(move || {
        let mut state = camera.lock().unwrap_or_else(|poison| poison.into_inner());
        measure(&mut state, address, &username, &points, unit, &|| web_password(&camera_id))
    })
    .await
}

/// The camera's measuring parameters (emissivity, distance, reflected and air temperature, …).
#[tauri::command]
pub async fn thermal_params_get(thermal: State<'_, Arc<Thermal>>, camera_id: String, ip: String, port: u16, username: String) -> Result<MeasureParams, String> {
    let address = check_camera(&camera_id, &username, &ip, port)?;
    let camera = thermal.camera(&camera_id);
    crate::run_blocking(move || {
        let mut state = camera.lock().unwrap_or_else(|poison| poison.into_inner());
        with_session(&mut state, address, &username, &|| web_password(&camera_id), read_params)
    })
    .await
}

/// Writes the given parameters into the camera (fields left `None` stay as they are) and returns
/// what the camera holds afterwards.
#[tauri::command]
pub async fn thermal_params_set(thermal: State<'_, Arc<Thermal>>, camera_id: String, ip: String, port: u16, username: String, params: MeasureParams) -> Result<MeasureParams, String> {
    let address = check_camera(&camera_id, &username, &ip, port)?;
    let query = params_query(&params)?;
    let camera = thermal.camera(&camera_id);
    crate::run_blocking(move || {
        let mut state = camera.lock().unwrap_or_else(|poison| poison.into_inner());
        with_session(&mut state, address, &username, &|| web_password(&camera_id), |session| {
            let answer = get_ok(session, &query)?;
            if answer.trim() != "OK" {
                return Err(Failure::Transient(format!("камера не приняла параметры ({})", answer.lines().map(str::trim).find(|line| !line.is_empty() && *line != "Error").unwrap_or("пустой ответ"))));
            }
            eprintln!("[thermal] {address}: параметры измерения записаны: {query}");
            read_params(session)
        })
    })
    .await
}

/// Forgets a refused password or a missing radiometry verdict: the next poll asks the camera again.
#[tauri::command]
pub fn thermal_reset(thermal: State<'_, Arc<Thermal>>, camera_id: String) {
    thermal.cameras.lock().unwrap_or_else(|poison| poison.into_inner()).remove(&camera_id);
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{net::TcpListener, sync::atomic::{AtomicUsize, Ordering}, thread};

    #[test]
    fn dahua_answer_is_split_into_pairs() {
        let pairs = key_values("PointTemperInfo.Type=1\r\nPointTemperInfo.TemperAver=36.5\r\n");
        assert_eq!(pairs, vec![("PointTemperInfo.Type", "1"), ("PointTemperInfo.TemperAver", "36.5")]);
    }

    #[test]
    fn point_answer_of_the_stand_camera_is_parsed() {
        let body = "pointTempInfo.TemperAver=67.699997\r\npointTempInfo.TemperatureUnit=Centigrade\r\npointTempInfo.Type=Spot\r\n";
        assert_eq!(parse_point(body), Ok((67.699997, "Centigrade".to_string())));
        assert_eq!(parse_point("Error\r\nErrorID=2, Detail=Invalid Request!\r\n"), Err("ErrorID=2, Detail=Invalid Request!".to_string()));
    }

    #[test]
    fn units_follow_the_label_or_the_override() {
        assert_eq!(to_celsius(67.699997, "Centigrade", Unit::Camera), Ok(67.7));
        assert_eq!(to_celsius(67.699997, "Centigrade", Unit::Fahrenheit), Ok(19.8));
        assert_eq!(to_celsius(98.6, "Fahrenheit", Unit::Camera), Ok(37.0));
        assert_eq!(to_celsius(300.0, "Kelvin", Unit::Camera), Ok(26.9));
        assert!(to_celsius(1.0, "Rankine", Unit::Camera).is_err());
    }

    /// `getConfig&name=HeatImagingThermometry` of the stand camera (2026-10-01), abridged.
    const STAND_PARAMS: &str = "table.HeatImagingThermometry.Altitude=100\r\ntable.HeatImagingThermometry.AtmosphericTemperature=23.000000\r\n\
        table.HeatImagingThermometry.AtmosphericTransmissivity=1.000000\r\ntable.HeatImagingThermometry.DistanceDecimalPart=0.500000\r\n\
        table.HeatImagingThermometry.Isotherm.MaxLimitTemp=140\r\ntable.HeatImagingThermometry.ObjectDistance=5\r\n\
        table.HeatImagingThermometry.ObjectEmissivity=0.980000\r\ntable.HeatImagingThermometry.ReflectedTemperature=23.000000\r\n\
        table.HeatImagingThermometry.RelativeHumidity=60\r\ntable.HeatImagingThermometry.TemperatureUnit=Centigrade\r\n";

    #[test]
    fn camera_parameters_are_read_with_the_split_distance() {
        let params = parse_params(STAND_PARAMS);
        assert_eq!(
            params,
            MeasureParams {
                emissivity: Some(0.98),
                distance: Some(5.5),
                reflected_temperature: Some(23.0),
                atmospheric_temperature: Some(23.0),
                transmissivity: Some(1.0),
                humidity: Some(60.0),
            }
        );
        assert_eq!(parse_params("Error\r\nErrorID=2, Detail=Invalid Request!\r\n"), MeasureParams::default());
    }

    #[test]
    fn parameters_are_written_as_the_camera_page_writes_them() {
        let query = params_query(&MeasureParams { emissivity: Some(0.95), distance: Some(12.3), ..MeasureParams::default() }).unwrap();
        assert_eq!(
            query,
            "/cgi-bin/configManager.cgi?action=setConfig&HeatImagingThermometry.ObjectEmissivity=0.95&HeatImagingThermometry.ObjectDistance=12&HeatImagingThermometry.DistanceDecimalPart=0.3"
        );
        assert!(params_query(&MeasureParams { emissivity: Some(1.5), ..MeasureParams::default() }).is_err());
        assert!(params_query(&MeasureParams { distance: Some(-1.0), ..MeasureParams::default() }).is_err());
        assert!(params_query(&MeasureParams::default()).is_err());
    }

    #[test]
    fn frame_fractions_map_onto_the_8192_grid() {
        assert_eq!((coordinate(0.0), coordinate(0.5), coordinate(1.0), coordinate(1.5)), (0, 4096, 8191, 8191));
    }

    /// A camera that challenges every request without credentials and refuses every password the
    /// way the stand camera does («Invalid Authority!» with HTTP 200). Returns its port and the
    /// number of requests that carried credentials.
    fn refusing_camera() -> (SocketAddr, Arc<AtomicUsize>) {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let attempts = Arc::new(AtomicUsize::new(0));
        let counter = Arc::clone(&attempts);
        thread::spawn(move || {
            for stream in listener.incoming() {
                let mut stream = stream.unwrap();
                let mut request = Vec::new();
                let mut buffer = [0_u8; 1024];
                while !request.windows(4).any(|window| window == b"\r\n\r\n") {
                    let count = stream.read(&mut buffer).unwrap();
                    if count == 0 {
                        break;
                    }
                    request.extend_from_slice(&buffer[..count]);
                }
                let answer = if String::from_utf8_lossy(&request).contains("Authorization: Digest") {
                    counter.fetch_add(1, Ordering::SeqCst);
                    let body = "Error\r\nErrorID=0, Detail=Invalid Authority!\r\n";
                    format!("HTTP/1.1 200 OK\r\nContent-Length: {}\r\n\r\n{body}", body.len())
                } else {
                    "HTTP/1.1 401 Unauthorized\r\nWWW-Authenticate: Digest realm=\"Login to TEST\",qop=\"auth\",nonce=\"1\",opaque=\"x\"\r\nContent-Length: 0\r\n\r\n".to_string()
                };
                stream.write_all(answer.as_bytes()).unwrap();
            }
        });
        (address, attempts)
    }

    #[test]
    fn a_refused_password_is_tried_once_and_never_again() {
        let (address, attempts) = refusing_camera();
        let mut state = CameraThermal::default();
        let password = || Ok("wrong".to_string());
        let points = [[0.5, 0.5], [0.1, 0.1], [0.9, 0.9]];
        let first = measure(&mut state, address, "admin", &points, Unit::Camera, &password).unwrap_err();
        assert!(first.contains("отклонила пароль"), "{first}");
        for _ in 0..3 {
            assert_eq!(measure(&mut state, address, "admin", &points, Unit::Camera, &password).unwrap_err(), first);
        }
        assert_eq!(attempts.load(Ordering::SeqCst), 1, "one failed login per saved password, not one per point or poll");
        // Another address or login is another account: it gets its own single attempt.
        let _ = measure(&mut state, address, "operator", &points, Unit::Camera, &password);
        assert_eq!(attempts.load(Ordering::SeqCst), 2);
    }

    /// Read-only probe of a thermal camera's HTTP API (`MKIS_HTTP=camera2-web@192.168.1.107:80`):
    /// which radiometry calls it answers (`MKIS_PATHS` = paths separated by `|`, `MKIS_USER`,
    /// `MKIS_SAVE` = directory for binary answers such as snapshots). The password comes from the
    /// keychain and is never printed; the probe stops at the first refusal.
    #[test]
    #[ignore]
    fn real_radiometry() {
        let spec = std::env::var("MKIS_HTTP").expect("MKIS_HTTP=camera2-web@ip:port");
        let (id, target) = spec.split_once('@').unwrap();
        let address: SocketAddr = target.parse().unwrap();
        let password = crate::keyring_entry(id).unwrap().get_password().unwrap();
        let username = std::env::var("MKIS_USER").unwrap_or_else(|_| "admin".into());
        let mut session = Session::new(address, username, password);
        let extra: Vec<String> = std::env::var("MKIS_PATHS").map(|value| value.split('|').map(String::from).collect()).unwrap_or_default();
        let defaults = [
            "/cgi-bin/magicBox.cgi?action=getSystemInfo",
            "/cgi-bin/RadiometryManager.cgi?action=getCaps&channel=1",
            "/cgi-bin/configManager.cgi?action=getConfig&name=HeatImagingThermometry",
            "/cgi-bin/RadiometryManager.cgi?action=getRandomPointTemper&channel=1&coordinate[0]=4096&coordinate[1]=4096",
        ];
        let paths: Vec<String> = if extra.is_empty() { defaults.iter().map(|path| path.to_string()).collect() } else { extra };
        for path in paths {
            let started = std::time::Instant::now();
            match session.get(&path) {
                Ok(response) => {
                    let text = response.raw.iter().take(4096).all(|&byte| matches!(byte, b'\t' | b'\r' | b'\n' | 0x20..=0x7e));
                    let content = header(&response.head, "Content-Type").unwrap_or("").to_string();
                    println!("\n=== {path}\nHTTP {} — {:?} · {content} · {} байт", response.status, started.elapsed(), response.raw.len());
                    if text {
                        println!("{}", response.body);
                    } else if let Ok(directory) = std::env::var("MKIS_SAVE") {
                        let name: String = path.chars().map(|c| if c.is_ascii_alphanumeric() { c } else { '_' }).collect();
                        let file = std::path::Path::new(&directory).join(format!("{}.bin", &name[name.len().saturating_sub(60)..]));
                        std::fs::write(&file, &response.raw).unwrap();
                        println!("двоичный ответ сохранён: {}", file.display());
                    }
                }
                Err(HttpError::Unauthorized) => {
                    println!("\n=== {path}\nпароль отклонён — дальше не пробую");
                    return;
                }
                Err(HttpError::Other(error)) => println!("\n=== {path}\nошибка: {error}"),
            }
        }
    }
}
