export type DeviceKind = "camera" | "platform" | "rangefinder" | "relay";

export interface DeviceSummary {
  id: string;
  name: string;
  kind: DeviceKind;
  ip: string;
  port: number;
  protocol: string;
  connected: boolean;
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

export interface RecordingConfig {
  camera1: boolean;
  camera2: boolean;
  directory: string;
  format: "mkv" | "mp4";
  segmentMinutes: number;
  includeMetadata: boolean;
  includeEncryptedSecrets: boolean;
}

export interface AlignmentConfig {
  enabled: boolean;
  tolerancePx: number;
  stableMs: number;
}

export interface AppConfig {
  schemaVersion: number;
  cameras: [CameraConfig, CameraConfig];
  platformIp: string;
  platformPort: number;
  rangefinderIp: string;
  rangefinderPort: number;
  relayIp: string;
  relayPort: number;
  profiles: RockingProfile[];
  recording: RecordingConfig;
  alignment: AlignmentConfig;
}
