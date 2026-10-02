import { invoke } from "@tauri-apps/api/core";
import { drawReticles } from "./Reticle";
import { drawThermalOverlay } from "./thermal";
import { drawRangeDisplay, type RangeDisplay } from "./rangefinder";
import { drawRangeSight } from "./sightGeometry";
import type { RangeSightConfig, ReticleConfig, ThermalConfig, ThermalReadings } from "./types";

/** Encoders the webview may offer, best first; MP4/H.264 plays everywhere, WebM is the fallback. */
const FORMATS = [
  { mime: "video/mp4;codecs=avc1.640028", extension: "mp4" },
  { mime: "video/mp4;codecs=avc1", extension: "mp4" },
  { mime: "video/mp4", extension: "mp4" },
  { mime: "video/webm;codecs=vp9", extension: "webm" },
  { mime: "video/webm;codecs=vp8", extension: "webm" },
] as const;

const FPS = 25;
const MAX_HEIGHT = 1080;
const BITRATE = 8_000_000;
/** MediaRecorder hands over a chunk this often; a crash loses at most this much. */
const CHUNK_MS = 1000;

export interface SplitOpenRequest {
  directory: string;
  title: string;
  camera1Name: string;
  camera2Name: string;
  utcOffsetMinutes: number;
}

/** One pane: its decoded video canvas, its palette filter and, when they should be burnt in, its reticles. */
export interface SplitSource {
  canvas: HTMLCanvasElement;
  /** Canvas `filter` that gives the picture the palette shown on screen, or null. */
  filter: string | null;
  /** Mirroring shown on screen. */
  flipX: boolean;
  flipY: boolean;
  reticles: ReticleConfig[] | null;
  /** Rangefinder sight with its distance, drawn instead of the reticles, or null. */
  sight: { sight: RangeSightConfig; offset: { x: number; y: number }; display: RangeDisplay | null } | null;
  /** Distance on the crosshair with its anchor (centre offset and size in CSS px, colour), or null. */
  range: { display: RangeDisplay; cx: number; cy: number; top: number; color: string } | null;
  /** Thermal overlay to burn in, with the latest temperatures, or null. */
  thermal: { config: ThermalConfig; readings: ThermalReadings | null } | null;
}

export interface SplitStatus {
  state: "recording" | "stopped" | "error";
  file: string | null;
  bytes: number;
  message: string | null;
}

/**
 * Records both panes side by side into one file: frames are composed on a canvas in the on-screen
 * order and encoded by the webview's MediaRecorder; chunks are appended by the native side.
 */
export class SplitRecorder {
  private canvas = document.createElement("canvas");
  private context = this.canvas.getContext("2d");
  private timer: number | null = null;
  private segmentTimer: number | null = null;
  private recorder: MediaRecorder | null = null;
  private fileId: number | null = null;
  private file: string | null = null;
  private bytes = 0;
  /** Chunks are written strictly in order. */
  private queue: Promise<unknown> = Promise.resolve();
  private stopped = false;
  private failed = false;

  constructor(
    private readonly sources: () => [SplitSource | null, SplitSource | null],
    private readonly request: SplitOpenRequest,
    private readonly segmentMinutes: number,
    private readonly onStatus: (status: SplitStatus) => void,
  ) {}

  /** Starts recording; returns the directory used. */
  async start(): Promise<string> {
    const format = FORMATS.find((candidate) => MediaRecorder.isTypeSupported(candidate.mime));
    if (!format) throw new Error("WebView не поддерживает кодирование видео (MediaRecorder)");
    const [left, right] = this.sources().map((source) => source?.canvas ?? null);
    if (!left || !right || left.width < 16 || right.width < 16) throw new Error("для сплита нужны оба видеопотока");
    // Both pictures scaled to one height; the width follows their aspect ratios.
    const height = Math.min(MAX_HEIGHT, Math.max(left.height, right.height)) & ~1;
    const width = (Math.round((left.width * height) / left.height) + Math.round((right.width * height) / right.height) + 1) & ~1;
    this.canvas.width = width;
    this.canvas.height = height;
    this.draw();
    this.timer = window.setInterval(() => this.draw(), 1000 / FPS);
    return this.openSegment(format);
  }

  private draw() {
    const context = this.context;
    if (!context) return;
    const { width, height } = this.canvas;
    context.fillStyle = "#000";
    context.fillRect(0, 0, width, height);
    const [left, right] = this.sources();
    const leftWidth = left && left.canvas.height ? Math.round((left.canvas.width * height) / left.canvas.height) : width / 2;
    // Each picture keeps its aspect ratio inside its slot, like object-fit: contain.
    const place = (source: SplitSource | null, x: number, slot: number) => {
      const video = source?.canvas;
      if (!source || !video || video.width === 0 || video.height === 0) return;
      const scale = Math.min(slot / video.width, height / video.height);
      const w = video.width * scale;
      const h = video.height * scale;
      const left = x + (slot - w) / 2;
      const top = (height - h) / 2;
      context.save();
      context.filter = source.filter ?? "none";
      context.translate(left + (source.flipX ? w : 0), top + (source.flipY ? h : 0));
      context.scale(source.flipX ? -1 : 1, source.flipY ? -1 : 1);
      context.drawImage(video, 0, 0, w, h);
      context.restore();
      // Overlay settings are screen pixels over the displayed video: keep the same size relative to the picture.
      const rect = video.getBoundingClientRect();
      const shown = Math.min(rect.width / video.width, rect.height / video.height);
      if (source.reticles && shown > 0) drawReticles(context, source.reticles, x + slot / 2, height / 2, scale / shown);
      if (source.sight && shown > 0) {
        const k = scale / shown;
        drawRangeSight(context, source.sight.sight, source.sight.display, x + slot / 2 + source.sight.offset.x * k, height / 2 + source.sight.offset.y * k, k);
      }
      if (source.range && shown > 0) {
        const k = scale / shown;
        drawRangeDisplay(context, source.range.display, x + slot / 2 + source.range.cx * k, height / 2 + source.range.cy * k, source.range.top, source.range.color, k);
      }
      // A hidden pane has no screen size: its overlay is drawn as for a 540 px high pane.
      if (source.thermal) drawThermalOverlay(context, source.thermal.config, source.thermal.readings, { x: left, y: top, width: w, height: h }, shown > 0 ? scale / shown : Math.max(1, h / 540));
    };
    place(left, 0, leftWidth);
    place(right, leftWidth, width - leftWidth);
  }

  private async openSegment(format: (typeof FORMATS)[number]): Promise<string> {
    const opened = await invoke<{ id: number; path: string; directory: string }>("split_open", {
      request: { ...this.request, extension: format.extension },
    });
    this.fileId = opened.id;
    this.file = opened.path;
    this.bytes = 0;
    const id = opened.id;
    const recorder = new MediaRecorder(this.canvas.captureStream(FPS), { mimeType: format.mime, videoBitsPerSecond: BITRATE });
    recorder.ondataavailable = (event) => {
      if (event.data.size === 0) return;
      this.queue = this.queue
        .then(() => event.data.arrayBuffer())
        .then((buffer) => invoke<number>("split_chunk", new Uint8Array(buffer), { headers: { "x-split-id": String(id) } }))
        .then((bytes) => {
          if (this.fileId === id) {
            this.bytes = bytes;
            this.onStatus({ state: "recording", file: this.file, bytes, message: null });
          }
        })
        .catch((error) => this.fail(String(error)));
    };
    recorder.onerror = () => this.fail("ошибка кодировщика");
    recorder.start(CHUNK_MS);
    this.recorder = recorder;
    this.onStatus({ state: "recording", file: this.file, bytes: 0, message: null });
    // Rotate files like the pass-through recorder does.
    this.segmentTimer = window.setTimeout(() => void this.rotate(format), this.segmentMinutes * 60_000);
    return opened.directory;
  }

  private async closeSegment() {
    const recorder = this.recorder;
    const id = this.fileId;
    this.recorder = null;
    if (this.segmentTimer !== null) window.clearTimeout(this.segmentTimer);
    this.segmentTimer = null;
    if (recorder && recorder.state !== "inactive") {
      // The final chunk arrives in ondataavailable right before onstop.
      await new Promise<void>((resolve) => {
        recorder.onstop = () => resolve();
        recorder.stop();
      });
    }
    await this.queue.catch(() => undefined);
    if (id !== null) await invoke("split_close", { id }).catch(() => undefined);
  }

  private async rotate(format: (typeof FORMATS)[number]) {
    if (this.stopped) return;
    await this.closeSegment();
    if (!this.stopped) await this.openSegment(format).catch((error) => this.fail(String(error)));
  }

  private fail(message: string) {
    if (this.stopped) return;
    this.failed = true;
    this.onStatus({ state: "error", file: this.file, bytes: this.bytes, message });
    void this.stop();
  }

  async stop(): Promise<void> {
    if (this.stopped) return;
    this.stopped = true;
    if (this.timer !== null) window.clearInterval(this.timer);
    this.timer = null;
    await this.closeSegment();
    if (!this.failed) this.onStatus({ state: "stopped", file: this.file, bytes: this.bytes, message: null });
  }
}
