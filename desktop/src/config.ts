import type {
  AppConfig,
  CameraConfig,
  DeviceKind,
  DeviceModule,
  ModuleView,
  ReticleConfig,
  ReticleStyle,
  RockingProfile,
  VideoStats,
} from "./types";

export const SCHEMA_VERSION = 4;

export const OFF_STATS: VideoStats = { state: "off", fps: null, width: null, height: null, message: "", dropped: 0 };
export const MAX_CUSTOM_MODULES = 24;
export const MAX_NAME_LENGTH = 32;
export const MAX_TITLE_LENGTH = 160;
export const DEFAULT_MODULE_NAMES: Record<string, string> = {
  camera1: "CAM 01",
  camera2: "CAM 02",
  platform: "TL.0009",
  rangefinder: "Дальномер",
  relay: "Relay X3",
};
export const BUILTIN_MODULE_IDS = Object.keys(DEFAULT_MODULE_NAMES);
const MODULE_ID = /^[a-z0-9][a-z0-9-]{0,47}$/;

export const PLATFORM_LIMITS = {
  panSpeed: 50,
  tiltSpeed: 19,
  pan: 180,
  tiltMin: -45,
  tiltMax: 90,
} as const;

export const RETICLE_STYLES: { value: ReticleStyle; label: string }[] = [
  { value: "circleCross", label: "Круг + крест" },
  { value: "cross", label: "Крест" },
  { value: "crossGap", label: "Крест с разрывом" },
  { value: "crossDot", label: "Крест + точка" },
  { value: "duplex", label: "Дуплекс" },
  { value: "tee", label: "Т-образный" },
  { value: "circle", label: "Круг" },
  { value: "dot", label: "Точка" },
  { value: "brackets", label: "Уголки" },
];

export const RETICLE_COLORS = ["#ffffff", "#000000", "#ff3b30", "#ffd60a", "#22d3ee", "#4da3ff", "#f0a64a", "#ff2d95"];

type Range = readonly [number, number];

export const RETICLE_LIMITS: Record<"width" | "height" | "thickness" | "gap" | "radius" | "offsetX" | "offsetY" | "opacity", Range> = {
  width: [4, 2000],
  height: [4, 2000],
  thickness: [1, 12],
  gap: [0, 300],
  radius: [1, 400],
  offsetX: [-1000, 1000],
  offsetY: [-1000, 1000],
  opacity: [0.1, 1],
};

export const KIND_LABELS: Record<DeviceKind, string> = { camera: "Камера", platform: "Поворотка", rangefinder: "Дальномер", relay: "Реле", tcp: "Устройство" };

export const MODULE_PRESETS: Record<DeviceKind, { label: string; protocol: string; port: number }> = {
  camera: { label: "Камера ONVIF", protocol: "ONVIF / RTSP", port: 80 },
  platform: { label: "Поворотное устройство", protocol: "SERVICE $…#", port: 9760 },
  rangefinder: { label: "Дальномер", protocol: "TCP", port: 20108 },
  relay: { label: "Реле", protocol: "TCP", port: 9762 },
  tcp: { label: "TCP-устройство", protocol: "TCP", port: 502 },
};

export const clamp = (value: number, [min, max]: Range) => Math.min(max, Math.max(min, value));
/** Must match `STEP_PERCENT` in onvif.rs. */
export const LENS_STEP_LIMITS: Range = [0.01, 25];
export const isIPv4 = (value: string) =>
  /^(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}$/.test(value.trim());
export const isPort = (value: number) => Number.isInteger(value) && value >= 1 && value <= 65535;
/** Mirrors the native check: absolute, printable ASCII, no credentials or fragment. */
/** A path the native side accepts. Empty is valid only with `streamAuto` (no fallback). */
export const isStreamPath = (value: string) => value.length <= 256 && /^\/[\x21-\x7e]*$/.test(value) && !/[@\\#]/.test(value);

export function defaultReticles(): ReticleConfig[] {
  return [
    { enabled: true, style: "circleCross", color: "#f1f5f9", opacity: 0.8, width: 54, height: 54, thickness: 1, gap: 0, radius: 4, offsetX: 0, offsetY: 0, outline: false },
    { enabled: false, style: "brackets", color: "#ffffff", opacity: 0.7, width: 120, height: 90, thickness: 1, gap: 0, radius: 14, offsetX: 0, offsetY: 0, outline: false },
    { enabled: false, style: "dot", color: "#ff3b30", opacity: 1, width: 20, height: 20, thickness: 1, gap: 0, radius: 2, offsetX: 0, offsetY: 0, outline: true },
  ];
}

export function createDefaultConfig(): AppConfig {
  const camera = (id: CameraConfig["id"], name: string, ip: string, streamPath: string, profile: string): CameraConfig => ({
    id, name, ip, onvifPort: 80, rtspPort: 554, streamAuto: true, streamPath, username: "admin", profile, autoConnect: true, osd: false, zoomStepPercent: 0.1, focusStepPercent: 2, reticles: defaultReticles(),
  });
  return {
    schemaVersion: SCHEMA_VERSION,
    productTitle: "",
    // Stream paths come from the cameras over ONVIF; a stored path is only the fallback. CAM 01 is a Uniview
    // UV-ZNH2130M; CAM 02 is whichever thermal camera is fitted (192.168.1.108 is the Dahua-family factory address).
    cameras: [
      camera("camera1", "CAM 01 · OPTICAL", "192.168.1.68", "/media/video1", "PROFILE_1"),
      camera("camera2", "CAM 02 · THERMAL", "192.168.1.108", "", "THERMAL_1"),
    ],
    platformIp: "192.168.1.115",
    platformPort: 9760,
    rangefinderIp: "192.168.1.7",
    rangefinderPort: 20108,
    relayIp: "192.168.127.254",
    relayPort: 9762,
    modules: [],
    hiddenModules: [],
    moduleNames: {},
    reticlesLinked: false,
    jog: { panSpeed: 10, tiltSpeed: 5, invertPan: false, invertTilt: false },
    profiles: Array.from({ length: 5 }, (_, index) => ({
      id: index + 1,
      name: `Профиль ${index + 1}`,
      panMin: -45,
      panMax: 45,
      tiltMin: -15,
      tiltMax: 20,
      panSpeed: 20,
      tiltSpeed: 8,
      cycles: 10,
      pauseSeconds: 1,
      smoothMotion: true,
    })),
    recording: { camera1: true, camera2: true, directory: "", format: "mp4", layout: "separate", splitReticles: true, stopAfterMinutes: 0, segmentMinutes: 30, includeMetadata: true, includeEncryptedSecrets: false },
    report: { serialNumber: "", operator: "" },
    alignment: { enabled: false, tolerancePx: 3, stableMs: 1200 },
  };
}

type Json = Record<string, unknown>;
const isRecord = (value: unknown): value is Json => typeof value === "object" && value !== null && !Array.isArray(value);

/** Takes stored values only where they have the same shape as the defaults; arrays are normalised separately. */
function mergeShape<T>(defaults: T, stored: unknown): T {
  if (Array.isArray(defaults)) return defaults;
  if (isRecord(defaults)) {
    if (!isRecord(stored)) return defaults;
    const merged: Json = { ...defaults };
    for (const key of Object.keys(defaults)) merged[key] = mergeShape(defaults[key], stored[key]);
    return merged as T;
  }
  if (typeof defaults === "number") return (typeof stored === "number" && Number.isFinite(stored) ? stored : defaults) as T;
  return (typeof stored === typeof defaults ? stored : defaults) as T;
}

function normalizeReticle(defaults: ReticleConfig, stored: unknown): ReticleConfig {
  const reticle = mergeShape(defaults, stored);
  const whole = (value: number, range: Range) => Math.round(clamp(value, range));
  return {
    ...reticle,
    style: RETICLE_STYLES.some((style) => style.value === reticle.style) ? reticle.style : defaults.style,
    color: /^#[0-9a-f]{6}$/i.test(reticle.color) ? reticle.color : defaults.color,
    opacity: clamp(reticle.opacity, RETICLE_LIMITS.opacity),
    width: whole(reticle.width, RETICLE_LIMITS.width),
    height: whole(reticle.height, RETICLE_LIMITS.height),
    thickness: whole(reticle.thickness, RETICLE_LIMITS.thickness),
    gap: whole(reticle.gap, RETICLE_LIMITS.gap),
    radius: whole(reticle.radius, RETICLE_LIMITS.radius),
    offsetX: whole(reticle.offsetX, RETICLE_LIMITS.offsetX),
    offsetY: whole(reticle.offsetY, RETICLE_LIMITS.offsetY),
  };
}

function normalizeCamera(defaults: CameraConfig, stored: unknown): CameraConfig {
  const camera = mergeShape(defaults, stored);
  const reticles = isRecord(stored) && Array.isArray(stored.reticles) ? stored.reticles : [];
  return { ...camera, id: defaults.id, zoomStepPercent: clamp(camera.zoomStepPercent, LENS_STEP_LIMITS), focusStepPercent: clamp(camera.focusStepPercent, LENS_STEP_LIMITS), reticles: defaults.reticles.map((reticle, index) => normalizeReticle(reticle, reticles[index])) };
}

function normalizeModules(stored: unknown): DeviceModule[] {
  if (!Array.isArray(stored)) return [];
  const empty: DeviceModule = { id: "", name: "", kind: "tcp", ip: "", port: 0, protocol: "" };
  const seen = new Set(BUILTIN_MODULE_IDS);
  const modules: DeviceModule[] = [];
  for (const item of stored) {
    const module = mergeShape(empty, item);
    if (!MODULE_ID.test(module.id) || seen.has(module.id) || !(module.kind in MODULE_PRESETS)) continue;
    seen.add(module.id);
    modules.push({
      ...module,
      name: module.name.trim().slice(0, MAX_NAME_LENGTH) || MODULE_PRESETS[module.kind].label,
      port: isPort(module.port) ? module.port : MODULE_PRESETS[module.kind].port,
      protocol: module.protocol || MODULE_PRESETS[module.kind].protocol,
    });
  }
  return modules.slice(0, MAX_CUSTOM_MODULES);
}

function normalizeModuleNames(stored: unknown): Record<string, string> {
  if (!isRecord(stored)) return {};
  const names: Record<string, string> = {};
  for (const id of BUILTIN_MODULE_IDS) {
    const name = stored[id];
    if (typeof name !== "string") continue;
    const trimmed = name.trim().slice(0, MAX_NAME_LENGTH);
    if (trimmed && trimmed !== DEFAULT_MODULE_NAMES[id]) names[id] = trimmed;
  }
  return names;
}

/** Accepts any stored value (older schema, partial or damaged) and returns a complete, valid config. */
export function migrateConfig(stored: unknown): AppConfig {
  const defaults = createDefaultConfig();
  if (!isRecord(stored)) return defaults;
  const config = mergeShape(defaults, stored);
  const cameras = Array.isArray(stored.cameras) ? stored.cameras : [];
  const profiles = Array.isArray(stored.profiles) ? stored.profiles : [];
  config.cameras = [normalizeCamera(defaults.cameras[0], cameras[0]), normalizeCamera(defaults.cameras[1], cameras[1])];
  config.profiles = defaults.profiles.map((profile, index) => ({ ...mergeShape(profile, profiles[index]), id: profile.id }));
  config.modules = normalizeModules(stored.modules);
  config.moduleNames = normalizeModuleNames(stored.moduleNames);
  config.productTitle = config.productTitle.trim().slice(0, MAX_TITLE_LENGTH);
  config.report = {
    serialNumber: config.report.serialNumber.trim().slice(0, 64),
    operator: config.report.operator.trim().slice(0, 64),
  };
  config.hiddenModules = Array.isArray(stored.hiddenModules)
    ? [...new Set(stored.hiddenModules.filter((id): id is string => typeof id === "string"))]
    : [];
  // Schema 4: TL.0009 answers the service protocol only on 9760 (verified on the device; 9761/9762 stay silent).
  const storedSchema = typeof stored.schemaVersion === "number" ? stored.schemaVersion : 0;
  if (storedSchema < 2 || (storedSchema < 4 && config.platformPort === 9762)) config.platformPort = 9760;
  // Only fragmented MP4 is implemented; an older «mkv» choice would otherwise look honoured.
  config.recording.format = "mp4";
  if (!["separate", "split", "both"].includes(config.recording.layout)) config.recording.layout = "separate";
  config.recording.stopAfterMinutes = Math.round(clamp(config.recording.stopAfterMinutes, [0, 1440]));
  config.recording.includeEncryptedSecrets = false;
  config.schemaVersion = SCHEMA_VERSION;
  return config;
}

/** Display name of a built-in device, honouring the operator's rename. */
export const moduleName = (config: AppConfig, id: string) => config.moduleNames[id] ?? DEFAULT_MODULE_NAMES[id] ?? id;

export function listModules(config: AppConfig): ModuleView[] {
  const hidden = new Set(config.hiddenModules);
  const [camera1, camera2] = config.cameras;
  const name = (id: string) => moduleName(config, id);
  const builtins: DeviceModule[] = [
    { id: "camera1", name: name("camera1"), kind: "camera", ip: camera1.ip, port: camera1.onvifPort, protocol: "ONVIF / RTSP" },
    { id: "camera2", name: name("camera2"), kind: "camera", ip: camera2.ip, port: camera2.onvifPort, protocol: "ONVIF / RTSP" },
    { id: "platform", name: name("platform"), kind: "platform", ip: config.platformIp, port: config.platformPort, protocol: "SERVICE $…#" },
    { id: "rangefinder", name: name("rangefinder"), kind: "rangefinder", ip: config.rangefinderIp, port: config.rangefinderPort, protocol: "TCP" },
    { id: "relay", name: name("relay"), kind: "relay", ip: config.relayIp, port: config.relayPort, protocol: "TCP · Pelco-D" },
  ];
  return [
    ...builtins.map((module) => ({ ...module, builtin: true, hidden: hidden.has(module.id) })),
    ...config.modules.map((module) => ({ ...module, builtin: false, hidden: hidden.has(module.id) })),
  ];
}

export interface ModuleDraft {
  kind: DeviceKind;
  name: string;
  ip: string;
  port: string;
}

export function validateModuleDraft(draft: ModuleDraft, builtin: boolean): string | null {
  // A built-in device with an empty name falls back to its default name.
  if (!builtin && !draft.name.trim()) return "Укажите название";
  if (draft.name.trim().length > MAX_NAME_LENGTH) return `Название не длиннее ${MAX_NAME_LENGTH} символов`;
  if (!isIPv4(draft.ip)) return "IP-адрес в формате 192.168.1.10";
  if (!isPort(Number(draft.port))) return "Порт от 1 до 65535";
  return null;
}

function renameBuiltin(config: AppConfig, id: string, name: string): Record<string, string> {
  const names = { ...config.moduleNames };
  if (!name || name === DEFAULT_MODULE_NAMES[id]) delete names[id];
  else names[id] = name;
  return names;
}

function newModuleId(): string {
  const random = crypto.getRandomValues(new Uint32Array(1))[0].toString(36);
  return `m-${Date.now().toString(36)}-${random}`;
}

/** Creates a module (`id` = null) or updates the name and address of an existing one. */
export function saveModule(config: AppConfig, id: string | null, draft: ModuleDraft): AppConfig {
  const ip = draft.ip.trim();
  const port = Number(draft.port);
  const name = draft.name.trim().slice(0, MAX_NAME_LENGTH);
  switch (id) {
    case "camera1":
    case "camera2": {
      const index = id === "camera1" ? 0 : 1;
      const cameras = [...config.cameras] as [CameraConfig, CameraConfig];
      cameras[index] = { ...cameras[index], ip, onvifPort: port };
      return { ...config, cameras, moduleNames: renameBuiltin(config, id, name) };
    }
    case "platform":
      return { ...config, platformIp: ip, platformPort: port, moduleNames: renameBuiltin(config, id, name) };
    case "rangefinder":
      return { ...config, rangefinderIp: ip, rangefinderPort: port, moduleNames: renameBuiltin(config, id, name) };
    case "relay":
      return { ...config, relayIp: ip, relayPort: port, moduleNames: renameBuiltin(config, id, name) };
    case null:
      return {
        ...config,
        modules: [...config.modules, { id: newModuleId(), kind: draft.kind, name, ip, port, protocol: MODULE_PRESETS[draft.kind].protocol }],
      };
    default:
      return { ...config, modules: config.modules.map((module) => (module.id === id ? { ...module, name: name || module.name, ip, port } : module)) };
  }
}

export const removeModule = (config: AppConfig, id: string): AppConfig => ({
  ...config,
  modules: config.modules.filter((module) => module.id !== id),
  hiddenModules: config.hiddenModules.filter((hiddenId) => hiddenId !== id),
});

export const setModuleHidden = (config: AppConfig, id: string, hidden: boolean): AppConfig => ({
  ...config,
  hiddenModules: hidden ? [...new Set([...config.hiddenModules, id])] : config.hiddenModules.filter((hiddenId) => hiddenId !== id),
});

/** Mirrors the native validation so the operator sees the problem before a command is sent. */
export function profileError(profile: RockingProfile): string | null {
  const { pan, tiltMin, tiltMax, panSpeed, tiltSpeed } = PLATFORM_LIMITS;
  if (!(profile.panMin < profile.panMax) || profile.panMin < -pan || profile.panMax > pan) return `PAN: min < max в пределах ±${pan}°`;
  if (!(profile.tiltMin < profile.tiltMax) || profile.tiltMin < tiltMin || profile.tiltMax > tiltMax) return `TILT: min < max в пределах ${tiltMin}…${tiltMax}°`;
  if (!(profile.panSpeed > 0 && profile.panSpeed <= panSpeed)) return `PAN: скорость 0…${panSpeed}°/с`;
  if (!(profile.tiltSpeed > 0 && profile.tiltSpeed <= tiltSpeed)) return `TILT: скорость 0…${tiltSpeed}°/с`;
  if (!Number.isInteger(profile.cycles) || profile.cycles < 1 || profile.cycles > 1000) return "Циклы: от 1 до 1000";
  if (!(profile.pauseSeconds >= 0 && profile.pauseSeconds <= 300)) return "Пауза: от 0 до 300 с";
  return null;
}
