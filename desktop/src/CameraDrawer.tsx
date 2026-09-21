import { useEffect, useRef, useState } from "react";
import { Eye, EyeOff, RefreshCw, RotateCcw, Save, Trash2, X, Zap } from "lucide-react";
import { cameraLensStep, getSecret, hasSecret, setSecret } from "./api";
import { RETICLE_COLORS, RETICLE_LIMITS, RETICLE_STYLES, clamp, defaultReticles, isIPv4 } from "./config";
import { NumberField, Section, Toggle } from "./ui";
import type { CameraConfig, Notify, ProbeResult, ReticleConfig, ReticleStyle } from "./types";

type SectionId = "network" | "lens" | "reticle" | "display";
const REVEAL_MS = 10_000;

function SecretField({ cameraId, notify }: { cameraId: string; notify: Notify }) {
  const [stored, setStored] = useState<boolean | null>(null);
  const [draft, setDraft] = useState("");
  const [visible, setVisible] = useState(false);
  // True while the input shows the stored password (not something the operator typed).
  const [revealed, setRevealed] = useState(false);
  const revealedRef = useRef(false);
  const hideTimer = useRef<number | null>(null);

  const markRevealed = (value: boolean) => {
    revealedRef.current = value;
    setRevealed(value);
  };

  useEffect(() => {
    let alive = true;
    hasSecret(cameraId)
      .then((value) => alive && setStored(value))
      .catch(() => alive && setStored(null));
    return () => {
      alive = false;
      if (hideTimer.current !== null) window.clearTimeout(hideTimer.current);
    };
  }, [cameraId]);

  const hide = () => {
    setVisible(false);
    if (revealedRef.current) setDraft("");
    markRevealed(false);
  };

  // Reveal is an explicit, temporary action: the stored password leaves the keychain only on request.
  const reveal = async () => {
    if (visible) return hide();
    if (!draft && stored) {
      try {
        setDraft(await getSecret(cameraId));
        markRevealed(true);
      } catch (error) {
        return notify(`Связка ключей: ${String(error)}`, "error");
      }
    }
    setVisible(true);
    if (hideTimer.current !== null) window.clearTimeout(hideTimer.current);
    hideTimer.current = window.setTimeout(hide, REVEAL_MS);
  };

  const store = async (password: string) => {
    try {
      await setSecret(cameraId, password);
      setStored(Boolean(password));
      setDraft("");
      setVisible(false);
      markRevealed(false);
      notify(password ? "Пароль сохранён в системной связке ключей" : "Пароль удалён из связки ключей");
    } catch (error) {
      notify(`Связка ключей: ${String(error)}`, "error");
    }
  };

  return (
    <label className="field wide">
      <span>
        Пароль {stored ? <b className="tag">в связке ключей</b> : stored === false ? <b className="tag muted">не задан</b> : null}
      </span>
      <div className="input-action">
        <input
          type={visible ? "text" : "password"}
          value={draft}
          autoComplete="off"
          spellCheck={false}
          placeholder={stored ? "•••••••• сохранён" : "Введите пароль"}
          onChange={(event) => {
            setDraft(event.target.value);
            markRevealed(false);
          }}
        />
        <button type="button" onClick={() => void reveal()} disabled={!draft && !stored} title={visible ? "Скрыть" : "Показать на 10 секунд"}>
          {visible ? <EyeOff /> : <Eye />}
        </button>
        <button type="button" onClick={() => void store(draft)} disabled={!draft || revealed} title="Сохранить в связке ключей">
          <Save />
        </button>
        {stored && (
          <button type="button" onClick={() => void store("")} title="Удалить пароль">
            <Trash2 />
          </button>
        )}
      </div>
    </label>
  );
}

const USES: Record<"size" | "gap" | "radius" | "thickness", ReticleStyle[]> = {
  size: ["circleCross", "cross", "crossGap", "crossDot", "duplex", "tee", "brackets"],
  gap: ["circleCross", "crossGap", "crossDot", "duplex", "tee"],
  radius: ["circleCross", "circle", "dot", "brackets"],
  thickness: ["circleCross", "cross", "crossGap", "crossDot", "duplex", "tee", "circle", "brackets"],
};

function SliderRow({ label, value, range, sliderMax, unit, disabled, onChange }: {
  label: string;
  value: number;
  range: readonly [number, number];
  sliderMax?: number;
  unit: string;
  disabled?: boolean;
  onChange: (value: number) => void;
}) {
  const top = sliderMax ?? range[1];
  return (
    <div className={`slider-row ${disabled ? "dim" : ""}`}>
      <span>{label}</span>
      <input type="range" min={range[0]} max={top} value={Math.min(value, top)} disabled={disabled} aria-label={label} onChange={(event) => onChange(Number(event.target.value))} />
      <NumberField value={value} integer unit={unit} className="compact" min={range[0]} max={range[1]} onChange={(next) => onChange(clamp(next, range))} />
    </div>
  );
}

function ReticleEditor({ reticles, onChange, linked, onLinkedChange, bothLabel }: {
  reticles: ReticleConfig[];
  onChange: (next: ReticleConfig[]) => void;
  linked: boolean;
  onLinkedChange: (linked: boolean) => void;
  bothLabel: string;
}) {
  const [slot, setSlot] = useState(0);
  const reticle = reticles[slot];
  const patch = (update: Partial<ReticleConfig>) => onChange(reticles.map((item, index) => (index === slot ? { ...item, ...update } : item)));
  const uses = (kind: keyof typeof USES) => USES[kind].includes(reticle.style);

  return (
    <div className="reticle-editor">
      <div className={`setting-line reticle-link ${linked ? "on" : ""}`}>
        <span>
          Применять к обоим окнам <small>{linked ? `изменения идут в ${bothLabel}` : "прицелы этого окна скопируются во второе"}</small>
        </span>
        <Toggle value={linked} onChange={onLinkedChange} title={`Одинаковые прицелы для ${bothLabel}`} />
      </div>
      <div className="slot-row">
        <div className="slots" role="tablist" aria-label="Прицелы">
          {reticles.map((item, index) => (
            <button key={index} role="tab" aria-selected={slot === index} className={slot === index ? "active" : ""} onClick={() => setSlot(index)} type="button" title={`Прицел ${index + 1}${item.enabled ? " · показан" : ""}`}>
              {index + 1}
              {item.enabled && <i />}
            </button>
          ))}
        </div>
        <Toggle value={reticle.enabled} onChange={(enabled) => patch({ enabled })} label="Показывать" />
      </div>
      <div className="slider-row">
        <span>Вид</span>
        <select value={reticle.style} onChange={(event) => patch({ style: event.target.value as ReticleStyle })}>
          {RETICLE_STYLES.map((style) => (
            <option key={style.value} value={style.value}>{style.label}</option>
          ))}
        </select>
      </div>
      <div className="slider-row">
        <span>Цвет</span>
        <div className="swatches">
          {RETICLE_COLORS.map((color) => (
            <button key={color} type="button" className={color === reticle.color ? "active" : ""} style={{ background: color }} onClick={() => patch({ color })} title={color} aria-label={`Цвет ${color}`} />
          ))}
          <input type="color" value={reticle.color} onChange={(event) => patch({ color: event.target.value })} title="Свой цвет" aria-label="Свой цвет" />
        </div>
      </div>
      <SliderRow label="Гориз." value={reticle.width} range={RETICLE_LIMITS.width} sliderMax={600} unit="px" disabled={!uses("size")} onChange={(width) => patch({ width })} />
      <SliderRow label="Верт." value={reticle.height} range={RETICLE_LIMITS.height} sliderMax={600} unit="px" disabled={!uses("size")} onChange={(height) => patch({ height })} />
      <SliderRow label="Толщина" value={reticle.thickness} range={RETICLE_LIMITS.thickness} unit="px" disabled={!uses("thickness")} onChange={(thickness) => patch({ thickness })} />
      <SliderRow label="Разрыв" value={reticle.gap} range={RETICLE_LIMITS.gap} sliderMax={120} unit="px" disabled={!uses("gap")} onChange={(gap) => patch({ gap })} />
      <SliderRow label="Радиус" value={reticle.radius} range={RETICLE_LIMITS.radius} sliderMax={200} unit="px" disabled={!uses("radius")} onChange={(radius) => patch({ radius })} />
      <SliderRow label="Непрозр." value={Math.round(reticle.opacity * 100)} range={[10, 100]} unit="%" onChange={(value) => patch({ opacity: value / 100 })} />
      <div className="slider-row offsets">
        <span>Смещение</span>
        <NumberField label="X" value={reticle.offsetX} integer unit="px" className="compact" min={RETICLE_LIMITS.offsetX[0]} max={RETICLE_LIMITS.offsetX[1]} onChange={(offsetX) => patch({ offsetX: clamp(offsetX, RETICLE_LIMITS.offsetX) })} />
        <NumberField label="Y" value={reticle.offsetY} integer unit="px" className="compact" min={RETICLE_LIMITS.offsetY[0]} max={RETICLE_LIMITS.offsetY[1]} onChange={(offsetY) => patch({ offsetY: clamp(offsetY, RETICLE_LIMITS.offsetY) })} />
      </div>
      <div className="reticle-actions">
        <Toggle value={reticle.outline} onChange={(outline) => patch({ outline })} label="Тёмная обводка" />
        <button type="button" onClick={() => patch({ ...defaultReticles()[slot], enabled: reticle.enabled })} title="Вернуть параметры по умолчанию">
          <RotateCcw /> Сброс
        </button>
      </div>
    </div>
  );
}

export function CameraDrawer({ camera, side, label, otherLabel, probe, reticlesLinked, onClose, onChange, onReticlesChange, onReticlesLinkedChange, onProbe, notify }: {
  camera: CameraConfig;
  side: "left" | "right";
  label: string;
  otherLabel: string;
  probe: ProbeResult | undefined;
  reticlesLinked: boolean;
  onClose: () => void;
  onChange: (patch: Partial<CameraConfig>) => void;
  onReticlesChange: (reticles: ReticleConfig[]) => void;
  onReticlesLinkedChange: (linked: boolean) => void;
  onProbe: () => void;
  notify: Notify;
}) {
  const [open, setOpen] = useState<SectionId | null>("network");
  const accent = side === "left" ? "blue" : "amber";
  const toggle = (id: SectionId) => setOpen((current) => (current === id ? null : id));
  const step = (mode: "zoom" | "focus", direction: 1 | -1) =>
    void cameraLensStep(camera.id, mode, direction).catch((error) => notify(`${label} · ${String(error)}`, "error"));
  const enabledReticles = camera.reticles.filter((reticle) => reticle.enabled).length;

  return (
    <aside className={`camera-drawer ${side} ${accent}`} aria-label={`Настройки ${label}`}>
      <header className="drawer-head">
        <i className={`dot ${accent}`} />
        <div>
          <strong>{label}</strong>
          <small>{side === "left" ? "оптическая" : "тепловизионная · эталон"}</small>
        </div>
        <span className={`link-state ${probe?.connected ? "on" : ""}`} title={probe?.error ?? undefined}>
          {probe ? (probe.connected ? "связь" : "нет связи") : "—"}
        </span>
        <button className="icon-button" onClick={onClose} type="button" title="Закрыть">
          <X />
        </button>
      </header>

      <div className="drawer-body">
        <Section title="Сеть и доступ" open={open === "network"} onToggle={() => toggle("network")}>
          <div className="form-grid">
            <label className={`field wide ${isIPv4(camera.ip) ? "" : "invalid"}`}>
              <span>IP-адрес</span>
              <input value={camera.ip} spellCheck={false} onChange={(event) => onChange({ ip: event.target.value.trim() })} />
            </label>
            <NumberField label="ONVIF порт" value={camera.onvifPort} integer min={1} max={65535} onChange={(onvifPort) => onChange({ onvifPort })} />
            <NumberField label="RTSP порт" value={camera.rtspPort} integer min={1} max={65535} onChange={(rtspPort) => onChange({ rtspPort })} />
            <label className="field wide">
              <span>Логин</span>
              <input value={camera.username} autoComplete="off" spellCheck={false} onChange={(event) => onChange({ username: event.target.value })} />
            </label>
            <SecretField cameraId={camera.id} notify={notify} />
          </div>
          <div className="row-actions">
            <button type="button" onClick={onProbe}>
              <RefreshCw /> Проверить связь
            </button>
            <button type="button" disabled title="Декодирование RTSP ещё не подключено к новому клиенту">
              <Zap /> Подключить
            </button>
          </div>
          <div className="setting-line">
            <span>Автоподключение</span>
            <Toggle value={camera.autoConnect} onChange={(autoConnect) => onChange({ autoConnect })} />
          </div>
        </Section>

        <Section title="Объектив · ONVIF" badge="не подключён" open={open === "lens"} onToggle={() => toggle("lens")}>
          <div className="lens-grid">
            <span>ZOOM</span>
            <button type="button" onClick={() => step("zoom", -1)}>−</button>
            <button type="button" onClick={() => step("zoom", 1)}>+</button>
            <span>FOCUS</span>
            <button type="button" onClick={() => step("focus", -1)}>Near</button>
            <button type="button" onClick={() => step("focus", 1)}>Far</button>
          </div>
          <p className="hint">Колесо над видео — zoom · ПКМ + колесо — focus</p>
        </Section>

        <Section title="Перекрестие" badge={`${enabledReticles}/3${reticlesLinked ? " · оба окна" : ""}`} open={open === "reticle"} onToggle={() => toggle("reticle")}>
          <ReticleEditor
            reticles={camera.reticles}
            onChange={onReticlesChange}
            linked={reticlesLinked}
            onLinkedChange={onReticlesLinkedChange}
            bothLabel={`${label} и ${otherLabel}`}
          />
        </Section>

        <Section title="Отображение" open={open === "display"} onToggle={() => toggle("display")}>
          <div className="setting-line">
            <span>
              OSD камеры <small>имя · FPS · ONVIF</small>
            </span>
            <Toggle value={camera.osd} onChange={(osd) => onChange({ osd })} />
          </div>
          <div className="setting-line">
            <span>Профиль потока</span>
            <strong>{camera.profile}</strong>
          </div>
        </Section>
      </div>
    </aside>
  );
}
