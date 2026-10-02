import { useEffect, useState } from "react";
import type { Dispatch, ReactNode, SetStateAction } from "react";
import { Activity, Camera, Check, ChevronUp, CircleDot, Crosshair, Eye, EyeOff, FileText, FolderOpen, LocateFixed, Pencil, Play, Plus, Radio, RefreshCw, Ruler, Square, Trash2, Video, X } from "lucide-react";
import { chooseRecordingDirectory, probeModules, rangefinderGates, rangefinderInfo, rangefinderSelfTest, runPlatformSelfTest, startRockingProfile, stopRockingProfile } from "./api";
import { describeCode, formatMetres, mainTarget, rangeLabel } from "./rangefinder";
import {
  DEFAULT_MODULE_NAMES,
  KIND_LABELS,
  MAX_CUSTOM_MODULES,
  MAX_NAME_LENGTH,
  MODULE_PRESETS,
  PLATFORM_LIMITS,
  RANGEFINDER_LIMITS,
  RETICLE_COLORS,
  SIGHT_LIMITS,
  SIGHT_STYLES,
  isIPv4,
  moduleName,
  profileError,
  removeModule,
  saveModule,
  setModuleHidden,
  validateModuleDraft,
  type ModuleDraft,
} from "./config";
import { moduleKinds, rangefinderSelfTestRecord, selfTestRecord, tcpRecord, testKey } from "./report";
import { Countdown, NumberField, Toggle, useConfirm } from "./ui";
import type { JogControl } from "./useJog";
import type { SplitStatus } from "./splitRecorder";
import type { AppConfig, CameraConfig, DeviceKind, ModuleView, Notify, ProbeResult, RangeOverlay, RangeSightConfig, RangeSightStyle, RangefinderConfig, RangefinderInfo, RangefinderSelfTest, RangefinderStatus, RangefinderTargetMode, RecordingConfig, RecordingEvent, RockingEvent, RockingProfile, TestRecord, VideoStats } from "./types";

export type SystemTab = "summary" | "platform" | "rangefinder" | "tests" | "record";
type SetConfig = Dispatch<SetStateAction<AppConfig>>;

const TABS: { id: SystemTab; label: string; icon: ReactNode }[] = [
  { id: "summary", label: "Сводка", icon: <Activity /> },
  { id: "platform", label: "Поворотка", icon: <LocateFixed /> },
  { id: "rangefinder", label: "Дальномер", icon: <Ruler /> },
  { id: "tests", label: "Тесты", icon: <Radio /> },
  { id: "record", label: "Запись", icon: <Video /> },
];
const KINDS = Object.keys(MODULE_PRESETS) as DeviceKind[];

function linkLabel(module: ModuleView, probe: ProbeResult | undefined): string {
  if (module.hidden) return "скрыт";
  if (!probe) return "—";
  if (!probe.connected) return "нет связи";
  return probe.latencyMs === null ? "связь" : `${probe.latencyMs} мс`;
}

function ModuleRow({ module, probe, onEdit, onToggleHidden, onRemove }: {
  module: ModuleView;
  probe: ProbeResult | undefined;
  onEdit: () => void;
  onToggleHidden: () => void;
  onRemove: () => void;
}) {
  const [armed, confirm] = useConfirm();
  const state = module.hidden ? "hidden" : probe?.connected ? "online" : probe ? "offline" : "unknown";
  return (
    <div className={`module-row ${state}`}>
      <i className="module-dot" />
      <strong title={module.name}>{module.name}</strong>
      <span className="module-kind" title={module.protocol}>{KIND_LABELS[module.kind]} · {module.protocol}</span>
      <code>{module.ip}:{module.port}</code>
      <span className="module-latency" title={probe?.error ?? undefined}>{linkLabel(module, probe)}</span>
      <div className="row-tools">
        <button type="button" onClick={onEdit} title="Переименовать или изменить адрес"><Pencil /></button>
        <button type="button" onClick={onToggleHidden} title={module.hidden ? "Показывать" : "Скрыть из сводки и строки статуса"}>
          {module.hidden ? <Eye /> : <EyeOff />}
        </button>
        {!module.builtin && (
          <button type="button" className={`danger-tool ${armed ? "armed" : ""}`} onClick={() => confirm(onRemove)} title={armed ? "Нажмите ещё раз, чтобы удалить" : "Удалить модуль"}>
            {armed ? "Удалить?" : <Trash2 />}
          </button>
        )}
      </div>
    </div>
  );
}

function ModuleEditor({ draft, setDraft, defaultName, isNew, error, onSave, onCancel }: {
  draft: ModuleDraft;
  setDraft: Dispatch<SetStateAction<ModuleDraft>>;
  /** Set for built-in devices: an empty name restores it. */
  defaultName?: string;
  isNew: boolean;
  error: string | null;
  onSave: () => void;
  onCancel: () => void;
}) {
  return (
    <form className="module-row editing" onSubmit={(event) => { event.preventDefault(); onSave(); }}>
      {isNew ? (
        <select value={draft.kind} aria-label="Тип модуля" onChange={(event) => {
          const kind = event.target.value as DeviceKind;
          setDraft((current) => ({ ...current, kind, port: String(MODULE_PRESETS[kind].port) }));
        }}>
          {KINDS.map((kind) => <option key={kind} value={kind}>{MODULE_PRESETS[kind].label}</option>)}
        </select>
      ) : (
        <span className="module-kind">{KIND_LABELS[draft.kind]}</span>
      )}
      <input
        placeholder={defaultName ?? "Название"}
        title={defaultName ? `Пустое поле вернёт имя «${defaultName}»` : undefined}
        value={draft.name}
        maxLength={MAX_NAME_LENGTH}
        autoFocus
        aria-label="Название"
        onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))}
      />
      <input placeholder="IP-адрес" value={draft.ip} spellCheck={false} aria-label="IP-адрес" className={draft.ip && !isIPv4(draft.ip) ? "invalid" : ""} onChange={(event) => setDraft((current) => ({ ...current, ip: event.target.value.trim() }))} />
      <input placeholder="Порт" value={draft.port} inputMode="numeric" aria-label="Порт" onChange={(event) => setDraft((current) => ({ ...current, port: event.target.value.replace(/\D/g, "") }))} />
      <div className="row-tools">
        <button type="submit" disabled={Boolean(error)} title={error ?? "Сохранить"}><Check /></button>
        <button type="button" onClick={onCancel} title="Отмена"><X /></button>
      </div>
    </form>
  );
}

function ModulesPanel({ modules, probes, probing, onProbe, setConfig, notify }: {
  modules: ModuleView[];
  probes: Record<string, ProbeResult>;
  probing: boolean;
  onProbe: () => void;
  setConfig: SetConfig;
  notify: Notify;
}) {
  const [showHidden, setShowHidden] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState<ModuleDraft>({ kind: "tcp", name: "", ip: "", port: "" });
  const visible = modules.filter((module) => !module.hidden);
  const hiddenCount = modules.length - visible.length;
  const online = visible.filter((module) => probes[module.id]?.connected).length;
  const customCount = modules.filter((module) => !module.builtin).length;
  const isNew = editing === "new";
  const editingModule = modules.find((module) => module.id === editing);
  const error = editing ? validateModuleDraft(draft, editingModule?.builtin ?? false) : null;
  const rows = modules.filter((module) => showHidden || !module.hidden);

  const startAdd = () => {
    setDraft({ kind: "tcp", name: "", ip: "", port: String(MODULE_PRESETS.tcp.port) });
    setEditing("new");
  };
  const startEdit = (module: ModuleView) => {
    setDraft({ kind: module.kind, name: module.name, ip: module.ip, port: String(module.port) });
    setEditing(module.id);
  };
  const commit = () => {
    if (error) return notify(error, "error");
    setConfig((config) => saveModule(config, isNew ? null : editing, draft));
    const name = draft.name.trim() || (editing ? DEFAULT_MODULE_NAMES[editing] : "") || "Модуль";
    notify(isNew ? `Модуль «${name}» добавлен` : `«${name}» · ${draft.ip}:${draft.port} сохранено`);
    setEditing(null);
  };

  return (
    <div className="modules-panel">
      <div className="panel-head">
        <strong>Модули устройств</strong>
        <span className="muted">на связи {online} из {visible.length}</span>
        <div className="spacer" />
        {hiddenCount > 0 && (
          <button className={`chip ${showHidden ? "active" : ""}`} onClick={() => setShowHidden((value) => !value)} type="button">
            {showHidden ? <Eye /> : <EyeOff />} Скрытые · {hiddenCount}
          </button>
        )}
        <button className="chip" onClick={onProbe} type="button" disabled={probing}>
          <RefreshCw className={probing ? "spin" : ""} /> Опросить
        </button>
        <button className="chip primary" onClick={startAdd} type="button" disabled={isNew || customCount >= MAX_CUSTOM_MODULES}>
          <Plus /> Добавить модуль
        </button>
      </div>
      <div className="module-grid">
        {isNew && <ModuleEditor draft={draft} setDraft={setDraft} isNew error={error} onSave={commit} onCancel={() => setEditing(null)} />}
        {rows.map((module) =>
          editing === module.id ? (
            <ModuleEditor key={module.id} draft={draft} setDraft={setDraft} defaultName={module.builtin ? DEFAULT_MODULE_NAMES[module.id] : undefined} isNew={false} error={error} onSave={commit} onCancel={() => setEditing(null)} />
          ) : (
            <ModuleRow
              key={module.id}
              module={module}
              probe={probes[module.id]}
              onEdit={() => startEdit(module)}
              onToggleHidden={() => setConfig((config) => setModuleHidden(config, module.id, !module.hidden))}
              onRemove={() => {
                setConfig((config) => removeModule(config, module.id));
                notify(`Модуль «${module.name}» удалён`);
              }}
            />
          ),
        )}
      </div>
    </div>
  );
}

function rockingLabel(rocking: RockingEvent | null): string {
  if (!rocking) return "ГОТОВ";
  switch (rocking.state) {
    case "running":
      return `ЦИКЛ ${rocking.cycle}/${rocking.cycles}`;
    case "completed":
      return "ЗАВЕРШЕНО";
    case "cancelled":
      return "ОСТАНОВЛЕНО";
    case "failed":
      return "ОШИБКА";
  }
}

function PlatformPanel({ config, setConfig, jog, rocking, notify }: {
  config: AppConfig;
  setConfig: SetConfig;
  jog: JogControl;
  rocking: RockingEvent | null;
  notify: Notify;
}) {
  const [selected, setSelected] = useState(0);
  const profile = config.profiles[selected];
  const error = profileError(profile);
  const { platformIp: ip, platformPort: port } = config;
  const patchProfile = (patch: Partial<RockingProfile>) =>
    setConfig((current) => ({ ...current, profiles: current.profiles.map((item, index) => (index === selected ? { ...item, ...patch } : item)) }));
  const patchJog = (patch: Partial<AppConfig["jog"]>) => setConfig((current) => ({ ...current, jog: { ...current.jog, ...patch } }));
  const start = () => {
    if (error) return notify(error, "error");
    startRockingProfile(ip, port, profile)
      .then(() => notify(`Качка · ${profile.name}`))
      .catch((reason) => notify(`Качка не запущена: ${String(reason)}`, "error"));
  };
  const stop = () =>
    stopRockingProfile(ip, port)
      .then(() => notify("Качка остановлена, оси получили стоп"))
      .catch((reason) => notify(`Стоп не доставлен: ${String(reason)}`, "error"));
  const { pan, tiltMin, tiltMax, panSpeed, tiltSpeed } = PLATFORM_LIMITS;

  return (
    <div className="platform-panel">
      <div className="jog-block">
        <div className="panel-head">
          <strong>{moduleName(config, "platform")}</strong>
          <code>{ip}:{port}</code>
        </div>
        <div className="jog-row">
          <div className="jog-grid" aria-label="Ручное движение: удерживайте кнопку">
            <i /><button type="button" {...jog.bind("up")} aria-label="Вверх">▲</button><i />
            <button type="button" {...jog.bind("left")} aria-label="Влево">◀</button>
            <button type="button" className="stop" onClick={jog.stopNow} aria-label="Стоп">■</button>
            <button type="button" {...jog.bind("right")} aria-label="Вправо">▶</button>
            <i /><button type="button" {...jog.bind("down")} aria-label="Вниз">▼</button><i />
          </div>
          <div className="jog-speeds">
            <NumberField label="PAN" unit="°/с" value={config.jog.panSpeed} min={0.1} max={panSpeed} onChange={(value) => patchJog({ panSpeed: value })} />
            <NumberField label="TILT" unit="°/с" value={config.jog.tiltSpeed} min={0.1} max={tiltSpeed} onChange={(value) => patchJog({ tiltSpeed: value })} />
            <Toggle value={config.jog.invertPan} onChange={(invertPan) => patchJog({ invertPan })} label="Инверт PAN" title="Поменять местами ◀ и ▶" />
            <Toggle value={config.jog.invertTilt} onChange={(invertTilt) => patchJog({ invertTilt })} label="Инверт TILT" title="Поменять местами ▲ и ▼" />
          </div>
        </div>
        <p className="hint">Движение только пока кнопка удерживается · Esc — стоп</p>
      </div>
      <div className="rocking-block">
        <div className="panel-head">
          <strong>Качка</strong>
          <div className="profile-tabs">
            {config.profiles.map((item, index) => (
              <button key={item.id} className={index === selected ? "active" : ""} onClick={() => setSelected(index)} type="button" title={item.name}>{index + 1}</button>
            ))}
          </div>
          <input className="profile-name" value={profile.name} maxLength={32} aria-label="Название профиля" onChange={(event) => patchProfile({ name: event.target.value })} />
          <Toggle value={profile.smoothMotion} onChange={(smoothMotion) => patchProfile({ smoothMotion })} label="Плавно" title="Флаг сохраняется; плавный профиль ещё не реализован в драйвере" />
          <div className="spacer" />
          <span className={`rocking-state ${rocking?.state === "running" ? "on" : ""}`}>{rockingLabel(rocking)}</span>
        </div>
        <div className="rocking-body">
          <div className="number-grid">
            <NumberField label="PAN MIN" unit="°" value={profile.panMin} min={-pan} max={pan} onChange={(panMin) => patchProfile({ panMin })} />
            <NumberField label="PAN MAX" unit="°" value={profile.panMax} min={-pan} max={pan} onChange={(panMax) => patchProfile({ panMax })} />
            <NumberField label="PAN СКОР." unit="°/с" value={profile.panSpeed} min={0.1} max={panSpeed} onChange={(value) => patchProfile({ panSpeed: value })} />
            <NumberField label="ЦИКЛЫ" unit="×" integer value={profile.cycles} min={1} max={1000} onChange={(cycles) => patchProfile({ cycles })} />
            <NumberField label="TILT MIN" unit="°" value={profile.tiltMin} min={tiltMin} max={tiltMax} onChange={(value) => patchProfile({ tiltMin: value })} />
            <NumberField label="TILT MAX" unit="°" value={profile.tiltMax} min={tiltMin} max={tiltMax} onChange={(value) => patchProfile({ tiltMax: value })} />
            <NumberField label="TILT СКОР." unit="°/с" value={profile.tiltSpeed} min={0.1} max={tiltSpeed} onChange={(value) => patchProfile({ tiltSpeed: value })} />
            <NumberField label="ПАУЗА" unit="с" value={profile.pauseSeconds} min={0} max={300} onChange={(pauseSeconds) => patchProfile({ pauseSeconds })} />
          </div>
          <div className="rocking-actions">
            <button className="primary" onClick={start} disabled={Boolean(error)} type="button" title={error ?? "Запустить профиль"}><Play /> Запустить</button>
            <button className="danger" onClick={() => void stop()} type="button"><Square /> Стоп</button>
          </div>
        </div>
        {error && <p className="form-error">{error}</p>}
      </div>
    </div>
  );
}

function testSummary(record: TestRecord | undefined): string {
  if (!record) return "не выполнялась";
  return `${record.ok ? "✓" : "✗"} ${record.detail}`;
}

const TARGET_MODES: { value: RangefinderTargetMode; label: string; title: string }[] = [
  { value: "first", label: "Первая", title: "Ближайшая цель: дальность до первого отражения" },
  { value: "last", label: "Последняя", title: "Дальняя цель: сквозь ветки, сетку, дождь" },
  { value: "multi", label: "Несколько", title: "До трёх целей за один замер" },
];

/**
 * The rangefinder: ranging (single and continuous), its settings and the module. Results arrive as
 * events and show at the reticle and in the status bar too; gates are kept by the module itself.
 */
function RangefinderPanel({ config, setConfig, status, onRange, onContinuous, onRecords, notify }: {
  config: AppConfig;
  setConfig: SetConfig;
  status: RangefinderStatus;
  onRange: () => void;
  onContinuous: (on: boolean) => void;
  onRecords: (records: TestRecord[]) => void;
  notify: Notify;
}) {
  const { rangefinderIp: ip, rangefinderPort: port, rangefinder: settings } = config;
  const name = moduleName(config, "rangefinder");
  const [info, setInfo] = useState<RangefinderInfo | null>(null);
  const [gates, setGates] = useState<{ min: number; max: number } | null>(null);
  const [test, setTest] = useState<RangefinderSelfTest | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const patch = (update: Partial<RangefinderConfig>) => setConfig((current) => ({ ...current, rangefinder: { ...current.rangefinder, ...update } }));
  const sight = settings.sight;
  const patchSight = (update: Partial<RangeSightConfig>) =>
    setConfig((current) => ({ ...current, rangefinder: { ...current.rangefinder, sight: { ...current.rangefinder.sight, ...update } } }));
  const patchOffset = (id: "camera1" | "camera2", update: Partial<{ x: number; y: number }>) =>
    patchSight({ offsets: { ...sight.offsets, [id]: { ...sight.offsets[id], ...update } } });

  const loadInfo = async () => {
    setBusy("info");
    try {
      const value = await rangefinderInfo(ip, port);
      setInfo(value);
      if (value.gateMin !== null && value.gateMax !== null) setGates({ min: value.gateMin, max: value.gateMax });
    } catch (error) {
      notify(`${name}: ${String(error)}`, "error");
    } finally {
      setBusy(null);
    }
  };
  // Opening the panel reads the module (no laser emission).
  useEffect(() => {
    void loadInfo();
  }, [ip, port]);

  const writeGates = async () => {
    if (!gates) return;
    setBusy("gates");
    try {
      const value = await rangefinderGates(ip, port, gates);
      if (value.min !== null && value.max !== null) setGates({ min: value.min, max: value.max });
      notify(`${name}: строб ${value.min ?? "—"}–${value.max ?? "—"} м записан в модуль`);
    } catch (error) {
      notify(`${name}: ${String(error)}`, "error");
    } finally {
      setBusy(null);
    }
  };

  const selfTest = async () => {
    setBusy("selftest");
    try {
      const result = await rangefinderSelfTest(ip, port);
      setTest(result);
      const record = rangefinderSelfTestRecord(result);
      onRecords([record]);
      notify(`${name} · самодиагностика: ${record.detail}`, record.ok ? "info" : "error");
    } catch (error) {
      onRecords([{ moduleId: "rangefinder", kind: "selftest", ok: false, detail: `ошибка связи · ${String(error)}`, at: new Date().toISOString() }]);
      notify(`${name} · ${String(error)}`, "error");
    } finally {
      setBusy(null);
    }
  };

  const reading = status.reading;
  const label = rangeLabel(reading);
  const main = mainTarget(reading);
  const age = reading ? Math.max(0, Math.round((Date.now() - reading.at) / 1000)) : 0;
  const [gateLow, gateHigh] = RANGEFINDER_LIMITS.gate;
  const gatesValid = gates !== null && gates.min >= gateLow && gates.max <= gateHigh && gates.min < gates.max;
  const overlays: { value: RangeOverlay; label: string }[] = [
    { value: "both", label: "на обеих камерах" },
    { value: "camera1", label: moduleName(config, "camera1") },
    { value: "camera2", label: moduleName(config, "camera2") },
    { value: "off", label: "не показывать" },
  ];
  const linkText = status.connected ? "связь" : status.connected === false ? "нет связи" : "—";

  return (
    <div className="rangefinder-panel">
      <div className="range-block">
        <div className="panel-head">
          <strong>{name}</strong>
          <span className={`link-dot ${status.connected ? "on" : status.connected === false ? "off" : ""}`} title={status.message || undefined}>{linkText}</span>
          <code>{ip}:{port}</code>
        </div>
        <div className={`range-readout ${label?.stale ? "stale" : ""}`} title={label?.note || undefined}>
          <strong>{main?.distance !== null && main?.distance !== undefined ? main.distance.toFixed(1) : "—"}</strong>
          <span>м</span>
        </div>
        <p className="hint" title={status.message || undefined}>
          {reading
            ? `${describeCode(main?.code ?? 0)} · ${age} с назад${reading.continuous ? " · непрерывно" : ""}${reading.faults.filter((fault) => fault !== "нет отражения").length ? ` · ${reading.faults.join(", ")}` : ""}`
            : status.connected === false ? status.message : "замеров ещё не было"}
        </p>
        {reading && reading.targets.length > 1 && <p className="hint">{reading.targets.map((target) => `${target.index + 1}: ${formatMetres(target.distance)}`).join(" · ")}</p>}
        <div className="range-actions">
          <button className="primary" type="button" onClick={onRange} disabled={status.continuous} title="Один замер · клавиша R">
            <Crosshair /> Замер · R
          </button>
          <button
            type="button"
            className={status.continuous ? "active" : ""}
            onClick={() => onContinuous(!status.continuous)}
            title={status.continuous ? "Остановить непрерывный замер · Esc" : `Непрерывно ${settings.frequencyHz} Гц, автостоп через ${settings.continuousSeconds} с`}
          >
            {status.continuous ? <Square /> : <Play />} {status.continuous ? "Стоп" : "Непрерывно"}
          </button>
        </div>
      </div>
      <div className="range-settings">
        <div className="setting-line">
          <span>Цель</span>
          <div className="segmented">
            {TARGET_MODES.map((mode) => (
              <button key={mode.value} type="button" className={settings.targetMode === mode.value ? "active" : ""} onClick={() => patch({ targetMode: mode.value })} title={mode.title}>
                {mode.label}
              </button>
            ))}
          </div>
        </div>
        <div className="setting-line">
          <span>Непрерывно <small>частота · автостоп</small></span>
          <div className="inline-fields">
            <NumberField value={settings.frequencyHz} integer unit="Гц" className="compact" min={RANGEFINDER_LIMITS.frequencyHz[0]} max={RANGEFINDER_LIMITS.frequencyHz[1]} onChange={(frequencyHz) => patch({ frequencyHz })} />
            <NumberField value={settings.continuousSeconds} integer unit="с" className="compact" min={RANGEFINDER_LIMITS.continuousSeconds[0]} max={RANGEFINDER_LIMITS.continuousSeconds[1]} onChange={(continuousSeconds) => patch({ continuousSeconds })} />
          </div>
        </div>
        <div className="setting-line">
          <span>Строб, м <small>ближе и дальше не мерить</small></span>
          <div className="inline-fields">
            <NumberField value={gates?.min ?? 0} integer className="compact" min={gateLow} max={gateHigh} onChange={(min) => setGates((current) => ({ min, max: current?.max ?? gateHigh }))} />
            <NumberField value={gates?.max ?? 0} integer className="compact" min={gateLow} max={gateHigh} onChange={(max) => setGates((current) => ({ min: current?.min ?? gateLow, max }))} />
            <button type="button" className="chip" onClick={() => void writeGates()} disabled={!gatesValid || busy !== null} title="Записать строб в модуль">Записать</button>
          </div>
        </div>
        <div className="setting-line">
          <span>Дальность у прицела</span>
          <select value={settings.overlay} onChange={(event) => patch({ overlay: event.target.value as RangeOverlay })}>
            {overlays.map((item) => (
              <option key={item.value} value={item.value}>{item.label}</option>
            ))}
          </select>
        </div>
        <div className="setting-line">
          <span>Замер после остановки поворотки <small>когда отпущена кнопка D-pad</small></span>
          <Toggle value={settings.rangeAfterJog} onChange={(rangeAfterJog) => patch({ rangeAfterJog })} />
        </div>
      </div>
      <div className="range-sight-settings">
        <div className="setting-line">
          <span>Прицел дальномера <small>вместо перекрестий</small></span>
          <div className="inline-fields">
            <select
              value={sight.style}
              title={SIGHT_STYLES.find((item) => item.value === sight.style)?.title}
              onChange={(event) => {
                const style = event.target.value as RangeSightStyle;
                patchSight({ style, color: SIGHT_STYLES.find((item) => item.value === style)?.color ?? sight.color });
              }}
            >
              {SIGHT_STYLES.map((item) => (
                <option key={item.value} value={item.value} title={item.title}>{item.label}</option>
              ))}
            </select>
            <Toggle value={sight.enabled} onChange={(enabled) => patchSight({ enabled })} title="Показывать прицел дальномера (кнопка «Дальномер» вверху)" />
          </div>
        </div>
        <div className="setting-line">
          <span>Цвет</span>
          <div className="swatches">
            {RETICLE_COLORS.map((color) => (
              <button key={color} type="button" className={color === sight.color ? "active" : ""} style={{ background: color }} onClick={() => patchSight({ color })} title={color} aria-label={`Цвет ${color}`} />
            ))}
            <input type="color" value={sight.color} onChange={(event) => patchSight({ color: event.target.value })} title="Свой цвет" aria-label="Свой цвет" />
          </div>
        </div>
        <div className="setting-line">
          <span>Размер · яркость</span>
          <div className="inline-fields">
            <NumberField value={sight.scale} integer unit="%" className="compact" min={SIGHT_LIMITS.scale[0]} max={SIGHT_LIMITS.scale[1]} onChange={(scale) => patchSight({ scale })} />
            <NumberField value={sight.brightness} integer unit="%" className="compact" min={SIGHT_LIMITS.brightness[0]} max={SIGHT_LIMITS.brightness[1]} onChange={(brightness) => patchSight({ brightness })} />
          </div>
        </div>
        {(["camera1", "camera2"] as const).map((id) => (
          <div className="setting-line" key={id}>
            <span>Луч на {moduleName(config, id)} <small>X · Y, px от центра</small></span>
            <div className="inline-fields">
              <NumberField value={sight.offsets[id].x} integer className="compact" min={SIGHT_LIMITS.offset[0]} max={SIGHT_LIMITS.offset[1]} onChange={(x) => patchOffset(id, { x })} />
              <NumberField value={sight.offsets[id].y} integer className="compact" min={SIGHT_LIMITS.offset[0]} max={SIGHT_LIMITS.offset[1]} onChange={(y) => patchOffset(id, { y })} />
            </div>
          </div>
        ))}
      </div>
      <div className="range-module">
        <div className="panel-head">
          <strong>Модуль</strong>
          <span className="muted">1535 нм · класс 1</span>
          <button type="button" className="chip" onClick={() => void loadInfo()} disabled={busy !== null} title="Прочитать сведения (без излучения)">
            <RefreshCw /> {busy === "info" ? "…" : "Обновить"}
          </button>
        </div>
        <p title="Серийный номер (месяц.год № )">Зав. № {info?.serial ?? "—"}</p>
        <p title="Прошивки FPGA и MCU">FPGA {info?.fpga ?? "—"} · MCU {info?.mcu ?? "—"}</p>
        <p title={info?.hardware}>{info?.hardware ?? "—"}</p>
        <p>Импульсов: {info?.pulsesTotal ?? "—"} · с включения {info?.pulsesSincePowerOn ?? "—"}</p>
        <div className="range-test">
          <button type="button" className="chip" onClick={() => void selfTest()} disabled={busy !== null || status.continuous} title="Встроенный тест модуля: один импульс лазера">
            {busy === "selftest" ? "…" : "Самодиагностика"}
          </button>
          <span className={test ? (test.ok ? "pass" : "fail") : ""} title={test?.raw}>
            {test ? (test.ok ? `норма${test.faults.includes("нет отражения") ? " · цели нет" : ` · эхо ${test.echo}`}` : test.faults.join(", ")) : "не выполнялась"}
          </span>
        </div>
      </div>
    </div>
  );
}

function TestsPanel({ config, setConfig, modules, testLog, onRecords, onProbeResults, onReport, notify }: {
  config: AppConfig;
  setConfig: SetConfig;
  modules: ModuleView[];
  testLog: Record<string, TestRecord>;
  onRecords: (records: TestRecord[]) => void;
  onProbeResults: (results: ProbeResult[]) => void;
  onReport: () => void;
  notify: Notify;
}) {
  const [running, setRunning] = useState<string | null>(null);
  const [armed, confirm] = useConfirm();
  const visible = modules.filter((module) => !module.hidden);
  const required = visible.flatMap((module) => moduleKinds(module.id).map((kind) => testKey(module.id, kind)));
  const passed = required.filter((key) => testLog[key]?.ok).length;
  const failed = required.filter((key) => testLog[key] && !testLog[key].ok).length;
  const pending = required.length - passed - failed;
  const platformName = moduleName(config, "platform");
  const patchReport = (patch: Partial<AppConfig["report"]>) => setConfig((current) => ({ ...current, report: { ...current.report, ...patch } }));

  const check = async (targets: ModuleView[], key: string) => {
    setRunning(key);
    try {
      const probed = await probeModules(targets.map(({ id, ip, port }) => ({ id, ip, port })));
      onProbeResults(probed);
      onRecords(probed.map((result) => tcpRecord(result)));
    } catch (error) {
      notify(`Проверка не выполнена: ${String(error)}`, "error");
    } finally {
      setRunning(null);
    }
  };

  const selfTest = async () => {
    setRunning("selftest");
    try {
      const record = selfTestRecord(await runPlatformSelfTest(config.platformIp, config.platformPort));
      onRecords([record]);
      notify(`${platformName} · самодиагностика: ${record.detail}`, record.ok ? "info" : "error");
    } catch (error) {
      onRecords([{ moduleId: "platform", kind: "selftest", ok: false, detail: `ошибка связи · ${String(error)}`, at: new Date().toISOString() }]);
      notify(`${platformName} · ${String(error)}`, "error");
    } finally {
      setRunning(null);
    }
  };

  const rangefinderName = moduleName(config, "rangefinder");
  const rangefinderTest = async () => {
    setRunning("rangefinder-selftest");
    try {
      const record = rangefinderSelfTestRecord(await rangefinderSelfTest(config.rangefinderIp, config.rangefinderPort));
      onRecords([record]);
      notify(`${rangefinderName} · самодиагностика: ${record.detail}`, record.ok ? "info" : "error");
    } catch (error) {
      onRecords([{ moduleId: "rangefinder", kind: "selftest", ok: false, detail: `ошибка связи · ${String(error)}`, at: new Date().toISOString() }]);
      notify(`${rangefinderName} · ${String(error)}`, "error");
    } finally {
      setRunning(null);
    }
  };

  return (
    <div className="tests-panel">
      <div className="panel-head">
        <strong>Проверки</strong>
        <span className="test-counts" title="Для протокола нужны TCP-проверки всех показанных модулей и самодиагностика поворотки и дальномера">
          <b className="pass">✓ {passed}</b> <b className="fail">✗ {failed}</b> <b>— {pending}</b>
        </span>
        <div className="spacer" />
        <label className="report-field"><span>Зав. №</span><input value={config.report.serialNumber} maxLength={64} spellCheck={false} onChange={(event) => patchReport({ serialNumber: event.target.value })} /></label>
        <label className="report-field"><span>Оператор</span><input value={config.report.operator} maxLength={64} onChange={(event) => patchReport({ operator: event.target.value })} /></label>
        <button className="chip" onClick={() => void check(visible, "all")} disabled={running !== null || !visible.length} type="button">
          <Play /> Проверить все
        </button>
        <button className="chip primary" onClick={onReport} type="button" title="Протокол по выполненным проверкам: откроется печать → «Сохранить как PDF»">
          <FileText /> PDF-отчёт
        </button>
      </div>
      <div className="test-grid">
        {visible.map((module) => {
          const tcp = testLog[testKey(module.id, "tcp")];
          const hasSelfTest = moduleKinds(module.id).includes("selftest");
          const self = hasSelfTest ? testLog[testKey(module.id, "selftest")] : undefined;
          const state = [tcp, ...(hasSelfTest ? [self] : [])];
          const tone = state.some((record) => record && !record.ok) ? "fail" : state.every((record) => record?.ok) ? "pass" : "";
          const text = hasSelfTest ? `TCP ${testSummary(tcp)} · самодиагностика ${testSummary(self)}` : testSummary(tcp);
          return (
            <div className={`test-row ${tone}`} key={module.id}>
              <strong title={module.name}>{module.name}</strong>
              <code>{module.ip}:{module.port}</code>
              <span className="test-result" title={text}>{text}</span>
              <div className="row-tools">
                <button type="button" onClick={() => void check([module], module.id)} disabled={running !== null}>TCP</button>
                {module.id === "platform" && (
                  <button type="button" className={armed ? "armed" : ""} onClick={() => confirm(() => void selfTest())} disabled={running !== null} title="Самодиагностика: оси придут в движение">
                    {armed ? "Оси двинутся — да?" : "Самодиагностика"}
                  </button>
                )}
                {module.id === "rangefinder" && (
                  <button type="button" onClick={() => void rangefinderTest()} disabled={running !== null} title="Встроенный тест модуля: один импульс лазера (класс 1, безопасен для глаз)">
                    Самодиагностика
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export interface RecordingControl {
  active: boolean;
  files: Partial<Record<CameraConfig["id"], RecordingEvent>>;
  split: SplitStatus | null;
  /** Auto-stop time (epoch ms) of the running recording, if a timer was set. */
  endsAt: number | null;
  video: Record<CameraConfig["id"], VideoStats>;
  start: () => void;
  stop: () => void;
}

const megabytes = (bytes: number) => `${(bytes / 1_048_576).toFixed(1)} МБ`;
const fileName = (path: string) => path.split(/[\\/]/).pop() ?? path;

function splitLine(control: RecordingControl, bothPlaying: boolean): string {
  const status = control.split;
  if (status?.state === "error") return `ошибка: ${status.message ?? "—"}`;
  if (status?.file) return `${control.active ? "" : "записано: "}${fileName(status.file)} · ${megabytes(status.bytes)}`;
  return bothPlaying ? "готово · кадр обеих камер, перекодирование в окне" : "нужны оба видеопотока";
}

function recordingLine(control: RecordingControl, id: CameraConfig["id"], selected: boolean): string {
  if (!selected) return "не выбрана";
  const event = control.files[id];
  if (event?.state === "error") return `ошибка: ${event.message ?? "—"}`;
  if (control.active) {
    if (control.video[id].state !== "playing") return "нет видеопотока — запись начнётся, когда он пойдёт";
    return event?.file ? `${fileName(event.file)} · ${megabytes(event.bytes)}` : "ожидание ключевого кадра…";
  }
  return event?.file ? `записано: ${fileName(event.file)} · ${megabytes(event.bytes)}` : "готова";
}

function RecordPanel({ config, setConfig, control }: { config: AppConfig; setConfig: SetConfig; control: RecordingControl }) {
  const recording = config.recording;
  const patch = (update: Partial<RecordingConfig>) => setConfig((current) => ({ ...current, recording: { ...current.recording, ...update } }));
  const locked = control.active;
  // Without a chosen directory recording goes to «Videos/MKIS100TEST».
  const bothPlaying = control.video.camera1.state === "playing" && control.video.camera2.state === "playing";
  const separate = recording.layout !== "split";
  const splitWanted = recording.layout !== "separate";
  const ready = (!separate || recording.camera1 || recording.camera2) && (!splitWanted || bothPlaying);
  return (
    <div className="record-panel">
      <div className="record-sources">
        <button className={recording.camera1 || !separate ? "selected blue" : ""} disabled={locked || !separate} onClick={() => patch({ camera1: !recording.camera1 })} type="button" aria-pressed={recording.camera1}><Camera /> {moduleName(config, "camera1")}</button>
        <button className={recording.camera2 || !separate ? "selected amber" : ""} disabled={locked || !separate} onClick={() => patch({ camera2: !recording.camera2 })} type="button" aria-pressed={recording.camera2}><Camera /> {moduleName(config, "camera2")}</button>
      </div>
      <div className="record-settings">
        <label className="field wide">
          <span>Каталог записи</span>
          <div className="input-action">
            <input value={recording.directory} placeholder="Видео\MKIS100TEST (по умолчанию)" readOnly title={recording.directory || "Если каталог не выбран, запись идёт в папку «Видео\MKIS100TEST»"} />
            <button type="button" title="Выбрать каталог" disabled={locked} onClick={() => void chooseRecordingDirectory().then((path) => path && patch({ directory: path }))}><FolderOpen /></button>
          </div>
        </label>
        <label className="field">
          <span>Режим записи</span>
          <select value={recording.layout} disabled={locked} onChange={(event) => patch({ layout: event.target.value as RecordingConfig["layout"] })}>
            <option value="separate">Раздельно · MP4 на камеру</option>
            <option value="split">Сплит · обе камеры в одном файле</option>
            <option value="both">Раздельно + сплит</option>
          </select>
        </label>
        <NumberField label="Сегмент, мин" integer value={recording.segmentMinutes} min={1} max={240} onChange={(segmentMinutes) => patch({ segmentMinutes })} />
        <NumberField label="Стоп через, мин" integer value={recording.stopAfterMinutes} min={0} max={1440} onChange={(stopAfterMinutes) => patch({ stopAfterMinutes })} />
      </div>
      <div className="record-meta">
        <div className="setting-line" title="Пароли в запись и метаданные не попадают; зашифрованный manifest паролей не реализован"><span>Метаданные (JSON рядом с файлом): камера, адрес потока, кодек, время</span><Toggle value={recording.includeMetadata} disabled={locked} onChange={(includeMetadata) => patch({ includeMetadata })} /></div>
        {separate && <p className="hint">{moduleName(config, "camera1")}: {recordingLine(control, "camera1", recording.camera1)}</p>}
        {separate && <p className="hint">{moduleName(config, "camera2")}: {recordingLine(control, "camera2", recording.camera2)}</p>}
        {splitWanted && <p className="hint">Сплит: {splitLine(control, bothPlaying)}</p>}
        <p className="hint">Таймер: {control.active && control.endsAt !== null ? <>остановится в {new Date(control.endsAt).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })} · осталось <Countdown endsAt={control.endsAt} /></> : recording.stopAfterMinutes > 0 ? `запись остановится через ${recording.stopAfterMinutes} мин` : "выключен (0) · остановка вручную"}</p>
        {splitWanted && <div className="setting-line"><span>Прицелы в сплит-записи</span><Toggle value={recording.splitReticles} onChange={(splitReticles) => patch({ splitReticles })} /></div>}
        {splitWanted && <div className="setting-line"><span>Точки и температуры тепловизора в сплит-записи</span><Toggle value={recording.splitThermal} onChange={(splitThermal) => patch({ splitThermal })} /></div>}
      </div>
      <button
        className={`record-start ${control.active ? "active" : ""}`}
        type="button"
        disabled={!control.active && !ready}
        onClick={control.active ? control.stop : control.start}
        title={ready ? (separate ? "Раздельно: MP4 пишется прямо из потока камеры, без перекодирования" : "Сплит: обе камеры рядом в одном файле") : splitWanted && !bothPlaying ? "Для сплита нужны оба видеопотока" : "Выберите хотя бы одну камеру"}
      >
        {control.active ? <Square /> : <CircleDot />} {control.active ? "Остановить" : "Начать запись"}
        <small>{control.active ? "идёт запись" : !ready ? (splitWanted && !bothPlaying ? "нужны обе камеры" : "выберите камеру") : recording.layout === "split" ? "сплит · один файл" : recording.layout === "both" ? "MP4 + сплит" : "MP4 · без перекодирования"}</small>
      </button>
    </div>
  );
}

export function SystemDrawer({ tab, setTab, config, setConfig, modules, probes, probing, onProbe, onProbeResults, testLog, onTestRecords, onReport, jog, rocking, recording, rangefinder, onRange, onRangeContinuous, notify, onClose }: {
  tab: SystemTab;
  setTab: (tab: SystemTab) => void;
  config: AppConfig;
  setConfig: SetConfig;
  modules: ModuleView[];
  probes: Record<string, ProbeResult>;
  probing: boolean;
  onProbe: () => void;
  onProbeResults: (results: ProbeResult[]) => void;
  testLog: Record<string, TestRecord>;
  onTestRecords: (records: TestRecord[]) => void;
  onReport: () => void;
  jog: JogControl;
  rocking: RockingEvent | null;
  recording: RecordingControl;
  rangefinder: RangefinderStatus;
  onRange: () => void;
  onRangeContinuous: (on: boolean) => void;
  notify: Notify;
  onClose: () => void;
}) {
  return (
    <section className="system-drawer" aria-label="Система">
      <nav className="system-tabs">
        {TABS.map((item) => (
          <button key={item.id} className={tab === item.id ? "active" : ""} onClick={() => setTab(item.id)} type="button">
            {item.icon}
            {item.label}
          </button>
        ))}
        <button className="close-system" onClick={onClose} type="button" title="Свернуть">
          <ChevronUp />
        </button>
      </nav>
      <div className="system-body">
        {tab === "summary" && <ModulesPanel modules={modules} probes={probes} probing={probing} onProbe={onProbe} setConfig={setConfig} notify={notify} />}
        {tab === "platform" && <PlatformPanel config={config} setConfig={setConfig} jog={jog} rocking={rocking} notify={notify} />}
        {tab === "rangefinder" && (
          <RangefinderPanel config={config} setConfig={setConfig} status={rangefinder} onRange={onRange} onContinuous={onRangeContinuous} onRecords={onTestRecords} notify={notify} />
        )}
        {tab === "tests" && (
          <TestsPanel config={config} setConfig={setConfig} modules={modules} testLog={testLog} onRecords={onTestRecords} onProbeResults={onProbeResults} onReport={onReport} notify={notify} />
        )}
        {tab === "record" && <RecordPanel config={config} setConfig={setConfig} control={recording} />}
      </div>
    </section>
  );
}
