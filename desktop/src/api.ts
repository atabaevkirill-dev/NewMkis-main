import { Channel, invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { open } from "@tauri-apps/plugin-dialog";
import { createDefaultConfig, migrateConfig, moduleName } from "./config";
import type { AppConfig, CameraConfig, FoundCamera, ProbeResult, ProbeTarget, RecordingEvent, RockingEvent, RockingProfile, StreamEvent } from "./types";

export type JogDirection = "left" | "right" | "up" | "down";

export const inTauri = () => "__TAURI_INTERNALS__" in window;
const BROWSER_MODE = "браузерный режим: оборудование не опрашивается";

let lastSeq = 0;
/** Monotonic across reloads, so the native side can order a stop against in-flight motion requests. */
function nextSeq(): number {
  const now = Math.floor((performance.timeOrigin + performance.now()) * 1000);
  lastSeq = Math.max(lastSeq + 1, now);
  return lastSeq;
}

export async function loadConfig(): Promise<{ config: AppConfig; recoveredFrom: string | null }> {
  if (!inTauri()) {
    try {
      const stored = localStorage.getItem("oncam-config");
      return { config: migrateConfig(stored ? JSON.parse(stored) : null), recoveredFrom: null };
    } catch {
      return { config: createDefaultConfig(), recoveredFrom: null };
    }
  }
  const loaded = await invoke<{ config: unknown; recoveredFrom: string | null }>("get_config");
  return { config: migrateConfig(loaded.config), recoveredFrom: loaded.recoveredFrom };
}

export async function persistConfig(config: AppConfig): Promise<void> {
  if (!inTauri()) {
    localStorage.setItem("oncam-config", JSON.stringify(config));
    return;
  }
  await invoke("save_config", { config });
}

export async function probeModules(targets: ProbeTarget[]): Promise<ProbeResult[]> {
  if (!inTauri()) return targets.map(({ id }) => ({ id, connected: false, latencyMs: null, error: BROWSER_MODE }));
  return invoke<ProbeResult[]>("probe_devices", { targets });
}

// Browser preview keeps passwords in memory only: never in localStorage or sessionStorage.
const browserSecrets = new Map<string, string>();

export async function hasSecret(deviceId: string): Promise<boolean> {
  if (!inTauri()) return browserSecrets.has(deviceId);
  return invoke<boolean>("has_secret", { deviceId });
}

export async function getSecret(deviceId: string): Promise<string> {
  if (!inTauri()) return browserSecrets.get(deviceId) ?? "";
  return invoke<string>("get_secret", { deviceId });
}

/** An empty password removes the stored one. */
export async function setSecret(deviceId: string, password: string): Promise<void> {
  if (!inTauri()) {
    if (password) browserSecrets.set(deviceId, password);
    else browserSecrets.delete(deviceId);
    return;
  }
  await invoke("set_secret", { deviceId, password });
}

export async function chooseRecordingDirectory(): Promise<string | null> {
  if (!inTauri()) return null;
  const selected = await open({ directory: true, multiple: false });
  return typeof selected === "string" ? selected : null;
}

export async function platformJog(ip: string, port: number, direction: JogDirection, speed: number): Promise<string> {
  if (!inTauri()) return `ДЕМО · ${BROWSER_MODE}`;
  return invoke<string>("platform_jog", { ip, port, direction, speed, seq: nextSeq() });
}

/** Confirms that the jog button is still held; without it the native watchdog stops the axes. */
export async function platformKeepalive(): Promise<void> {
  if (!inTauri()) return;
  await invoke("platform_jog_keepalive");
}

/** Stops both axes and cancels any running profile or held jog. */
export async function platformStop(ip: string, port: number): Promise<void> {
  if (!inTauri()) return;
  await invoke("platform_stop", { ip, port, seq: nextSeq() });
}

export async function runPlatformSelfTest(ip: string, port: number): Promise<string[]> {
  if (!inTauri()) return [`ДЕМО · ${BROWSER_MODE}`];
  return invoke<string[]>("platform_self_test", { ip, port, seq: nextSeq() });
}

export async function startRockingProfile(ip: string, port: number, profile: RockingProfile): Promise<void> {
  if (!inTauri()) throw new Error(BROWSER_MODE);
  await invoke("start_rocking", { ip, port, profile, seq: nextSeq() });
}

export async function stopRockingProfile(ip: string, port: number): Promise<void> {
  if (!inTauri()) return;
  await invoke("stop_rocking", { ip, port, seq: nextSeq() });
}

/** Opens the system print dialog (the report page is laid out for A4; choose «Save as PDF»). */
export async function printPage(): Promise<void> {
  if (inTauri() && (await invoke<boolean>("print_page"))) return;
  window.print();
}

/** `steps` signed lens steps of the camera zoom/focus step each; resolves once the lens has moved. Use `lensStep` from lens.ts. */
export async function cameraLensStep(camera: CameraConfig, mode: "zoom" | "focus", steps: number): Promise<void> {
  if (!inTauri()) throw new Error(BROWSER_MODE);
  await invoke("camera_lens_step", {
    cameraId: camera.id, ip: camera.ip, port: camera.onvifPort, username: camera.username, mode, steps, stepPercent: mode === "zoom" ? camera.zoomStepPercent : camera.focusStepPercent,
  });
}

const STREAM_STATES = ["connecting", "playing", "error"] as const;

/** Decodes the binary messages of `video.rs`; unknown or truncated messages are dropped. */
function parseStreamMessage(buffer: ArrayBuffer): StreamEvent | null {
  const bytes = new Uint8Array(buffer);
  const view = new DataView(buffer);
  if (bytes[0] === 2 && bytes.length >= 10) {
    return { kind: "frame", key: bytes[1] === 1, timestamp: Number(view.getBigInt64(2, true)), data: bytes.subarray(10) };
  }
  if (bytes[0] === 1 && bytes.length >= 10) {
    const codecEnd = 10 + bytes[9];
    return {
      kind: "config",
      codedWidth: view.getUint16(1, true),
      codedHeight: view.getUint16(3, true),
      width: view.getUint16(5, true),
      height: view.getUint16(7, true),
      codec: new TextDecoder().decode(bytes.subarray(10, codecEnd)),
      description: bytes.slice(codecEnd),
    };
  }
  if (bytes[0] === 3 && bytes.length >= 2 && bytes[1] < STREAM_STATES.length) {
    return { kind: "state", state: STREAM_STATES[bytes[1]], message: new TextDecoder().decode(bytes.subarray(2)) };
  }
  return null;
}

/** ONVIF cameras answering WS-Discovery on every local network, sorted by address (about 2.5 s). */
export async function discoverCameras(): Promise<FoundCamera[]> {
  if (!inTauri()) return [];
  return invoke<FoundCamera[]>("discover_cameras");
}

/**
 * Opens the camera's RTSP stream on the native side (password comes from the keychain there) and
 * delivers encoded frames. The returned function stops exactly this stream, even if called early.
 */
export function startCameraStream(camera: CameraConfig, onEvent: (event: StreamEvent) => void): { started: Promise<void>; stop: () => void } {
  if (!inTauri()) return { started: Promise.reject(new Error(BROWSER_MODE)), stop: () => undefined };
  const token = nextSeq();
  const channel = new Channel<ArrayBuffer>((buffer) => {
    const event = parseStreamMessage(buffer);
    if (event) onEvent(event);
  });
  const started = invoke<void>("camera_stream_start", {
    cameraId: camera.id, ip: camera.ip, port: camera.rtspPort, onvifPort: camera.onvifPort, auto: camera.streamAuto,
    username: camera.username, path: camera.streamPath, token, channel,
  });
  const stop = () => {
    // Wait for the start to land first, otherwise the stop could arrive before the task exists.
    void started.catch(() => undefined).then(() => invoke("camera_stream_stop", { cameraId: camera.id, token })).catch(() => undefined);
  };
  return { started, stop };
}

/**
 * Records the selected cameras' running streams to fragmented MP4 (no transcoding). Files are named
 * «<product title>_<camera name>_<local time>.mp4»; returns the directory actually used.
 */
export async function startRecording(config: AppConfig): Promise<string> {
  if (!inTauri()) throw new Error(BROWSER_MODE);
  const { camera1, camera2, directory, segmentMinutes, includeMetadata } = config.recording;
  const settings = {
    camera1, camera2, directory, segmentMinutes, includeMetadata,
    title: config.productTitle,
    camera1Name: moduleName(config, "camera1"),
    camera2Name: moduleName(config, "camera2"),
    utcOffsetMinutes: -new Date().getTimezoneOffset(),
  };
  return invoke<string>("recording_start", { settings });
}

export async function stopRecording(): Promise<void> {
  if (!inTauri()) return;
  await invoke("recording_stop");
}

export async function onRecordingState(handler: (event: RecordingEvent) => void): Promise<UnlistenFn> {
  if (!inTauri()) return () => undefined;
  return listen<RecordingEvent>("recording-state", (event) => handler(event.payload));
}

export async function onRockingState(handler: (event: RockingEvent) => void): Promise<UnlistenFn> {
  if (!inTauri()) return () => undefined;
  return listen<RockingEvent>("rocking-state", (event) => handler(event.payload));
}

/** Writes a diagnostic line into the native log (used for video timing measurements). */
export function diagLog(message: string): void {
  if (inTauri()) void invoke("diag_log", { message }).catch(() => undefined);
}
