import { memo } from "react";
import type { ReticleConfig } from "./types";

type Primitive =
  | { kind: "line"; x1: number; y1: number; x2: number; y2: number; weight: number }
  | { kind: "circle"; r: number; fill: boolean; weight: number };

const line = (x1: number, y1: number, x2: number, y2: number, weight: number): Primitive => ({ kind: "line", x1, y1, x2, y2, weight });

/** Horizontal and vertical arms around the centre, leaving `gap` px empty. */
function arms(h: number, v: number, gap: number, weight: number, top = true): Primitive[] {
  if (gap <= 0) return [line(-h, 0, h, 0, weight), line(0, top ? -v : 0, 0, v, weight)];
  const result: Primitive[] = [];
  if (gap < h) result.push(line(-h, 0, -gap, 0, weight), line(gap, 0, h, 0, weight));
  if (gap < v) {
    if (top) result.push(line(0, -v, 0, -gap, weight));
    result.push(line(0, gap, 0, v, weight));
  }
  return result;
}

/** Geometry of one reticle around its own centre, in screen pixels. */
export function reticlePrimitives(reticle: ReticleConfig): Primitive[] {
  const h = reticle.width / 2;
  const v = reticle.height / 2;
  const t = reticle.thickness;
  const gap = reticle.gap;
  switch (reticle.style) {
    case "cross":
      return arms(h, v, 0, t);
    case "crossGap":
      return arms(h, v, Math.max(gap, t * 3), t);
    case "crossDot":
      return [...arms(h, v, Math.max(gap, t * 3), t), { kind: "circle", r: Math.max(t, 1.5), fill: true, weight: 0 }];
    case "circleCross":
      return [...arms(h, v, gap, t), { kind: "circle", r: reticle.radius, fill: false, weight: t }];
    case "circle":
      return [{ kind: "circle", r: reticle.radius, fill: false, weight: t }];
    case "dot":
      return [{ kind: "circle", r: reticle.radius, fill: true, weight: 0 }];
    case "tee":
      return arms(h, v, gap, t, false);
    case "duplex": {
      // Thin precise centre, thick outer posts that stay visible at a glance.
      const hInner = h * 0.5;
      const vInner = v * 0.5;
      return [
        ...arms(hInner, vInner, gap, t),
        line(-h, 0, -hInner, 0, t * 3),
        line(hInner, 0, h, 0, t * 3),
        line(0, -v, 0, -vInner, t * 3),
        line(0, vInner, 0, v, t * 3),
      ];
    }
    case "brackets": {
      const arm = Math.min(reticle.radius, h, v);
      return [
        line(-h, -v, -h + arm, -v, t), line(-h, -v, -h, -v + arm, t),
        line(h, -v, h - arm, -v, t), line(h, -v, h, -v + arm, t),
        line(-h, v, -h + arm, v, t), line(-h, v, -h, v - arm, t),
        line(h, v, h - arm, v, t), line(h, v, h, v - arm, t),
      ];
    }
  }
}

/**
 * Draws reticles on a 2D canvas exactly as the SVG layer shows them, for recordings.
 * `k` converts the on-screen CSS pixels of the reticle settings into canvas pixels.
 */
export function drawReticles(context: CanvasRenderingContext2D, reticles: ReticleConfig[], cx: number, cy: number, k: number) {
  const stroke = (items: Primitive[], color: string, extra: number) => {
    context.strokeStyle = color;
    context.fillStyle = color;
    for (const item of items) {
      context.beginPath();
      if (item.kind === "line") {
        context.lineWidth = Math.max(1, (item.weight + extra) * k);
        context.lineCap = extra ? "square" : "butt";
        context.moveTo(item.x1 * k, item.y1 * k);
        context.lineTo(item.x2 * k, item.y2 * k);
        context.stroke();
      } else if (item.fill) {
        context.arc(0, 0, Math.max(0.5, (item.r + extra / 2) * k), 0, Math.PI * 2);
        context.fill();
      } else {
        context.lineWidth = Math.max(1, (item.weight + extra) * k);
        context.arc(0, 0, item.r * k, 0, Math.PI * 2);
        context.stroke();
      }
    }
  };
  for (const reticle of reticles) {
    if (!reticle.enabled) continue;
    const items = reticlePrimitives(reticle);
    context.save();
    context.translate(cx + reticle.offsetX * k, cy + reticle.offsetY * k);
    context.globalAlpha = reticle.opacity * 0.7;
    if (reticle.outline) stroke(items, "#000000", 2);
    context.globalAlpha = reticle.opacity;
    stroke(items, reticle.color, 0);
    context.restore();
  }
}

function Primitives({ items, color, halo }: { items: Primitive[]; color: string; halo: boolean }) {
  const extra = halo ? 2 : 0;
  return (
    <>
      {items.map((item, index) =>
        item.kind === "line" ? (
          <line
            key={index}
            x1={item.x1}
            y1={item.y1}
            x2={item.x2}
            y2={item.y2}
            stroke={color}
            strokeWidth={item.weight + extra}
            strokeLinecap={halo ? "square" : "butt"}
            shapeRendering="crispEdges"
          />
        ) : (
          <circle
            key={index}
            r={item.fill ? item.r + extra / 2 : item.r}
            fill={item.fill ? color : "none"}
            stroke={item.fill ? "none" : color}
            strokeWidth={item.fill ? 0 : item.weight + extra}
          />
        ),
      )}
    </>
  );
}

function ReticleShape({ reticle }: { reticle: ReticleConfig }) {
  const items = reticlePrimitives(reticle);
  return (
    <g transform={`translate(${reticle.offsetX} ${reticle.offsetY})`} opacity={reticle.opacity}>
      {reticle.outline && (
        <g opacity={0.7}>
          <Primitives items={items} color="#000000" halo />
        </g>
      )}
      <Primitives items={items} color={reticle.color} halo={false} />
    </g>
  );
}

/** Up to three configurable reticles centred on the video pane. */
export const ReticleLayer = memo(function ReticleLayer({ reticles }: { reticles: ReticleConfig[] }) {
  const active = reticles.filter((reticle) => reticle.enabled);
  if (!active.length) return null;
  return (
    <svg className="reticle-layer" aria-hidden="true">
      <svg x="50%" y="50%" overflow="visible">
        {active.map((reticle, index) => (
          <ReticleShape key={index} reticle={reticle} />
        ))}
      </svg>
    </svg>
  );
});
