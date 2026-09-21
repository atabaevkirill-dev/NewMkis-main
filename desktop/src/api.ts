import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { open } from "@tauri-apps/plugin-dialog";
import { createDefaultConfig, migrateConfig } from "./config";
import type { AppConfig, ProbeResult, ProbeTarget, RockingEvent, RockingProfile } from "./types";

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

export async function cameraLensStep(cameraId: string, mode: "zoom" | "focus", direction: number): Promise<void> {
  if (!inTauri()) throw new Error(BROWSER_MODE);
  await invoke("camera_lens_step", { cameraId, mode, direction });
}

export async function onRockingState(handler: (event: RockingEvent) => void): Promise<UnlistenFn> {
  if (!inTauri()) return () => undefined;
  return listen<RockingEvent>("rocking-state", (event) => handler(event.payload));
}
