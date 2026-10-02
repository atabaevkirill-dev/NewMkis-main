import { memo, useId } from "react";
import type { RangeDisplay } from "./rangefinder";
import { sightLayout, sightRows, sightShape, type SightPrimitive } from "./sightGeometry";
import type { RangeSightConfig } from "./types";

function Primitives({ items, color, extra }: { items: SightPrimitive[]; color: string; extra: number }) {
  return (
    <>
      {items.map((item, index) => {
        if (item.kind === "line") return <line key={index} x1={item.x1} y1={item.y1} x2={item.x2} y2={item.y2} stroke={color} strokeWidth={item.width + extra} strokeLinecap="round" />;
        if (item.kind === "circle") {
          return item.fill
            ? <circle key={index} cx={item.cx} cy={item.cy} r={item.r + extra / 2} fill={color} />
            : <circle key={index} cx={item.cx} cy={item.cy} r={item.r} fill="none" stroke={color} strokeWidth={item.width + extra} />;
        }
        return <polygon key={index} points={item.points.map(([x, y]) => `${x},${y}`).join(" ")} fill={item.fill && extra === 0 ? color : "none"} stroke={color} strokeWidth={item.width + extra} strokeLinejoin="round" />;
      })}
    </>
  );
}

/**
 * Rangefinder sight on a video pane, around the laser aiming point (pane centre + this camera's offset),
 * with the distance built in. The collimator glows; the ranging box blinks while a range is on its way.
 */
export const RangeSight = memo(function RangeSight({ sight, offset, display }: {
  sight: RangeSightConfig;
  offset: { x: number; y: number };
  display: RangeDisplay | null;
}) {
  // React ids contain characters that do not belong in a url(#…) reference.
  const glowId = `sight-glow-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const shape = sightShape(sight.style, sight.scale);
  const layout = sightLayout(sight.style, sight.scale);
  const collimator = sight.style === "collimator";
  const ranging = display?.ranging ?? false;
  return (
    <svg
      className={`range-sight ${ranging ? "ranging" : ""}`}
      style={{ left: `calc(50% + ${offset.x}px)`, top: `calc(50% + ${offset.y}px)` }}
      width="1"
      height="1"
      overflow="visible"
      aria-hidden="true"
    >
      {collimator && (
        <defs>
          <filter id={glowId} x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="2.4" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
      )}
      <g opacity={sight.brightness / 100}>
        {!collimator && (
          <g opacity={0.6}>
            <Primitives items={[...shape.steady, ...shape.ranging]} color="#000000" extra={2} />
          </g>
        )}
        <g filter={collimator ? `url(#${glowId})` : undefined}>
          <Primitives items={shape.steady} color={sight.color} extra={0} />
          <g className="sight-ranging-part">
            <Primitives items={shape.ranging} color={sight.color} extra={0} />
          </g>
        </g>
        {ranging && sight.style !== "box" && <circle className="ranging-ring" r={14 * (sight.scale / 100)} fill="none" stroke={sight.color} strokeWidth="1.5" />}
      </g>
      {display && (
        <g
          className={display.stale ? "stale" : undefined}
          fill={sight.color}
          stroke="rgba(0, 0, 0, 0.8)"
          strokeWidth="3"
          strokeLinejoin="round"
          paintOrder="stroke"
          textAnchor={layout.anchor}
          fontFamily='"IBM Plex Mono", Consolas, monospace'
        >
          {sightRows(sight.style, sight.scale, display).map((row, index) => (
            <text key={index} x={row.x} y={row.y} fontSize={row.size} fontWeight={row.weight} className={row.unit !== undefined ? "range-value" : undefined}>
              {row.text}
              {row.unit && <tspan fontSize={Math.round(row.size * 0.55)} dx="4">{row.unit}</tspan>}
            </text>
          ))}
        </g>
      )}
    </svg>
  );
});
