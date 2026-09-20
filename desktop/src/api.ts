import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import type { AppConfig, DeviceSummary, RockingProfile } from "./types";

export const defaultConfig: AppConfig = {
  schemaVersion: 2,
  cameras: [
    {
      id: "camera1",
      name: "CAM 01 · OPTICAL",
      ip: "192.168.1.68",
      onvifPort: 80,
      rtspPort: 554,
      username: "admin",
      profile: "PROFILE_1",
      autoConnect: true,
      osd: false,
    },
    {
      id: "camera2",
      name: "CAM 02 · THERMAL",
      ip: "192.168.1.108",
      onvifPort: 80,
      rtspPort: 554,
      username: "admin",
      profile: "THERMAL_1",
      autoConnect: true,
      osd: false,
    },
  ],
  platformIp: "192.168.1.115",
  platformPort: 9762,
  rangefinderIp: "192.168.1.7",
  rangefinderPort: 20108,
  relayIp: "192.168.127.254",
  relayPort: 9762,
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
  recording: {
    camera1: true,
    camera2: true,
    directory: "",
    format: "mkv",
    segmentMinutes: 30,
    includeMetadata: true,
    includeEncryptedSecrets: false,
  },
  alignment: {
    enabled: false,
    tolerancePx: 3,
    stableMs: 1200,
  },
};

const inTauri = () => "__TAURI_INTERNALS__" in window;

function migrateConfig(stored: Partial<AppConfig> | null): AppConfig {
  if (!stored) return defaultConfig;
  const migrated = { ...defaultConfig, ...stored } as AppConfig;
  if ((stored.schemaVersion ?? 0) < 2) {
    migrated.platformPort = 9762;
    migrated.schemaVersion = 2;
  }
  return migrated;
}

export async function loadConfig(): Promise<AppConfig> {
  if (!inTauri()) {
    const stored = localStorage.getItem("oncam-config");
    if (!stored) return defaultConfig;
    try {
      return migrateConfig(JSON.parse(stored) as Partial<AppConfig>);
    } catch {
      return defaultConfig;
    }
  }
  const stored = await invoke<AppConfig | null>("get_config");
  return migrateConfig(stored);
}

export async function persistConfig(config: AppConfig): Promise<void> {
  if (!inTauri()) {
    localStorage.setItem("oncam-config", JSON.stringify(config));
    return;
  }
  await invoke("save_config", { config });
}

export async function discoverDevices(): Promise<DeviceSummary[]> {
  if (!inTauri()) {
    await new Promise((resolve) => setTimeout(resolve, 700));
    return [
      { id: "camera1", name: "CAM 01", kind: "camera", ip: "192.168.1.68", port: 80, protocol: "ONVIF / RTSP", connected: true },
      { id: "camera2", name: "CAM 02", kind: "camera", ip: "192.168.1.108", port: 80, protocol: "ONVIF / RTSP", connected: true },
      { id: "platform", name: "TL.0009", kind: "platform", ip: "192.168.1.115", port: 9762, protocol: "SERVICE TCP", connected: true },
      { id: "rangefinder", name: "Rangefinder", kind: "rangefinder", ip: "192.168.1.7", port: 20108, protocol: "TCP", connected: true },
      { id: "relay", name: "Relay X3", kind: "relay", ip: "192.168.127.254", port: 9762, protocol: "PELCO-D", connected: true },
    ];
  }
  return invoke<DeviceSummary[]>("discover_devices");
}

export async function getSecret(deviceId: string): Promise<string> {
  if (!inTauri()) return sessionStorage.getItem(`oncam-secret:${deviceId}`) ?? "";
  return invoke<string>("get_secret", { deviceId });
}

export async function setSecret(deviceId: string, password: string): Promise<void> {
  if (!inTauri()) {
    sessionStorage.setItem(`oncam-secret:${deviceId}`, password);
    return;
  }
  await invoke("set_secret", { deviceId, password });
}

export async function chooseRecordingDirectory(): Promise<string | null> {
  if (!inTauri()) return null;
  const selected = await open({ directory: true, multiple: false });
  return typeof selected === "string" ? selected : null;
}

export async function platformJog(ip: string, port: number, direction: "left" | "right" | "up" | "down", speed: number): Promise<string> {
  if (!inTauri()) return `DEMO: ${direction} ${speed}`;
  return invoke<string>("platform_jog", { ip, port, direction, speed });
}

export async function platformStop(ip: string, port: number): Promise<void> {
  if (!inTauri()) return;
  await invoke("platform_stop", { ip, port });
}

export async function startRockingProfile(ip: string, port: number, profile: RockingProfile): Promise<void> {
  if (!inTauri()) return;
  await invoke("start_rocking", { ip, port, profile });
}

export async function stopRockingProfile(ip: string, port: number): Promise<void> {
  if (!inTauri()) return;
  await invoke("stop_rocking", { ip, port });
}

export async function runPlatformSelfTest(ip: string, port: number): Promise<string[]> {
  if (!inTauri()) return ["$m,1# → DEMO", "$M,1# → DEMO"];
  return invoke<string[]>("platform_self_test", { ip, port });
}

export async function cameraLensStep(cameraId: string, mode: "zoom" | "focus", direction: number): Promise<void> {
  if (!inTauri()) return;
  await invoke("camera_lens_step", { cameraId, mode, direction });
}
