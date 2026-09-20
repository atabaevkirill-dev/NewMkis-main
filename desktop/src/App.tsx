import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlignCenter,
  Aperture,
  Camera,
  ChevronDown,
  CircleDot,
  Crosshair,
  Eye,
  EyeOff,
  FolderOpen,
  Gauge,
  GripVertical,
  Layers3,
  LocateFixed,
  PanelTopOpen,
  Play,
  Radio,
  RefreshCw,
  Save,
  Settings2,
  SlidersHorizontal,
  Square,
  TestTube2,
  Video,
  X,
  Zap,
} from "lucide-react";
import {
  chooseRecordingDirectory,
  cameraLensStep,
  defaultConfig,
  discoverDevices,
  getSecret,
  loadConfig,
  persistConfig,
  platformJog,
  platformStop,
  runPlatformSelfTest,
  setSecret,
  startRockingProfile,
  stopRockingProfile,
} from "./api";
import type { AppConfig, CameraConfig, DeviceSummary, RockingProfile } from "./types";

type Drawer = "camera1" | "camera2" | null;
type SystemTab = "summary" | "platform" | "tests" | "record";

const cloneDefaults = (): AppConfig => structuredClone(defaultConfig);

function Toggle({ value, onChange, label }: { value: boolean; onChange: (value: boolean) => void; label?: string }) {
  return (
    <button className={`toggle ${value ? "is-on" : ""}`} onClick={() => onChange(!value)} type="button" aria-pressed={value}>
      <span />{label && <em>{label}</em>}
    </button>
  );
}

function LabeledField({ label, children, wide = false }: { label: string; children: React.ReactNode; wide?: boolean }) {
  return <label className={`field ${wide ? "wide" : ""}`}><span>{label}</span>{children}</label>;
}

function Metric({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "neutral" | "blue" | "amber" }) {
  return <div className={`metric ${tone}`}><span>{label}</span><strong>{value}</strong></div>;
}

function SecretField({ cameraId }: { cameraId: string }) {
  const [visible, setVisible] = useState(false);
  const [password, setPassword] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => { void getSecret(cameraId).then(setPassword).catch(() => setPassword("")); }, [cameraId]);

  const save = async () => {
    await setSecret(cameraId, password);
    setSaved(true);
    window.setTimeout(() => setSaved(false), 1400);
  };

  return (
    <LabeledField label="Пароль" wide>
      <div className="input-action">
        <input type={visible ? "text" : "password"} value={password} placeholder="Хранится в системной связке ключей" onChange={(e) => setPassword(e.target.value)} />
        <button onClick={() => setVisible(!visible)} title={visible ? "Скрыть пароль" : "Показать пароль"} type="button">{visible ? <EyeOff /> : <Eye />}</button>
        <button onClick={() => void save()} title="Сохранить пароль" type="button">{saved ? <span className="saved-mark">OK</span> : <Save />}</button>
      </div>
    </LabeledField>
  );
}

function CameraDrawer({ camera, side, onClose, onChange, onScan }: {
  camera: CameraConfig;
  side: "left" | "right";
  onClose: () => void;
  onChange: (patch: Partial<CameraConfig>) => void;
  onScan: () => void;
}) {
  const accent = side === "left" ? "blue" : "amber";
  return (
    <aside className={`camera-drawer ${side} ${accent}`}>
      <div className="drawer-title">
        <div><small>{side === "left" ? "КАМЕРА 01" : "КАМЕРА 02"}</small><h2>{side === "left" ? "Оптическая" : "Тепловизионная"}</h2></div>
        <button className="icon-button" onClick={onClose} type="button"><X /></button>
      </div>

      <section className="panel-section">
        <div className="section-head"><span>Сеть и подключение</span><Radio /></div>
        <div className="form-grid">
          <LabeledField label="IP-адрес" wide><input value={camera.ip} onChange={(e) => onChange({ ip: e.target.value })} /></LabeledField>
          <LabeledField label="ONVIF"><input type="number" value={camera.onvifPort} onChange={(e) => onChange({ onvifPort: Number(e.target.value) })} /></LabeledField>
          <LabeledField label="RTSP"><input type="number" value={camera.rtspPort} onChange={(e) => onChange({ rtspPort: Number(e.target.value) })} /></LabeledField>
          <LabeledField label="Логин" wide><input value={camera.username} onChange={(e) => onChange({ username: e.target.value })} /></LabeledField>
          <SecretField cameraId={camera.id} />
        </div>
        <div className="inline-actions">
          <button className="secondary" onClick={onScan} type="button"><RefreshCw /> Найти</button>
          <button className="primary" type="button"><Zap /> Подключить</button>
        </div>
        <div className="setting-line"><span>Автоподключение</span><Toggle value={camera.autoConnect} onChange={(autoConnect) => onChange({ autoConnect })} /></div>
      </section>

      <section className="panel-section">
        <div className="section-head"><span>Объектив · ONVIF</span><Aperture /></div>
        <div className="control-row"><span>ZOOM</span><button type="button">−</button><input aria-label="Zoom" type="range" min="0" max="100" defaultValue="42" /><button type="button">+</button></div>
        <div className="control-row"><span>FOCUS</span><button type="button">−</button><input aria-label="Focus" type="range" min="0" max="100" defaultValue="58" /><button type="button">+</button></div>
        <div className="inline-actions three"><button type="button">AF</button><button type="button">Near</button><button type="button">Far</button></div>
        <p className="gesture-hint">Колесо над видео — ZOOM · ПКМ + колесо — FOCUS</p>
      </section>

      <section className="panel-section compact">
        <div className="setting-line"><span>OSD камеры <small>имя · FPS · ONVIF</small></span><Toggle value={camera.osd} onChange={(osd) => onChange({ osd })} /></div>
        <div className="setting-line"><span>Профиль</span><strong>{camera.profile}</strong></div>
      </section>
    </aside>
  );
}

function DeviceCard({ device }: { device: DeviceSummary }) {
  return (
    <article className="device-card">
      <span className={`device-dot ${device.connected ? "online" : "offline"}`} />
      <div><strong>{device.name}</strong><small>{device.protocol}</small></div>
      <code>{device.ip}:{device.port}</code>
      <b>{device.connected ? "СВЯЗЬ" : "НЕТ СВЯЗИ"}</b>
    </article>
  );
}

function NumberBox({ label, value, unit, onChange }: { label: string; value: number; unit: string; onChange: (value: number) => void }) {
  return <label className="number-box"><span>{label}</span><div><input type="number" value={value} onChange={(e) => onChange(Number(e.target.value))} /><em>{unit}</em></div></label>;
}

function SystemDrawer({ tab, setTab, config, devices, scanning, onScan, onClose, onConfig, recording, setRecording }: {
  tab: SystemTab;
  setTab: (tab: SystemTab) => void;
  config: AppConfig;
  devices: DeviceSummary[];
  scanning: boolean;
  onScan: () => void;
  onClose: () => void;
  onConfig: (next: AppConfig) => void;
  recording: boolean;
  setRecording: (value: boolean) => void;
}) {
  const [selectedProfile, setSelectedProfile] = useState(0);
  const [platformMessage, setPlatformMessage] = useState("ГОТОВ");
  const profile = config.profiles[selectedProfile];
  const patchProfile = (patch: Partial<RockingProfile>) => {
    const profiles = config.profiles.map((item, index) => index === selectedProfile ? { ...item, ...patch } : item);
    onConfig({ ...config, profiles });
  };
  const jog = async (direction: "left" | "right" | "up" | "down") => {
    setPlatformMessage("КОМАНДА…");
    try {
      await platformJog(config.platformIp, config.platformPort, direction, direction === "left" || direction === "right" ? profile.panSpeed : profile.tiltSpeed);
      setPlatformMessage(direction.toUpperCase());
    } catch (error) { setPlatformMessage(`ОШИБКА: ${String(error)}`); }
  };
  const stop = async () => {
    try { await platformStop(config.platformIp, config.platformPort); setPlatformMessage("STOP"); }
    catch (error) { setPlatformMessage(`ОШИБКА: ${String(error)}`); }
  };
  const startRocking = async () => {
    try { await startRockingProfile(config.platformIp, config.platformPort, profile); setPlatformMessage(`КАЧКА · ${profile.name}`); }
    catch (error) { setPlatformMessage(`ОШИБКА: ${String(error)}`); }
  };
  const stopRocking = async () => {
    try { await stopRockingProfile(config.platformIp, config.platformPort); setPlatformMessage("КАЧКА ОСТАНОВЛЕНА"); }
    catch (error) { setPlatformMessage(`ОШИБКА: ${String(error)}`); }
  };

  return (
    <section className="system-drawer">
      <div className="system-tabs">
        <button className={tab === "summary" ? "active" : ""} onClick={() => setTab("summary")}><Layers3 /> Сводка</button>
        <button className={tab === "platform" ? "active" : ""} onClick={() => setTab("platform")}><LocateFixed /> Поворотка</button>
        <button className={tab === "tests" ? "active" : ""} onClick={() => setTab("tests")}><TestTube2 /> Тесты</button>
        <button className={tab === "record" ? "active" : ""} onClick={() => setTab("record")}><Video /> Запись</button>
        <button className="close-system" onClick={onClose}><ChevronDown /></button>
      </div>

      {tab === "summary" && <div className="system-body summary-body">
        <div className="device-grid">{devices.map((device) => <DeviceCard key={device.id} device={device} />)}</div>
        <div className="summary-actions">
          <button className="primary" onClick={onScan}><RefreshCw className={scanning ? "spin" : ""} /> {scanning ? "Поиск…" : "Автопоиск"}</button>
          <div><span>Найдено</span><strong>{devices.filter((item) => item.connected).length}/{devices.length}</strong></div>
          <div><span>Автоподключение</span><strong>ВКЛ</strong></div>
        </div>
      </div>}

      {tab === "platform" && <div className="system-body platform-body">
        <div className="platform-live">
          <div className="section-head"><span>TL.0009 · SERVICE TCP</span><Radio /></div>
          <div className="address-line"><code>{config.platformIp}:{config.platformPort}</code><span>{platformMessage}</span></div>
          <div className="jog-grid">
            <i /><button onPointerDown={() => void jog("up")} onPointerUp={() => void stop()}>▲</button><i />
            <button onPointerDown={() => void jog("left")} onPointerUp={() => void stop()}>◀</button><button className="stop" onClick={() => void stop()}>STOP</button><button onPointerDown={() => void jog("right")} onPointerUp={() => void stop()}>▶</button>
            <i /><button onPointerDown={() => void jog("down")} onPointerUp={() => void stop()}>▼</button><i />
          </div>
          <button className="secondary full">Установить текущую позицию как ноль</button>
        </div>
        <div className="rocking-editor">
          <div className="profile-tabs">{config.profiles.map((item, index) => <button key={item.id} className={selectedProfile === index ? "active" : ""} onClick={() => setSelectedProfile(index)}>{index + 1}</button>)}</div>
          <div className="rocking-title"><div><small>РЕЖИМ КАЧКИ</small><input value={profile.name} onChange={(e) => patchProfile({ name: e.target.value })} /></div><Toggle value={profile.smoothMotion} onChange={(smoothMotion) => patchProfile({ smoothMotion })} label="Плавно" /></div>
          <div className="number-grid">
            <NumberBox label="PAN MIN" value={profile.panMin} unit="°" onChange={(panMin) => patchProfile({ panMin })} />
            <NumberBox label="PAN MAX" value={profile.panMax} unit="°" onChange={(panMax) => patchProfile({ panMax })} />
            <NumberBox label="PAN SPEED" value={profile.panSpeed} unit="°/s" onChange={(panSpeed) => patchProfile({ panSpeed })} />
            <NumberBox label="TILT MIN" value={profile.tiltMin} unit="°" onChange={(tiltMin) => patchProfile({ tiltMin })} />
            <NumberBox label="TILT MAX" value={profile.tiltMax} unit="°" onChange={(tiltMax) => patchProfile({ tiltMax })} />
            <NumberBox label="TILT SPEED" value={profile.tiltSpeed} unit="°/s" onChange={(tiltSpeed) => patchProfile({ tiltSpeed })} />
            <NumberBox label="ЦИКЛЫ" value={profile.cycles} unit="×" onChange={(cycles) => patchProfile({ cycles })} />
            <NumberBox label="ПАУЗА" value={profile.pauseSeconds} unit="s" onChange={(pauseSeconds) => patchProfile({ pauseSeconds })} />
          </div>
          <div className="inline-actions"><button className="primary" onClick={() => void startRocking()}><Play /> Запустить профиль</button><button className="danger" onClick={() => void stopRocking()}><Square /> Остановить</button></div>
        </div>
      </div>}

      {tab === "tests" && <div className="system-body tests-body">
        {[
          ["Камера 01", "ONVIF · RTSP · FPS · Zoom/Focus", "192.168.1.68"],
          ["Камера 02", "ONVIF · RTSP · FPS · Zoom/Focus", "192.168.1.108"],
          ["TL.0009", "Инициализация · ошибки · позиция · скорость", `${config.platformIp}:${config.platformPort}`],
          ["Дальномер", "TCP · запрос дистанции", "192.168.1.7:20108"],
          ["Relay X3", "Связь · команды · ответ", "192.168.127.254:9762"],
        ].map(([name, detail, ip]) => <article className="test-card" key={name}><TestTube2 /><div><strong>{name}</strong><small>{detail}</small></div><code>{ip}</code><button onClick={name === "TL.0009" ? async () => { try { const result = await runPlatformSelfTest(config.platformIp, config.platformPort); setPlatformMessage(result.join(" · ")); } catch (error) { setPlatformMessage(`ОШИБКА: ${String(error)}`); } } : undefined}>Тест</button></article>)}
        <button className="primary run-all"><Play /> Полный автоматический тест</button>
      </div>}

      {tab === "record" && <div className="system-body record-body">
        <div className="record-settings">
          <div className="camera-select">
            <button className={config.recording.camera1 ? "selected blue" : ""} onClick={() => onConfig({ ...config, recording: { ...config.recording, camera1: !config.recording.camera1 } })}><Camera /> CAM 01</button>
            <button className={config.recording.camera2 ? "selected amber" : ""} onClick={() => onConfig({ ...config, recording: { ...config.recording, camera2: !config.recording.camera2 } })}><Camera /> CAM 02</button>
          </div>
          <LabeledField label="Каталог записи" wide><div className="input-action"><input value={config.recording.directory} placeholder="Выберите каталог" readOnly /><button onClick={async () => { const path = await chooseRecordingDirectory(); if (path) onConfig({ ...config, recording: { ...config.recording, directory: path } }); }}><FolderOpen /></button></div></LabeledField>
          <div className="record-options">
            <LabeledField label="Формат"><select value={config.recording.format} onChange={(e) => onConfig({ ...config, recording: { ...config.recording, format: e.target.value as "mkv" | "mp4" } })}><option value="mkv">MKV</option><option value="mp4">MP4</option></select></LabeledField>
            <LabeledField label="Сегмент, мин"><input type="number" value={config.recording.segmentMinutes} onChange={(e) => onConfig({ ...config, recording: { ...config.recording, segmentMinutes: Number(e.target.value) } })} /></LabeledField>
          </div>
        </div>
        <div className="metadata-box">
          <h3>Сопроводительные данные</h3>
          <div className="setting-line"><span>IP, ONVIF, время, телеметрия TL.0009</span><Toggle value={config.recording.includeMetadata} onChange={(includeMetadata) => onConfig({ ...config, recording: { ...config.recording, includeMetadata } })} /></div>
          <div className="setting-line warning"><span>Пароли в зашифрованном manifest</span><Toggle value={config.recording.includeEncryptedSecrets} onChange={(includeEncryptedSecrets) => onConfig({ ...config, recording: { ...config.recording, includeEncryptedSecrets } })} /></div>
          <p>Пароли никогда не записываются открытым текстом.</p>
        </div>
        <button className={recording ? "danger record-main" : "primary record-main"} onClick={() => setRecording(!recording)}>{recording ? <><Square /> Остановить запись</> : <><CircleDot /> Начать запись</>}</button>
      </div>}
    </section>
  );
}

function VideoPane({ camera, variant, alignment, matched, onJog, onStop }: {
  camera: CameraConfig;
  variant: "optical" | "thermal";
  alignment: boolean;
  matched: boolean;
  onJog: (direction: "left" | "right" | "up" | "down") => void;
  onStop: () => void;
}) {
  const rightMouseDown = useRef(false);
  const indicatorTimer = useRef<number | null>(null);
  const [lensIndicator, setLensIndicator] = useState("");
  const showLensIndicator = (message: string) => {
    setLensIndicator(message);
    if (indicatorTimer.current) window.clearTimeout(indicatorTimer.current);
    indicatorTimer.current = window.setTimeout(() => setLensIndicator(""), 650);
  };
  const handleWheel = (event: React.WheelEvent<HTMLDivElement>) => {
    if ((event.target as HTMLElement).closest(".video-dpad")) return;
    event.preventDefault();
    const direction = event.deltaY < 0 ? 1 : -1;
    const mode = rightMouseDown.current ? "focus" : "zoom";
    showLensIndicator(mode === "zoom" ? `ZOOM ${direction > 0 ? "+" : "−"}` : `FOCUS ${direction > 0 ? "FAR" : "NEAR"}`);
    void cameraLensStep(camera.id, mode, direction).catch(() => showLensIndicator("ONVIF · НЕТ СВЯЗИ"));
  };
  const jogButton = (direction: "left" | "right" | "up" | "down", label: string) => (
    <button
      className={direction}
      onPointerDown={() => onJog(direction)}
      onPointerUp={onStop}
      onPointerCancel={onStop}
      onPointerLeave={onStop}
      aria-label={`Поворотка ${direction}`}
      type="button"
    >{label}</button>
  );
  return (
    <div
      className={`video-pane ${variant}`}
      onWheel={handleWheel}
      onContextMenu={(event) => event.preventDefault()}
      onPointerDown={(event) => { if (event.button === 2) rightMouseDown.current = true; }}
      onPointerUp={(event) => { if (event.button === 2) rightMouseDown.current = false; }}
      onPointerCancel={() => { rightMouseDown.current = false; }}
      onPointerLeave={() => { rightMouseDown.current = false; }}
    >
      <div className="video-noise" />
      <div className="reticle"><i /><i /><span /></div>
      {alignment && <div className={`alignment-cue ${matched ? "matched" : ""}`}><div className="reference-axis" /><div className="moving-axis" />{matched && <b>ОСИ СОВПАЛИ</b>}</div>}
      {camera.osd && <div className="camera-osd"><strong>{camera.name}</strong><span>25 FPS</span><span>ONVIF</span></div>}
      <div className="video-dpad" aria-label="Управление TL.0009 через сервисный протокол">
        <div>
          <i />{jogButton("up", "▲")}<i />
          {jogButton("left", "◀")}<button className="stop" onClick={onStop} type="button">■</button>{jogButton("right", "▶")}
          <i />{jogButton("down", "▼")}<i />
        </div>
      </div>
      {lensIndicator && <div className="lens-indicator">{lensIndicator}</div>}
      <div className="signal-loss"><Radio /><span>Видеопоток ожидает подключения</span><small>RTSP · {camera.ip}:{camera.rtspPort}</small></div>
    </div>
  );
}

export default function App() {
  const [config, setConfig] = useState<AppConfig>(cloneDefaults);
  const [drawer, setDrawer] = useState<Drawer>(null);
  const [systemOpen, setSystemOpen] = useState(false);
  const [systemTab, setSystemTab] = useState<SystemTab>("summary");
  const [devices, setDevices] = useState<DeviceSummary[]>([]);
  const [scanning, setScanning] = useState(false);
  const [split, setSplit] = useState(50);
  const [swapped, setSwapped] = useState(false);
  const [recording, setRecording] = useState(false);
  const [saved, setSaved] = useState(false);
  const stageRef = useRef<HTMLDivElement>(null);

  useEffect(() => { void loadConfig().then(setConfig); }, []);
  useEffect(() => { void discoverDevices().then(setDevices).catch(() => setDevices([])); }, []);

  const fallbackDevices = useMemo<DeviceSummary[]>(() => [
    { id: "camera1", name: "CAM 01", kind: "camera", ip: config.cameras[0].ip, port: config.cameras[0].onvifPort, protocol: "ONVIF / RTSP", connected: false },
    { id: "camera2", name: "CAM 02", kind: "camera", ip: config.cameras[1].ip, port: config.cameras[1].onvifPort, protocol: "ONVIF / RTSP", connected: false },
    { id: "platform", name: "TL.0009", kind: "platform", ip: config.platformIp, port: config.platformPort, protocol: "SERVICE TCP", connected: false },
    { id: "rangefinder", name: "Дальномер", kind: "rangefinder", ip: config.rangefinderIp, port: config.rangefinderPort, protocol: "TCP", connected: false },
    { id: "relay", name: "Relay X3", kind: "relay", ip: config.relayIp, port: config.relayPort, protocol: "PELCO-D", connected: false },
  ], [config]);

  const runDiscovery = async () => {
    setScanning(true);
    try { setDevices(await discoverDevices()); } finally { setScanning(false); }
  };

  const saveAll = async () => {
    await persistConfig(config);
    setSaved(true);
    window.setTimeout(() => setSaved(false), 1500);
  };

  const patchCamera = (id: "camera1" | "camera2", patch: Partial<CameraConfig>) => {
    const cameras = config.cameras.map((camera) => camera.id === id ? { ...camera, ...patch } : camera) as [CameraConfig, CameraConfig];
    setConfig({ ...config, cameras });
  };

  const beginSplitDrag = (event: React.PointerEvent) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    const update = (clientX: number) => {
      const bounds = stageRef.current?.getBoundingClientRect();
      if (!bounds) return;
      setSplit(Math.max(24, Math.min(76, ((clientX - bounds.left) / bounds.width) * 100)));
    };
    const move = (e: PointerEvent) => update(e.clientX);
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const leftCamera = swapped ? config.cameras[1] : config.cameras[0];
  const rightCamera = swapped ? config.cameras[0] : config.cameras[1];
  const activeDevices = devices.length ? devices : fallbackDevices;
  const matched = config.alignment.enabled;
  const videoJog = (direction: "left" | "right" | "up" | "down") => {
    const speed = direction === "left" || direction === "right" ? config.profiles[0].panSpeed : config.profiles[0].tiltSpeed;
    void platformJog(config.platformIp, config.platformPort, direction, speed).catch(() => undefined);
  };
  const videoStop = () => { void platformStop(config.platformIp, config.platformPort).catch(() => undefined); };

  return (
    <main className="app-shell">
      <header className="command-bar" data-tauri-drag-region>
        <div className="brand"><div className="brand-mark"><Crosshair /></div><div><strong>ONCAM</strong><span>AXIS FUSION COCKPIT</span></div></div>
        <div className="header-status"><span><i className="blue-dot" /> CAM 01</span><span><i className="amber-dot" /> CAM 02</span><span><i className="white-dot" /> TL.0009</span></div>
        <div className="header-actions">
          <button className={config.alignment.enabled ? "active" : ""} onClick={() => setConfig({ ...config, alignment: { ...config.alignment, enabled: !config.alignment.enabled } })}><AlignCenter /> Сведение</button>
          <button className={recording ? "recording" : ""} onClick={() => setRecording(!recording)}>{recording ? <Square /> : <CircleDot />} {recording ? "REC" : "Запись"}</button>
          <button className={systemOpen ? "active" : ""} onClick={() => setSystemOpen(!systemOpen)}><PanelTopOpen /> Система</button>
          <button onClick={() => void saveAll()} title="Сохранить конфигурацию">{saved ? <span className="saved-mark">OK</span> : <Save />}</button>
        </div>
      </header>

      {systemOpen && <SystemDrawer tab={systemTab} setTab={setSystemTab} config={config} devices={activeDevices} scanning={scanning} onScan={() => void runDiscovery()} onClose={() => setSystemOpen(false)} onConfig={setConfig} recording={recording} setRecording={setRecording} />}

      <div className="workbench">
        {drawer === "camera1" && <CameraDrawer camera={config.cameras[0]} side="left" onClose={() => setDrawer(null)} onChange={(patch) => patchCamera("camera1", patch)} onScan={() => void runDiscovery()} />}

        <section className="video-workspace">
          <div className="video-toolbar">
            <button className="camera-open blue" onClick={() => setDrawer(drawer === "camera1" ? null : "camera1")}><SlidersHorizontal /> CAM 01</button>
            <div className="workspace-mode"><span>ЕДИНАЯ ВИДЕОПОВЕРХНОСТЬ</span><button onClick={() => setSwapped(!swapped)} title="Поменять камеры местами"><RefreshCw /> Поменять</button><button onClick={() => setSplit(50)} title="Равные размеры"><GripVertical /></button></div>
            <button className="camera-open amber" onClick={() => setDrawer(drawer === "camera2" ? null : "camera2")}>CAM 02 <SlidersHorizontal /></button>
          </div>
          <div className="video-stage" ref={stageRef} style={{ gridTemplateColumns: `${split}% ${100 - split}%` }}>
            <VideoPane camera={leftCamera} variant={leftCamera.id === "camera1" ? "optical" : "thermal"} alignment={config.alignment.enabled} matched={matched} onJog={videoJog} onStop={videoStop} />
            <button className="split-handle" style={{ left: `calc(${split}% - 10px)` }} onPointerDown={beginSplitDrag} title="Перетащите для изменения размера"><span /><GripVertical /></button>
            <VideoPane camera={rightCamera} variant={rightCamera.id === "camera2" ? "thermal" : "optical"} alignment={config.alignment.enabled} matched={matched} onJog={videoJog} onStop={videoStop} />
          </div>
        </section>

        {drawer === "camera2" && <CameraDrawer camera={config.cameras[1]} side="right" onClose={() => setDrawer(null)} onChange={(patch) => patchCamera("camera2", patch)} onScan={() => void runDiscovery()} />}
      </div>

      <footer className="telemetry-bar">
        <div><i className="blue-dot" /><b>CAM 01</b><span>{config.cameras[0].ip}</span><strong>25 FPS</strong><span>1920×1080</span></div>
        <div><i className="amber-dot" /><b>CAM 02</b><span>{config.cameras[1].ip}</span><strong>25 FPS</strong><span>640×512</span></div>
        <div className="axis-metrics"><Metric label="PAN" value="−12.40°" /><Metric label="TILT" value="+04.85°" /><Metric label="RANGE" value="— m" /><Metric label="ΔX / ΔY" value={config.alignment.enabled ? "0 / 0 px" : "— / —"} tone={config.alignment.enabled ? "blue" : "neutral"} /></div>
        <div className={`match-state ${config.alignment.enabled ? "matched" : ""}`}><Crosshair /><span>{config.alignment.enabled ? "ОСИ СОВПАЛИ" : "СВЕДЕНИЕ ВЫКЛ"}</span></div>
      </footer>
    </main>
  );
}
