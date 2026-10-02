import { memo } from "react";
import { rangeAnchor, rangeRows, type RangeDisplay } from "./rangefinder";
import type { ReticleConfig } from "./types";

/**
 * The distance on the crosshair, as in a rangefinder sight: big digits under the first shown reticle
 * in its colour with a dark halo, target mode and continuous ranging above it, blinking dashes and a
 * pulsing ring while a range is on its way.
 */
export const RangeReadout = memo(function RangeReadout({ display, reticles }: { display: RangeDisplay; reticles: ReticleConfig[] }) {
  const { cx, cy, top, color } = rangeAnchor(reticles);
  return (
    <svg
      className={`range-readout-svg ${display.stale ? "stale" : ""} ${display.ranging ? "ranging" : ""}`}
      style={{ left: `calc(50% + ${cx}px)`, top: `calc(50% + ${cy}px)` }}
      width="1"
      height="1"
      overflow="visible"
      aria-hidden="true"
    >
      {display.ranging && <circle className="ranging-ring" r={Math.max(8, top)} fill="none" stroke={color} strokeWidth="1.5" />}
      <g fill={color} stroke="rgba(0, 0, 0, 0.8)" strokeWidth="3" strokeLinejoin="round" paintOrder="stroke" textAnchor="middle" fontFamily='"IBM Plex Mono", Consolas, monospace'>
        {rangeRows(display, top).map((row, index) => (
          <text key={index} y={row.y} fontSize={row.size} fontWeight={row.weight} className={row.unit !== undefined ? "range-value" : undefined}>
            {row.text}
            {row.unit && <tspan fontSize={Math.round(row.size * 0.55)} dx="4">{row.unit}</tspan>}
          </text>
        ))}
      </g>
    </svg>
  );
});
