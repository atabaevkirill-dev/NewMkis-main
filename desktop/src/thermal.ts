import type { PaletteId, ThermalConfig, ThermalReadings } from "./types";

/**
 * False-colour palettes, cold → hot. They recolour the camera's white-hot picture by brightness, so
 * they are right only while the camera itself sends «white hot» (grey) video.
 */
export const PALETTES: { id: PaletteId; label: string; stops: [number, string][] }[] = [
  { id: "camera", label: "Как с камеры", stops: [[0, "#000000"], [1, "#ffffff"]] },
  { id: "whiteHot", label: "Белый горячий", stops: [[0, "#000000"], [1, "#ffffff"]] },
  { id: "blackHot", label: "Чёрный горячий", stops: [[0, "#ffffff"], [1, "#000000"]] },
  { id: "ironbow", label: "Железо", stops: [[0, "#000000"], [0.12, "#1c0754"], [0.26, "#560a8c"], [0.4, "#99138e"], [0.53, "#cf3460"], [0.66, "#ee6a26"], [0.8, "#fba40c"], [0.92, "#fdde4e"], [1, "#ffffff"]] },
  { id: "rainbow", label: "Радуга", stops: [[0, "#000000"], [0.1, "#3b0c8a"], [0.22, "#1d3fff"], [0.36, "#00b2ff"], [0.48, "#00e6a0"], [0.6, "#7cff2c"], [0.72, "#f2ef00"], [0.84, "#ff9300"], [0.94, "#ff2000"], [1, "#ffffff"]] },
  { id: "rainbowHc", label: "Радуга HC", stops: [[0, "#000000"], [0.12, "#ff00ff"], [0.26, "#0000ff"], [0.4, "#00ffff"], [0.54, "#00ff00"], [0.68, "#ffff00"], [0.84, "#ff0000"], [1, "#ffffff"]] },
  { id: "arctic", label: "Арктика", stops: [[0, "#000018"], [0.2, "#0a2a68"], [0.4, "#1764b8"], [0.55, "#4aa6de"], [0.66, "#bfe4f4"], [0.76, "#f4c27a"], [0.88, "#f08a2c"], [1, "#fff2b0"]] },
  { id: "iceFire", label: "Лёд и пламя", stops: [[0, "#e6f8ff"], [0.15, "#4cc2ff"], [0.32, "#0a46c8"], [0.5, "#00000c"], [0.66, "#7a0000"], [0.8, "#e02a00"], [0.92, "#ffa000"], [1, "#ffff9a"]] },
  { id: "redHot", label: "Красный горячий", stops: [[0, "#000000"], [0.78, "#d4d4d4"], [0.8, "#ff6040"], [1, "#ff0000"]] },
];

const paletteOf = (id: PaletteId) => PALETTES.find((palette) => palette.id === id) ?? PALETTES[0];

const channels = (hex: string) => [1, 3, 5].map((start) => parseInt(hex.slice(start, start + 2), 16) / 255);

/** The palette sampled at `count` evenly spaced levels: [r, g, b] in 0…1 for each. */
export function paletteTable(id: PaletteId, count = 33): number[][] {
  const stops = paletteOf(id).stops;
  return Array.from({ length: count }, (_, index) => {
    const t = index / (count - 1);
    const upper = Math.max(1, stops.findIndex(([position]) => position >= t));
    const [p0, c0] = stops[upper - 1];
    const [p1, c1] = stops[upper];
    const k = p1 > p0 ? (t - p0) / (p1 - p0) : 0;
    const a = channels(c0);
    const b = channels(c1);
    return a.map((value, channel) => value + (b[channel] - value) * k);
  });
}

/** CSS gradient of the palette, cold at the start of `direction`. */
export const paletteGradient = (id: PaletteId, direction = "to right") =>
  `linear-gradient(${direction}, ${paletteOf(id).stops.map(([position, color]) => `${color} ${position * 100}%`).join(", ")})`;

export const paletteFilterId = (id: PaletteId) => `thermal-palette-${id}`;

/** CSS / canvas `filter` that recolours a picture, or null when it is shown as the camera sends it. */
export const paletteFilter = (id: PaletteId) => (id === "camera" ? null : `url(#${paletteFilterId(id)})`);

export function defaultThermal(enabled: boolean): ThermalConfig {
  return {
    palette: "camera",
    colorBar: enabled,
    spots: [
      { enabled, x: 0.5, y: 0.5 },
      { enabled: false, x: 0.35, y: 0.5 },
      { enabled: false, x: 0.65, y: 0.5 },
    ],
    hotSpot: enabled,
    coldSpot: false,
    unit: "camera",
  };
}

/** Whether the frame extremes have to be found (markers or the labelled palette scale). */
export const wantsExtremes = (thermal: ThermalConfig) => thermal.hotSpot || thermal.coldSpot || thermal.colorBar;

export const formatTemperature = (value: number | null | undefined) => (value === null || value === undefined ? "—" : `${value.toFixed(1)}°C`);

export interface Point {
  x: number;
  y: number;
}

const HOT_COLOR = "#ff5a3c";
const COLD_COLOR = "#6cb6ff";

/**
 * Draws the thermal overlay on a 2D canvas as the screen layer shows it, for the split recording.
 * `box` is the picture on the canvas; `k` converts on-screen CSS pixels into canvas pixels.
 */
export function drawThermalOverlay(
  context: CanvasRenderingContext2D,
  thermal: ThermalConfig,
  readings: ThermalReadings | null,
  box: { x: number; y: number; width: number; height: number },
  k: number,
) {
  const { x, y, width, height } = box;
  context.save();
  context.font = `600 ${Math.max(8, Math.round(10 * k))}px "IBM Plex Mono", Consolas, monospace`;
  context.textBaseline = "middle";
  const label = (text: string, left: number, middle: number, color: string) => {
    const pad = 4 * k;
    const tall = 15 * k;
    context.fillStyle = "rgba(4, 6, 8, 0.62)";
    context.fillRect(left, middle - tall / 2, context.measureText(text).width + pad * 2, tall);
    context.fillStyle = color;
    context.fillText(text, left + pad, middle + 0.5 * k);
  };
  if (thermal.colorBar) {
    const top = y + height * 0.22;
    const bottom = y + height * 0.78;
    const left = x + 8 * k;
    const tall = 15 * k;
    const gap = 4 * k;
    const barTop = top + tall + gap;
    const barBottom = bottom - tall - gap;
    const gradient = context.createLinearGradient(0, barBottom, 0, barTop);
    for (const [position, color] of paletteOf(thermal.palette === "camera" ? "whiteHot" : thermal.palette).stops) gradient.addColorStop(position, color);
    context.fillStyle = gradient;
    context.fillRect(left, barTop, 10 * k, barBottom - barTop);
    context.lineWidth = Math.max(1, k);
    context.strokeStyle = "rgba(255, 255, 255, 0.55)";
    context.strokeRect(left, barTop, 10 * k, barBottom - barTop);
    label(formatTemperature(readings?.hot?.value), left, top + tall / 2, "#ffffff");
    label(formatTemperature(readings?.cold?.value), left, bottom - tall / 2, "#ffffff");
  }
  const at = (point: Point) => ({ px: x + point.x * width, py: y + point.y * height });
  const extreme = (point: { x: number; y: number; value: number | null } | null | undefined, color: string, text: string, sign: string) => {
    if (!point) return;
    const { px, py } = at(point);
    context.beginPath();
    context.arc(px, py, 7 * k, 0, Math.PI * 2);
    context.lineWidth = 4 * k;
    context.strokeStyle = "rgba(0, 0, 0, 0.7)";
    context.stroke();
    context.lineWidth = 2 * k;
    context.strokeStyle = color;
    context.stroke();
    label(`${sign} ${formatTemperature(point.value)}`, px + 5 * k, py - 17.5 * k, text);
  };
  if (thermal.hotSpot) extreme(readings?.hot, HOT_COLOR, "#ffb4a4", "▲");
  if (thermal.coldSpot) extreme(readings?.cold, COLD_COLOR, "#b8dcff", "▼");
  thermal.spots.forEach((spot, index) => {
    if (!spot.enabled) return;
    const { px, py } = at(spot);
    const arms = () => {
      context.beginPath();
      for (const [x0, y0, x1, y1] of [[-11, 0, -4, 0], [4, 0, 11, 0], [0, -11, 0, -4], [0, 4, 0, 11]]) {
        context.moveTo(px + x0 * k, py + y0 * k);
        context.lineTo(px + x1 * k, py + y1 * k);
      }
      context.stroke();
    };
    context.lineWidth = 3.5 * k;
    context.strokeStyle = "rgba(0, 0, 0, 0.75)";
    arms();
    context.lineWidth = 1.5 * k;
    context.strokeStyle = "#ffffff";
    arms();
    label(`T${index + 1} ${formatTemperature(readings?.spots[index])}`, px + 5 * k, py - 17.5 * k, "#ffffff");
  });
  context.restore();
}

const SCAN_WIDTH = 160;

const luma = (data: Uint8ClampedArray, index: number) => 0.299 * data[index] + 0.587 * data[index + 1] + 0.114 * data[index + 2];

/** Brightest and darkest 3×3 neighbourhood of an image, in its pixels. */
function extremesOf(image: ImageData): { hot: Point; cold: Point } {
  const { width, height, data } = image;
  const values = new Float32Array(width * height);
  for (let i = 0; i < values.length; i += 1) values[i] = luma(data, i * 4);
  let hot = { x: 0, y: 0, value: -Infinity };
  let cold = { x: 0, y: 0, value: Infinity };
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      // A 3×3 mean, so a single noisy pixel of the compressed picture does not win.
      let sum = 0;
      let count = 0;
      for (let dy = -1; dy <= 1; dy += 1) {
        const row = y + dy;
        if (row < 0 || row >= height) continue;
        for (let dx = -1; dx <= 1; dx += 1) {
          const column = x + dx;
          if (column < 0 || column >= width) continue;
          sum += values[row * width + column];
          count += 1;
        }
      }
      const value = sum / count;
      if (value > hot.value) hot = { x, y, value };
      if (value < cold.value) cold = { x, y, value };
    }
  }
  return { hot, cold };
}

/**
 * Where the frame is hottest and coldest (white-hot picture: brightest and darkest), as fractions
 * of the frame. A coarse copy finds the area, the full-resolution pixels around it give the point.
 */
export function findExtremes(canvas: HTMLCanvasElement, scratch: HTMLCanvasElement): { hot: Point; cold: Point } | null {
  const { width, height } = canvas;
  const context = canvas.getContext("2d");
  const coarseContext = scratch.getContext("2d", { willReadFrequently: true });
  if (!context || !coarseContext || width < 16 || height < 16) return null;
  scratch.width = SCAN_WIDTH;
  scratch.height = Math.max(1, Math.round((SCAN_WIDTH * height) / width));
  coarseContext.drawImage(canvas, 0, 0, scratch.width, scratch.height);
  const coarse = extremesOf(coarseContext.getImageData(0, 0, scratch.width, scratch.height));
  const factor = width / scratch.width;
  const radius = Math.ceil(factor * 1.5) + 2;
  const refine = (point: Point, pick: "hot" | "cold"): Point => {
    const cx = Math.round((point.x + 0.5) * factor);
    const cy = Math.round((point.y + 0.5) * factor);
    const x0 = Math.max(0, cx - radius);
    const y0 = Math.max(0, cy - radius);
    const x1 = Math.min(width, cx + radius);
    const y1 = Math.min(height, cy + radius);
    const found = extremesOf(context.getImageData(x0, y0, x1 - x0, y1 - y0))[pick];
    return { x: (x0 + found.x + 0.5) / width, y: (y0 + found.y + 0.5) / height };
  };
  return { hot: refine(coarse.hot, "hot"), cold: refine(coarse.cold, "cold") };
}
