import { memo, useCallback, useEffect, useRef, useState } from "react";
import type { MouseEvent as ReactMouseEvent, PointerEvent as ReactPointerEvent, RefObject } from "react";
import { Crosshair, RotateCcw } from "lucide-react";
import { thermalMeasure, thermalParamsGet, thermalParamsSet } from "./api";
import { PALETTES, findExtremes, formatTemperature, paletteFilterId, paletteGradient, paletteTable, wantsExtremes, type Point } from "./thermal";
import { NumberField, Toggle } from "./ui";
import type { CameraConfig, MeasureParams, PaletteId, ThermalConfig, ThermalReadings, ThermalSpot, ThermalUnit } from "./types";

/** One poll asks the camera for every point (≈ 40–60 ms each on the stand camera). */
const POLL_MS = 500;

/**
 * SVG filters that recolour a grey (white-hot) picture: luminance first, then a per-channel table of
 * the palette. Used as CSS `filter` on the video canvas, so the canvas keeps the camera's own pixels
 * for alignment and extremes, and as the canvas `filter` of the split recording.
 */
export const PaletteFilters = memo(function PaletteFilters() {
  return (
    <svg className="palette-filters" aria-hidden="true" focusable="false">
      <defs>
        {PALETTES.filter((palette) => palette.id !== "camera").map((palette) => {
          const table = paletteTable(palette.id);
          const values = (channel: number) => table.map((rgb) => rgb[channel].toFixed(4)).join(" ");
          return (
            <filter key={palette.id} id={paletteFilterId(palette.id)} colorInterpolationFilters="sRGB" x="0" y="0" width="100%" height="100%">
              <feColorMatrix type="matrix" values="0.299 0.587 0.114 0 0  0.299 0.587 0.114 0 0  0.299 0.587 0.114 0 0  0 0 0 1 0" />
              <feComponentTransfer>
                <feFuncR type="table" tableValues={values(0)} />
                <feFuncG type="table" tableValues={values(1)} />
                <feFuncB type="table" tableValues={values(2)} />
              </feComponentTransfer>
            </filter>
          );
        })}
      </defs>
    </svg>
  );
});

/** Where the video frame sits inside the pane (object-fit: contain), in pane CSS pixels. */
function useContentBox(paneRef: RefObject<HTMLDivElement | null>, frameWidth: number | null, frameHeight: number | null) {
  const [size, setSize] = useState({ width: 0, height: 0 });
  useEffect(() => {
    const pane = paneRef.current;
    if (!pane) return;
    const observer = new ResizeObserver(([entry]) => setSize({ width: entry.contentRect.width, height: entry.contentRect.height }));
    observer.observe(pane);
    return () => observer.disconnect();
  }, [paneRef]);
  if (!frameWidth || !frameHeight || !size.width || !size.height) return null;
  const scale = Math.min(size.width / frameWidth, size.height / frameHeight);
  return { left: (size.width - frameWidth * scale) / 2, top: (size.height - frameHeight * scale) / 2, width: frameWidth * scale, height: frameHeight * scale };
}

const unit = (value: number) => Math.min(1, Math.max(0, value));

function CrossMark() {
  return (
    <svg className="spot-cross" viewBox="-12 -12 24 24" aria-hidden="true">
      <path className="halo" d="M-11 0H-4M4 0H11M0 -11V-4M0 4V11" />
      <path d="M-11 0H-4M4 0H11M0 -11V-4M0 4V11" />
    </svg>
  );
}

/**
 * Thermal overlay of one pane: up to three measuring points the operator drags, markers that follow
 * the hottest and coldest point, the palette scale labelled with them. Every number comes from the
 * camera (`thermalMeasure`); without an answer the labels show «—».
 */
export function ThermalLayer({ camera, frameWidth, frameHeight, paneRef, onSpotsChange, onReadings, indicate }: {
  camera: CameraConfig;
  frameWidth: number | null;
  frameHeight: number | null;
  paneRef: RefObject<HTMLDivElement | null>;
  onSpotsChange: (spots: ThermalSpot[]) => void;
  onReadings: (id: CameraConfig["id"], readings: ThermalReadings | null) => void;
  /** Short message in the pane (e.g. «all three points are placed»). */
  indicate: (message: string) => void;
}) {
  const thermal = camera.thermal;
  const box = useContentBox(paneRef, frameWidth, frameHeight);
  const layerRef = useRef<HTMLDivElement>(null);
  const [readings, setReadings] = useState<ThermalReadings | null>(null);
  const [drag, setDrag] = useState<{ index: number; x: number; y: number } | null>(null);
  const cameraRef = useRef(camera);
  cameraRef.current = camera;
  const onReadingsRef = useRef(onReadings);
  onReadingsRef.current = onReadings;
  const { id, ip, onvifPort, username } = camera;
  const measuring = thermal.spots.some((spot) => spot.enabled) || wantsExtremes(thermal);

  useEffect(() => {
    const report = (next: ThermalReadings | null) => {
      setReadings(next);
      onReadingsRef.current(id, next);
    };
    if (!measuring) return report(null);
    let alive = true;
    let busy = false;
    const scratch = document.createElement("canvas");
    const tick = async () => {
      if (busy) return;
      busy = true;
      try {
        const current = cameraRef.current;
        const config = current.thermal;
        const canvas = paneRef.current?.querySelector<HTMLCanvasElement>("canvas.video-canvas") ?? null;
        const extremes = wantsExtremes(config) && canvas ? findExtremes(canvas, scratch) : null;
        const slots = config.spots.flatMap((spot, index) => (spot.enabled ? [index] : []));
        const points: [number, number][] = slots.map((index) => [config.spots[index].x, config.spots[index].y]);
        if (extremes) points.push([extremes.hot.x, extremes.hot.y], [extremes.cold.x, extremes.cold.y]);
        let values: (number | null)[] = points.map(() => null);
        let error: string | null = null;
        if (points.length) {
          try {
            values = await thermalMeasure(current, points);
          } catch (failure) {
            error = String(failure);
          }
        }
        if (!alive) return;
        const spots = config.spots.map((): number | null => null);
        slots.forEach((slot, index) => {
          spots[slot] = values[index];
        });
        const extreme = (point: Point | undefined, value: number | null) => (point ? { ...point, value } : null);
        report({ spots, hot: extreme(extremes?.hot, values[slots.length] ?? null), cold: extreme(extremes?.cold, values[slots.length + 1] ?? null), error });
      } finally {
        busy = false;
      }
    };
    void tick();
    const timer = window.setInterval(() => void tick(), POLL_MS);
    return () => {
      alive = false;
      window.clearInterval(timer);
      report(null);
    };
  }, [measuring, id, ip, onvifPort, username, paneRef]);

  const fraction = (event: { clientX: number; clientY: number }) => {
    const rect = layerRef.current?.getBoundingClientRect();
    if (!rect || !rect.width || !rect.height) return null;
    return { x: unit((event.clientX - rect.left) / rect.width), y: unit((event.clientY - rect.top) / rect.height) };
  };

  // Double click on the picture places the next free point there.
  const place = (event: ReactMouseEvent) => {
    const at = fraction(event);
    if (!at) return;
    const free = thermal.spots.findIndex((spot) => !spot.enabled);
    if (free < 0) return indicate("ВСЕ 3 ТОЧКИ ЗАНЯТЫ · ДВОЙНОЙ ЩЕЛЧОК ПО ТОЧКЕ УБИРАЕТ ЕЁ");
    onSpotsChange(thermal.spots.map((spot, index) => (index === free ? { enabled: true, ...at } : spot)));
  };

  const grab = (index: number) => (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (event.button !== 0) return;
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    setDrag({ index, x: thermal.spots[index].x, y: thermal.spots[index].y });
  };
  const move = (index: number) => (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (drag?.index !== index) return;
    const at = fraction(event);
    if (at) setDrag({ index, ...at });
  };
  const release = (index: number) => () => {
    if (drag?.index !== index) return;
    onSpotsChange(thermal.spots.map((spot, slot) => (slot === index ? { ...spot, x: drag.x, y: drag.y } : spot)));
    setDrag(null);
  };
  const remove = (index: number) => (event: ReactMouseEvent) => {
    event.stopPropagation();
    onSpotsChange(thermal.spots.map((spot, slot) => (slot === index ? { ...spot, enabled: false } : spot)));
  };

  if (!box) return null;
  const position = (point: Point) => ({ left: `${point.x * 100}%`, top: `${point.y * 100}%` });
  return (
    <div ref={layerRef} className="thermal-layer" style={{ left: box.left, top: box.top, width: box.width, height: box.height }} onDoubleClick={place}>
      {thermal.colorBar && (
        <div className="thermal-scale" title="Шкала палитры: самая горячая и самая холодная точка кадра">
          <b>{formatTemperature(readings?.hot?.value)}</b>
          <i style={{ background: paletteGradient(thermal.palette === "camera" ? "whiteHot" : thermal.palette, "to top") }} />
          <b>{formatTemperature(readings?.cold?.value)}</b>
        </div>
      )}
      {thermal.hotSpot && readings?.hot && (
        <div className="extreme hot" style={position(readings.hot)}>
          <i />
          <span>▲ {formatTemperature(readings.hot.value)}</span>
        </div>
      )}
      {thermal.coldSpot && readings?.cold && (
        <div className="extreme cold" style={position(readings.cold)}>
          <i />
          <span>▼ {formatTemperature(readings.cold.value)}</span>
        </div>
      )}
      {thermal.spots.map((spot, index) => {
        if (!spot.enabled) return null;
        const dragging = drag?.index === index;
        const at = dragging ? drag : spot;
        return (
          <button
            key={index}
            type="button"
            className={`spot ${dragging ? "dragging" : ""}`}
            style={position(at)}
            onPointerDown={grab(index)}
            onPointerMove={move(index)}
            onPointerUp={release(index)}
            onPointerCancel={() => setDrag(null)}
            onDoubleClick={remove(index)}
            title={`Точка T${index + 1}: перетащите · двойной щелчок убирает`}
          >
            <CrossMark />
            <span>T{index + 1} {dragging ? "…" : formatTemperature(readings?.spots[index])}</span>
          </button>
        );
      })}
      {readings?.error && <div className="thermal-error" title={readings.error}>Температура: {readings.error}</div>}
    </div>
  );
}

/** Camera fields with the ranges the stand camera advertises (`RadiometryManager getCaps`). */
const PARAM_FIELDS: { key: keyof MeasureParams; label: string; unit?: string; min: number; max: number; digits: number }[] = [
  { key: "emissivity", label: "Излучательность ε", min: 0.01, max: 1, digits: 2 },
  { key: "distance", label: "Дистанция до объекта", unit: "м", min: 0, max: 10000, digits: 1 },
  { key: "reflectedTemperature", label: "Отражённая температура", unit: "°C", min: -50, max: 327.7, digits: 1 },
  { key: "atmosphericTemperature", label: "Температура воздуха", unit: "°C", min: -50, max: 327.7, digits: 1 },
  { key: "humidity", label: "Влажность", unit: "%", min: 0, max: 100, digits: 0 },
  { key: "transmissivity", label: "Пропускание атмосферы", min: 0, max: 1, digits: 2 },
];

/** Typical emissivities (thermography reference tables); the surface itself decides, check when it matters. */
const EMISSIVITY_PRESETS: [string, number][] = [
  ["Кожа человека", 0.98],
  ["Вода", 0.96],
  ["Резина", 0.95],
  ["Краска матовая", 0.94],
  ["Бумага", 0.93],
  ["Кирпич", 0.93],
  ["Бетон", 0.92],
  ["Дерево", 0.9],
  ["Пластик", 0.9],
  ["Сталь окисленная", 0.8],
  ["Алюминий анодированный", 0.77],
  ["Алюминий окисленный", 0.3],
  ["Сталь полированная", 0.07],
];

const roundTo = (value: number, digits: number) => Math.round(value * 10 ** digits) / 10 ** digits;

/**
 * Measuring parameters kept by the camera: read when shown, written only by the button. The camera
 * corrects its temperatures with them (emissivity matters most).
 */
function CameraParams({ camera }: { camera: CameraConfig }) {
  const [stored, setStored] = useState<MeasureParams | null>(null);
  const [draft, setDraft] = useState<Partial<Record<keyof MeasureParams, number>>>({});
  const [status, setStatus] = useState<{ text: string; error: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const cameraRef = useRef(camera);
  cameraRef.current = camera;
  const { id, ip, onvifPort, username } = camera;

  const load = useCallback(async () => {
    setBusy(true);
    try {
      setStored(await thermalParamsGet(cameraRef.current));
      setDraft({});
      setStatus(null);
    } catch (error) {
      setStatus({ text: String(error), error: true });
    } finally {
      setBusy(false);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load, id, ip, onvifPort, username]);

  const fields = stored ? PARAM_FIELDS.filter((field) => stored[field.key] !== null) : [];
  const changed = fields.filter((field) => draft[field.key] !== undefined && draft[field.key] !== stored?.[field.key]);
  const invalid = changed.some((field) => {
    const value = draft[field.key] as number;
    return !(value >= field.min && value <= field.max);
  });
  const write = async () => {
    setBusy(true);
    try {
      const params = Object.fromEntries(changed.map((field) => [field.key, roundTo(draft[field.key] as number, field.digits)]));
      setStored(await thermalParamsSet(cameraRef.current, params));
      setDraft({});
      setStatus({ text: "Записано в камеру", error: false });
    } catch (error) {
      setStatus({ text: String(error), error: true });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="camera-params">
      <div className="params-head">
        <span>Параметры измерения · хранятся в камере</span>
        <button type="button" onClick={() => void load()} disabled={busy}>{busy ? "…" : "обновить"}</button>
      </div>
      {fields.map((field) => (
        <div key={field.key} className={`param-row ${draft[field.key] !== undefined && draft[field.key] !== stored?.[field.key] ? "changed" : ""}`}>
          <span>{field.label}</span>
          <NumberField
            value={draft[field.key] ?? (stored?.[field.key] as number)}
            unit={field.unit}
            className="compact"
            min={field.min}
            max={field.max}
            onChange={(next) => setDraft((current) => ({ ...current, [field.key]: next }))}
          />
        </div>
      ))}
      {fields.some((field) => field.key === "emissivity") && (
        <select
          className="emissivity-presets"
          value=""
          onChange={(event) => event.target.value && setDraft((current) => ({ ...current, emissivity: Number(event.target.value) }))}
          title="Подставить типовую излучательность материала"
        >
          <option value="">Типовая ε материала…</option>
          {EMISSIVITY_PRESETS.map(([name, value]) => (
            <option key={name} value={value}>{name} · {value.toFixed(2)}</option>
          ))}
        </select>
      )}
      {stored && (
        <div className="params-actions">
          <button type="button" onClick={() => void write()} disabled={busy || changed.length === 0 || invalid}>Записать в камеру</button>
          {changed.length > 0 && <button type="button" onClick={() => setDraft({})} disabled={busy}>Отменить</button>}
        </div>
      )}
      {status && <p className={`hint ${status.error ? "error" : ""}`}>{status.text}</p>}
    </div>
  );
}

const UNIT_LABELS: { value: ThermalUnit; label: string }[] = [
  { value: "camera", label: "как подписывает камера" },
  { value: "celsius", label: "°C" },
  { value: "fahrenheit", label: "°F → пересчёт в °C" },
];

/** Thermal settings in the camera drawer: palette, measuring points, extremes and the unit. */
export function ThermalEditor({ camera, thermal, readings, onChange, onRetry }: {
  camera: CameraConfig;
  thermal: ThermalConfig;
  readings: ThermalReadings | null;
  onChange: (thermal: ThermalConfig) => void;
  onRetry: () => void;
}) {
  const patch = (update: Partial<ThermalConfig>) => onChange({ ...thermal, ...update });
  const patchSpot = (slot: number, update: Partial<ThermalSpot>) => patch({ spots: thermal.spots.map((spot, index) => (index === slot ? { ...spot, ...update } : spot)) });
  return (
    <div className="thermal-editor">
      <div className="slider-row">
        <span>Палитра</span>
        <select value={thermal.palette} onChange={(event) => patch({ palette: event.target.value as PaletteId })}>
          {PALETTES.map((palette) => (
            <option key={palette.id} value={palette.id}>{palette.label}</option>
          ))}
        </select>
      </div>
      <div className="palette-strip" style={{ background: paletteGradient(thermal.palette === "camera" ? "whiteHot" : thermal.palette) }} title="холодное → горячее" />
      <div className="setting-line">
        <span>Шкала палитры <small>с температурой макс. и мин. кадра</small></span>
        <Toggle value={thermal.colorBar} onChange={(colorBar) => patch({ colorBar })} />
      </div>
      <div className="setting-line">
        <span>▲ Самая горячая точка <small>{formatTemperature(readings?.hot?.value)}</small></span>
        <Toggle value={thermal.hotSpot} onChange={(hotSpot) => patch({ hotSpot })} />
      </div>
      <div className="setting-line">
        <span>▼ Самая холодная точка <small>{formatTemperature(readings?.cold?.value)}</small></span>
        <Toggle value={thermal.coldSpot} onChange={(coldSpot) => patch({ coldSpot })} />
      </div>
      {thermal.spots.map((spot, index) => (
        <div key={index} className="spot-row">
          <Crosshair />
          <strong>T{index + 1}</strong>
          <code>{spot.enabled ? formatTemperature(readings?.spots[index]) : "выкл."}</code>
          <button type="button" onClick={() => patchSpot(index, { enabled: true, x: 0.5, y: 0.5 })} title="Поставить в центр кадра">
            <RotateCcw /> центр
          </button>
          <Toggle value={spot.enabled} onChange={(enabled) => patchSpot(index, { enabled })} title={`Точка T${index + 1}`} />
        </div>
      ))}
      <div className="slider-row">
        <span>Единица</span>
        <select value={thermal.unit} onChange={(event) => patch({ unit: event.target.value as ThermalUnit })}>
          {UNIT_LABELS.map((item) => (
            <option key={item.value} value={item.value}>{item.label}</option>
          ))}
        </select>
      </div>
      <CameraParams camera={camera} />
      {readings?.error && (
        <div className="thermal-status">
          <p className="hint error">{readings.error}</p>
          <button type="button" onClick={onRetry}>Повторить</button>
        </div>
      )}
      <p className="hint">
        Двойной щелчок по видео ставит точку, перетаскивание двигает, двойной щелчок по точке убирает. Температуру измеряет камера (HTTP API, пароль веб-интерфейса). Палитры перекрашивают картинку «белый горячий».
      </p>
    </div>
  );
}
