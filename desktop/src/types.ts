export type DeviceKind = "camera" | "platform" | "rangefinder" | "relay" | "tcp";

/** A device the operator added in the summary; built-in devices are derived from AppConfig fields. */
export interface DeviceModule {
  id: string;
  name: string;
  kind: DeviceKind;
  ip: string;
  port: number;
  protocol: string;
}

export interface ModuleView extends DeviceModule {
  builtin: boolean;
  hidden: boolean;
}

export interface ProbeTarget {
  id: string;
  ip: string;
  port: number;
}

export interface ProbeResult {
  id: string;
  connected: boolean;
  latencyMs: number | null;
  error: string | null;
}

export type ReticleStyle =
  | "circleCross"
  | "cross"
  | "crossGap"
  | "crossDot"
  | "duplex"
  | "tee"
  | "circle"
  | "dot"
  | "brackets";

export interface ReticleConfig {
  enabled: boolean;
  style: ReticleStyle;
  color: string;
  opacity: number;
  /** Horizontal extent, px. */
  width: number;
  /** Vertical extent, px. */
  height: number;
  thickness: number;
  /** Empty radius around the centre, px. */
  gap: number;
  /** Circle radius, dot radius or bracket arm length, px. */
  radius: number;
  offsetX: number;
  offsetY: number;
  /** Dark halo that keeps the reticle visible on bright (white-hot) scenes. */
  outline: boolean;
}

export interface CameraConfig {
  id: "camera1" | "camera2";
  name: string;
  ip: string;
  onvifPort: number;
  rtspPort: number;
  username: string;
  profile: string;
  autoConnect: boolean;
  osd: boolean;
  reticles: ReticleConfig[];
}

export interface RockingProfile {
  id: number;
  name: string;
  panMin: number;
  panMax: number;
  tiltMin: number;
  tiltMax: number;
  panSpeed: number;
  tiltSpeed: number;
  cycles: number;
  pauseSeconds: number;
  smoothMotion: boolean;
}

export interface JogConfig {
  panSpeed: number;
  tiltSpeed: number;
}

export interface RecordingConfig {
  camera1: boolean;
  camera2: boolean;
  directory: string;
  format: "mkv" | "mp4";
  segmentMinutes: number;
  includeMetadata: boolean;
  includeEncryptedSecrets: boolean;
}

export interface ReportConfig {
  serialNumber: string;
  operator: string;
}

export type TestKind = "tcp" | "selftest";

/** One executed check; the PDF protocol is built only from these records. */
export interface TestRecord {
  moduleId: string;
  kind: TestKind;
  ok: boolean;
  detail: string;
  /** ISO timestamp of the check. */
  at: string;
}

export interface AlignmentConfig {
  enabled: boolean;
  tolerancePx: number;
  stableMs: number;
}

export interface AppConfig {
  schemaVersion: number;
  /** Full name of the installation shown next to the app name. */
  productTitle: string;
  cameras: [CameraConfig, CameraConfig];
  platformIp: string;
  platformPort: number;
  rangefinderIp: string;
  rangefinderPort: number;
  relayIp: string;
  relayPort: number;
  modules: DeviceModule[];
  hiddenModules: string[];
  /** Operator-chosen names for built-in devices (id → name); missing means the default name. */
  moduleNames: Record<string, string>;
  /** When true, reticle edits in either drawer apply to both video panes. */
  reticlesLinked: boolean;
  jog: JogConfig;
  profiles: RockingProfile[];
  recording: RecordingConfig;
  report: ReportConfig;
  alignment: AlignmentConfig;
}

export interface RockingEvent {
  state: "running" | "completed" | "cancelled" | "failed";
  cycle: number;
  cycles: number;
  message: string | null;
}

export type Notify = (text: string, tone?: "info" | "error") => void;
