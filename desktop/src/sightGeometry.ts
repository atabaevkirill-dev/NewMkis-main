import type { RangeDisplay } from "./rangefinder";
import type { RangeSightConfig, RangeSightStyle } from "./types";

/**
 * Geometry of the rangefinder sights, around the laser aiming point, in CSS px. The screen (SVG) and the
 * split recording (canvas) draw the same primitives and the same readout layout.
 */
export type SightPrimitive =
  | { kind: "line"; x1: number; y1: number; x2: number; y2: number; width: number }
  | { kind: "circle"; cx: number; cy: number; r: number; width: number; fill: boolean }
  | { kind: "path"; points: [number, number][]; width: number; fill: boolean };

/** Part of the sight that blinks while a range is on its way (the ranging box). */
export interface SightShape {
  steady: SightPrimitive[];
  ranging: SightPrimitive[];
}

export function sightShape(style: RangeSightStyle, scale: number): SightShape {
  const s = scale / 100;
  const line = (x1: number, y1: number, x2: number, y2: number, width = 1.3): SightPrimitive => ({ kind: "line", x1: x1 * s, y1: y1 * s, x2: x2 * s, y2: y2 * s, width });
  const dot = (cx: number, cy: number, r: number): SightPrimitive => ({ kind: "circle", cx: cx * s, cy: cy * s, r: r * s, width: 0, fill: true });
  const ring = (r: number, width: number): SightPrimitive => ({ kind: "circle", cx: 0, cy: 0, r: r * s, width, fill: false });
  const arms: [number, number][] = [[1, 0], [-1, 0], [0, 1], [0, -1]];
  switch (style) {
    case "tactical": {
      // Fine cross with a gap at the aiming point, five mil-dots per arm, heavy outer posts.
      const steady: SightPrimitive[] = [dot(0, 0, 1.3)];
      for (const [dx, dy] of arms) {
        steady.push(line(dx * 7, dy * 7, dx * 112, dy * 112, 1.2), line(dx * 112, dy * 112, dx * 260, dy * 260, 4));
        for (let mark = 1; mark <= 5; mark += 1) steady.push(dot(dx * mark * 19, dy * mark * 19, 1.9));
      }
      return { steady, ranging: [] };
    }
    case "chevron":
      // ACOG-like: the tip of the chevron is the aiming point; stadia below it, side bars.
      return {
        steady: [
          { kind: "path", points: [[-16 * s, 15 * s], [0, 0], [16 * s, 15 * s], [11 * s, 15 * s], [0, 5.5 * s], [-11 * s, 15 * s]], width: 1, fill: true },
          line(0, 28, 0, 124, 1.2),
          line(-15, 46, 15, 46, 1.7),
          line(-11, 66, 11, 66, 1.7),
          line(-8, 86, 8, 86, 1.7),
          line(-5, 106, 5, 106, 1.7),
          line(-170, 0, -42, 0, 1.4),
          line(42, 0, 170, 0, 1.4),
        ],
        ranging: [],
      };
    case "box": {
      // Rangefinder display: corners of the laser aiming box, a small cross, frame lines (none below:
      // the distance goes there).
      const h = 20;
      const c = 8;
      const corners: SightPrimitive[] = [];
      for (const [sx, sy] of [[-1, -1], [1, -1], [-1, 1], [1, 1]] as const) {
        corners.push(line(sx * h, sy * h, sx * (h - c), sy * h, 1.9), line(sx * h, sy * h, sx * h, sy * (h - c), 1.9));
      }
      return {
        steady: [line(-5, 0, 5, 0, 1.2), line(0, -5, 0, 5, 1.2), line(-230, 0, -34, 0, 1.2), line(34, 0, 230, 0, 1.2), line(0, -230, 0, -34, 1.2)],
        ranging: corners,
      };
    }
    case "collimator":
      // Holographic sight: glowing ring with ticks and a centre dot.
      return {
        steady: [ring(30, 2), dot(0, 0, 2.6), line(0, -32, 0, -40, 2), line(0, 32, 0, 40, 2), line(-32, 0, -40, 0, 2), line(32, 0, 40, 0, 2)],
        ranging: [],
      };
  }
}

/** Where each sight puts the distance (CSS px from the aiming point) and how the text is anchored. */
export function sightLayout(style: RangeSightStyle, scale: number): { valueX: number; valueY: number; anchor: "start" | "middle"; topX: number; topY: number } {
  const s = scale / 100;
  switch (style) {
    case "tactical":
      // Lower right quadrant, clear of the arms and the dots.
      return { valueX: 12 * s + 6, valueY: 26 * s + 22, anchor: "start", topX: 12 * s + 6, topY: -(14 * s + 6) };
    case "chevron":
      return { valueX: 22 * s + 6, valueY: 30 * s + 14, anchor: "start", topX: 22 * s + 6, topY: -(10 * s + 4) };
    case "box":
      return { valueX: 0, valueY: 20 * s + 30, anchor: "middle", topX: 0, topY: -(20 * s + 9) };
    case "collimator":
      return { valueX: 0, valueY: 40 * s + 28, anchor: "middle", topX: 0, topY: -(40 * s + 8) };
  }
}

export interface SightRow {
  text: string;
  x: number;
  y: number;
  size: number;
  weight: number;
  unit?: string;
}

/** Text rows of the readout inside a sight. */
export function sightRows(style: RangeSightStyle, scale: number, display: RangeDisplay): SightRow[] {
  const layout = sightLayout(style, scale);
  const rows: SightRow[] = [];
  if (display.top) rows.push({ text: display.top, x: layout.topX, y: layout.topY, size: 11, weight: 600 });
  rows.push({ text: display.value, x: layout.valueX, y: layout.valueY, size: 24, weight: 700, unit: display.unit });
  let y = layout.valueY + 17;
  for (const line of display.extra) {
    rows.push({ text: line, x: layout.valueX, y, size: 13, weight: 600 });
    y += 16;
  }
  if (display.note) rows.push({ text: display.note, x: layout.valueX, y: y - 2, size: 11, weight: 500 });
  return rows;
}

const FONT = '"IBM Plex Mono", Consolas, monospace';

function strokePrimitives(context: CanvasRenderingContext2D, items: SightPrimitive[], color: string, extra: number, k: number) {
  context.strokeStyle = color;
  context.fillStyle = color;
  for (const item of items) {
    context.beginPath();
    if (item.kind === "line") {
      context.lineWidth = Math.max(1, (item.width + extra) * k);
      context.moveTo(item.x1 * k, item.y1 * k);
      context.lineTo(item.x2 * k, item.y2 * k);
      context.stroke();
    } else if (item.kind === "circle") {
      context.arc(item.cx * k, item.cy * k, Math.max(0.5, (item.r + (item.fill ? extra / 2 : 0)) * k), 0, Math.PI * 2);
      if (item.fill) context.fill();
      else {
        context.lineWidth = Math.max(1, (item.width + extra) * k);
        context.stroke();
      }
    } else {
      item.points.forEach(([x, y], index) => (index === 0 ? context.moveTo(x * k, y * k) : context.lineTo(x * k, y * k)));
      context.closePath();
      if (item.fill && extra === 0) context.fill();
      context.lineWidth = Math.max(1, (item.width + extra) * k);
      context.stroke();
    }
  }
}

/**
 * Draws a rangefinder sight with its readout on a 2D canvas as the screen shows it (split recording).
 * `cx`, `cy` is the aiming point on the canvas; `k` converts CSS px into canvas px.
 */
export function drawRangeSight(context: CanvasRenderingContext2D, sight: RangeSightConfig, display: RangeDisplay | null, cx: number, cy: number, k: number) {
  const shape = sightShape(sight.style, sight.scale);
  const items = [...shape.steady, ...shape.ranging];
  context.save();
  context.translate(cx, cy);
  context.globalAlpha = sight.brightness / 100;
  context.lineCap = "round";
  context.lineJoin = "round";
  if (sight.style !== "collimator") {
    context.globalAlpha = (sight.brightness / 100) * 0.6;
    strokePrimitives(context, items, "#000000", 2, k);
    context.globalAlpha = sight.brightness / 100;
  } else {
    context.shadowColor = sight.color;
    context.shadowBlur = 8 * k;
  }
  strokePrimitives(context, items, sight.color, 0, k);
  context.shadowBlur = 0;
  if (display) {
    context.globalAlpha = display.stale ? 0.7 : 1;
    context.textBaseline = "alphabetic";
    context.strokeStyle = "rgba(0, 0, 0, 0.8)";
    context.fillStyle = sight.color;
    for (const row of sightRows(sight.style, sight.scale, display)) {
      context.textAlign = row.x === 0 ? "center" : "left";
      context.font = `${row.weight} ${Math.max(8, Math.round(row.size * k))}px ${FONT}`;
      const text = row.unit ? `${row.text} ${row.unit}` : row.text;
      context.lineWidth = Math.max(2, 3 * k);
      context.strokeText(text, row.x * k, row.y * k);
      context.fillText(text, row.x * k, row.y * k);
    }
  }
  context.restore();
}
