import type { RangeReading, RangeTarget, RangefinderConfig, RangefinderStatus, RangefinderTargetMode, ReticleConfig } from "./types";

/** A single measurement older than this is shown dimmed: it may no longer be where the reticle points. */
export const STALE_MS = 5000;
/** The targets of one measurement arrive back to back within this. */
const BURST_MS = 300;
/** After a D-pad move ends the platform needs a moment before a range is meaningful. */
export const SETTLE_MS = 700;
const HISTORY = 20;

const CODES = ["одна цель", "есть цель ближе", "есть цель дальше", "есть цели ближе и дальше", "нет цели в стробе"];
export const describeCode = (code: number) => CODES[code] ?? `состояние ${code}`;

export const formatMetres = (value: number | null | undefined) => (value === null || value === undefined ? "—" : `${value.toFixed(1)} м`);

export const INITIAL_RANGEFINDER: RangefinderStatus = { connected: null, message: "", continuous: false, reading: null, history: [] };

/** The target shown at the reticle: the first one with a distance. */
export const mainTarget = (reading: RangeReading | null): RangeTarget | null =>
  reading ? reading.targets.find((target) => target.distance !== null) ?? reading.targets[0] ?? null : null;

export interface RangeLabel {
  text: string;
  note: string;
  stale: boolean;
}

/** What the reticle shows for a measurement. */
export function rangeLabel(reading: RangeReading | null, now = Date.now()): RangeLabel | null {
  if (!reading) return null;
  const target = mainTarget(reading);
  const found = reading.targets.filter((item) => item.distance !== null).length;
  const notes = [
    target && target.distance === null ? describeCode(4) : "",
    found > 1 ? `ещё ${found - 1} цел.` : "",
    ...reading.faults.filter((fault) => fault !== "нет отражения"),
  ].filter(Boolean);
  return {
    text: target && target.distance !== null ? formatMetres(target.distance) : "— м",
    note: notes.join(" · "),
    stale: !reading.continuous && now - reading.at > STALE_MS,
  };
}

/** Folds one target event into the state: the targets of one measurement form one reading. */
export function addTarget(status: RangefinderStatus, target: RangeTarget, continuous: boolean, now = Date.now()): RangefinderStatus {
  const current = status.reading;
  const same = current !== null && target.index > 0 && now - current.at < BURST_MS && current.continuous === continuous;
  const reading: RangeReading = same ? { ...current, targets: [...current.targets, target] } : { targets: [target], at: now, continuous, faults: [] };
  const history = same ? [reading, ...status.history.slice(1)] : [reading, ...status.history].slice(0, HISTORY);
  return { ...status, connected: true, reading, history };
}

/** A fault report belongs to the measurement it follows. */
export function addFaults(status: RangefinderStatus, faults: string[], now = Date.now()): RangefinderStatus {
  if (!status.reading || now - status.reading.at > 1000) return status;
  const reading = { ...status.reading, faults };
  return { ...status, reading, history: [reading, ...status.history.slice(1)] };
}

/** A single range still waiting for its reply is shown as «ranging» for at most this long. */
export const RANGING_MS = 3000;

const MODE_LABELS: Record<RangefinderTargetMode, string> = { first: "1-я цель", last: "посл. цель", multi: "мульти" };

/** What the crosshair shows, as in a rangefinder sight: the distance under it, indicators above it. */
export interface RangeDisplay {
  /** Digits, «– – – –» while ranging, «- - - -» when nothing is in the gate. */
  value: string;
  unit: string;
  /** Above the crosshair: target mode, continuous ranging. */
  top: string;
  /** Further targets in multi-target mode, nearest first. */
  extra: string[];
  /** Below everything: no target, faults. */
  note: string;
  stale: boolean;
  ranging: boolean;
}

export function rangeDisplay(status: RangefinderStatus, settings: RangefinderConfig, rangingAt: number | null, now = Date.now()): RangeDisplay | null {
  const ranging = rangingAt !== null && now - rangingAt < RANGING_MS;
  const reading = status.reading;
  const top = [MODE_LABELS[settings.targetMode], status.continuous ? `● ${settings.frequencyHz} Гц` : ""].filter(Boolean).join(" · ");
  if (ranging && !status.continuous) return { value: "– – – –", unit: "", top, extra: [], note: "", stale: false, ranging: true };
  // As in a rangefinder sight the range field is always there: dashes until the first range.
  if (!reading) {
    if (status.connected === null) return null;
    return { value: "- - - -", unit: "", top, extra: [], note: status.connected ? "R — замер" : "нет связи с дальномером", stale: false, ranging: false };
  }
  const target = mainTarget(reading);
  const found = reading ? reading.targets.filter((item) => item.distance !== null && item !== target) : [];
  const faults = reading ? reading.faults.filter((fault) => fault !== "нет отражения") : [];
  return {
    value: target && target.distance !== null ? target.distance.toFixed(1) : "- - - -",
    unit: target && target.distance !== null ? "м" : "",
    top,
    extra: found.map((item) => `${item.index + 1} ▸ ${(item.distance as number).toFixed(1)}`),
    note: [target && target.distance === null ? describeCode(4) : "", ...faults].filter(Boolean).join(" · "),
    stale: reading !== null && !reading.continuous && now - reading.at > STALE_MS,
    ranging: false,
  };
}

/** Empty space a line of digits needs below the centre to sit inside a reticle's gap, CSS px. */
const DIGITS_ROOM = 32;
/** However large the reticle, the digits stay this close to the aiming point. */
const MAX_TOP = 70;

/**
 * Where the digits go on the first shown reticle, in CSS px from the pane centre: `top` is the distance
 * from the aiming point to the top of the digits. Like a rangefinder sight they sit right under the
 * aiming point: inside the empty gap of a cross when there is room, under a small circle or dot, inside
 * a large circle or bracket box, on the lower post of a cross without a gap (readable by the halo). The
 * length of the lines never moves them (a 2000 px cross keeps them at the centre).
 */
export function rangeAnchor(reticles: ReticleConfig[]): { cx: number; cy: number; top: number; color: string } {
  const reticle = reticles.find((item) => item.enabled);
  if (!reticle) return { cx: 0, cy: 0, top: 12, color: "#ffffff" };
  const thickness = reticle.thickness;
  let top: number;
  switch (reticle.style) {
    case "circle":
      top = reticle.radius >= DIGITS_ROOM + 10 ? 10 : reticle.radius + 6;
      break;
    case "brackets": {
      const inner = Math.min(reticle.width, reticle.height) / 2;
      top = inner >= DIGITS_ROOM + 10 ? 10 : inner + 6;
      break;
    }
    case "dot":
      top = reticle.radius + 6;
      break;
    case "cross":
      top = 10;
      break;
    default: {
      // crossGap, crossDot, duplex, tee, circleCross: the arms leave `gap` empty around the centre.
      const gap = reticle.style === "crossGap" || reticle.style === "crossDot" ? Math.max(reticle.gap, thickness * 3) : reticle.gap;
      const mark = reticle.style === "circleCross" ? reticle.radius : reticle.style === "crossDot" ? Math.max(thickness, 1.5) : 0;
      top = gap - mark >= DIGITS_ROOM ? mark + 6 : Math.max(gap, mark) + 6;
    }
  }
  return { cx: reticle.offsetX, cy: reticle.offsetY, top: Math.min(Math.max(top, 8), MAX_TOP), color: reticle.color };
}

/** Text rows of the display relative to the aiming point (CSS px), shared by the screen and the recording. */
export function rangeRows(display: RangeDisplay, top: number): { text: string; y: number; size: number; weight: number; unit?: string }[] {
  const rows: { text: string; y: number; size: number; weight: number; unit?: string }[] = [];
  // Baselines: the digits are 24 px, so their top edge is about `top`.
  if (display.top) rows.push({ text: display.top, y: -(top + 2), size: 11, weight: 600 });
  rows.push({ text: display.value, y: top + 19, size: 24, weight: 700, unit: display.unit });
  let y = top + 36;
  for (const line of display.extra) {
    rows.push({ text: line, y, size: 13, weight: 600 });
    y += 16;
  }
  if (display.note) rows.push({ text: display.note, y: y - 2, size: 11, weight: 500 });
  return rows;
}

/** Draws the display on a 2D canvas as the screen shows it (split recording); `k` converts CSS px to canvas px. */
export function drawRangeDisplay(context: CanvasRenderingContext2D, display: RangeDisplay, cx: number, cy: number, top: number, color: string, k: number) {
  context.save();
  context.globalAlpha = display.stale ? 0.7 : 1;
  context.textAlign = "center";
  context.textBaseline = "alphabetic";
  context.lineJoin = "round";
  context.strokeStyle = "rgba(0, 0, 0, 0.8)";
  context.fillStyle = color;
  for (const row of rangeRows(display, top)) {
    const text = row.unit ? `${row.text} ${row.unit}` : row.text;
    context.font = `${row.weight} ${Math.max(8, Math.round(row.size * k))}px "IBM Plex Mono", Consolas, monospace`;
    context.lineWidth = Math.max(2, 3 * k);
    context.strokeText(text, cx, cy + row.y * k);
    context.fillText(text, cx, cy + row.y * k);
  }
  context.restore();
}
