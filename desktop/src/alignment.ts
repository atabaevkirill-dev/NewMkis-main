import type { ReticleConfig } from "./types";

/** Hot-target position in one camera, in that camera's video pixels. */
export interface TargetFix {
  x: number;
  y: number;
  /** Video frame size. */
  width: number;
  height: number;
  /** Displayed CSS pixels per video pixel (object-fit: contain). */
  scale: number;
}

/** Coarse search runs on a copy this wide; the centroid is then refined on the full frame. */
export const COARSE_WIDTH = 192;
/** Peak must stand this far (0–255 luma) above the frame mean, or there is no distinct target. */
const MIN_CONTRAST = 40;
/** A "target" covering more of the frame than this is a bright scene, not a target. */
const MAX_BLOB_SHARE = 0.2;

const luma = (data: Uint8ClampedArray, index: number) => 0.299 * data[index] + 0.587 * data[index + 1] + 0.114 * data[index + 2];

/**
 * Finds the brightest compact blob (white-hot thermal: the hottest spot) in a downscaled frame.
 * Returns its bounding box in coarse pixels and the luma threshold that delimits it.
 */
export function findBlob(image: ImageData): { x0: number; y0: number; x1: number; y1: number; threshold: number } | null {
  const { width, height, data } = image;
  const count = width * height;
  const values = new Float32Array(count);
  let peak = 0;
  let peakAt = 0;
  let sum = 0;
  for (let i = 0; i < count; i += 1) {
    const value = luma(data, i * 4);
    values[i] = value;
    sum += value;
    if (value > peak) {
      peak = value;
      peakAt = i;
    }
  }
  const mean = sum / count;
  if (peak - mean < MIN_CONTRAST) return null;
  const threshold = mean + (peak - mean) * 0.6;

  // Flood-fill from the peak: only the blob that contains it, not every bright pixel in the scene.
  const seen = new Uint8Array(count);
  const stack = [peakAt];
  seen[peakAt] = 1;
  let x0 = width, y0 = height, x1 = 0, y1 = 0, size = 0;
  while (stack.length) {
    const index = stack.pop()!;
    const x = index % width;
    const y = (index - x) / width;
    size += 1;
    if (size > count * MAX_BLOB_SHARE) return null;
    x0 = Math.min(x0, x); x1 = Math.max(x1, x);
    y0 = Math.min(y0, y); y1 = Math.max(y1, y);
    for (const next of [index - 1, index + 1, index - width, index + width]) {
      if (next < 0 || next >= count || seen[next]) continue;
      if ((next === index - 1 && x === 0) || (next === index + 1 && x === width - 1)) continue;
      seen[next] = 1;
      if (values[next] >= threshold) stack.push(next);
    }
  }
  return { x0, y0, x1, y1, threshold };
}

/** Intensity-weighted centroid of the pixels above `threshold` in a full-resolution crop. */
export function refineCentroid(image: ImageData, threshold: number): { x: number; y: number } | null {
  const { width, height, data } = image;
  let weight = 0;
  let sx = 0;
  let sy = 0;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const excess = luma(data, (y * width + x) * 4) - threshold;
      if (excess <= 0) continue;
      weight += excess;
      sx += excess * (x + 0.5);
      sy += excess * (y + 0.5);
    }
  }
  return weight > 0 ? { x: sx / weight, y: sy / weight } : null;
}

/** Centre of the first enabled reticle, in video pixels (reticle offsets are CSS pixels). */
export function reticleCentre(fix: TargetFix, reticles: ReticleConfig[]): { x: number; y: number } {
  const reticle = reticles.find((item) => item.enabled) ?? reticles[0];
  const offsetX = reticle ? reticle.offsetX : 0;
  const offsetY = reticle ? reticle.offsetY : 0;
  return { x: fix.width / 2 + offsetX / fix.scale, y: fix.height / 2 + offsetY / fix.scale };
}

export interface AxisError {
  dx: number;
  dy: number;
}

/** Target offset from the reticle centre; +x right, +y down (screen convention). */
export function axisError(fix: TargetFix | null, reticles: ReticleConfig[]): AxisError | null {
  if (!fix) return null;
  const centre = reticleCentre(fix, reticles);
  return { dx: fix.x - centre.x, dy: fix.y - centre.y };
}

export const within = (error: AxisError | null, tolerance: number) => error !== null && Math.abs(error.dx) <= tolerance && Math.abs(error.dy) <= tolerance;

export const signed = (value: number) => `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(1)}`;
