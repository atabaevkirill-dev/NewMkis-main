import { useState } from "react";
import type { Dispatch, ReactNode, SetStateAction } from "react";
import { Activity, Camera, Check, ChevronUp, CircleDot, Eye, EyeOff, FileText, FolderOpen, LocateFixed, Pencil, Play, Plus, Radio, RefreshCw, Square, Trash2, Video, X } from "lucide-react";
import { chooseRecordingDirectory, probeModules, runPlatformSelfTest, startRockingProfile, stopRockingProfile } from "./api";
import {
  DEFAULT_MODULE_NAMES,
  KIND_LABELS,
  MAX_CUSTOM_MODULES,
  MAX_NAME_LENGTH,
  MODULE_PRESETS,
  PLATFORM_LIMITS,
  isIPv4,
  moduleName,
  profileError,
  removeModule,
  saveModule,
  setModuleHidden,
  validateModuleDraft,
  type ModuleDraft,
} from "./config";
import { selfTestRecord, tcpRecord, testKey } from "./report";
import { NumberField, Toggle, useConfirm } from "./ui";
import type { JogControl } from "./useJog";
import type { AppConfig, DeviceKind, ModuleView, Notify, ProbeResult, RecordingConfig, RockingEvent, RockingProfile, TestRecord } from "./types";

export type SystemTab = "summary" | "platform" | "tests" | "record";
type SetConfig = Dispatch<SetStateAction<AppConfig>>;

const TABS: { id: SystemTab; label: string; icon: ReactNode }[] = [
  { id: "summary", label: "Сводка", icon: <Activity /> },
  { id: "platform", label: "Поворотка", icon: <LocateFixed /> },
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
  const required = visible.flatMap((module) => (module.id === "platform" ? [testKey(module.id, "tcp"), testKey(module.id, "selftest")] : [testKey(module.id, "tcp")]));
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

  return (
    <div className="tests-panel">
      <div className="panel-head">
        <strong>Проверки</strong>
        <span className="test-counts" title="Для протокола нужны TCP-проверки всех показанных модулей и самодиагностика поворотки">
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
          const self = module.id === "platform" ? testLog[testKey(module.id, "selftest")] : undefined;
          const state = [tcp, ...(module.id === "platform" ? [self] : [])];
          const tone = state.some((record) => record && !record.ok) ? "fail" : state.every((record) => record?.ok) ? "pass" : "";
          const text = module.id === "platform" ? `TCP ${testSummary(tcp)} · самодиагностика ${testSummary(self)}` : testSummary(tcp);
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
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function RecordPanel({ config, setConfig }: { config: AppConfig; setConfig: SetConfig }) {
  const recording = config.recording;
  const patch = (update: Partial<RecordingConfig>) => setConfig((current) => ({ ...current, recording: { ...current.recording, ...update } }));
  return (
    <div className="record-panel">
      <div className="record-sources">
        <button className={recording.camera1 ? "selected blue" : ""} onClick={() => patch({ camera1: !recording.camera1 })} type="button" aria-pressed={recording.camera1}><Camera /> {moduleName(config, "camera1")}</button>
        <button className={recording.camera2 ? "selected amber" : ""} onClick={() => patch({ camera2: !recording.camera2 })} type="button" aria-pressed={recording.camera2}><Camera /> {moduleName(config, "camera2")}</button>
      </div>
      <div className="record-settings">
        <label className="field wide">
          <span>Каталог записи</span>
          <div className="input-action">
            <input value={recording.directory} placeholder="Выберите каталог" readOnly />
            <button type="button" title="Выбрать каталог" onClick={() => void chooseRecordingDirectory().then((path) => path && patch({ directory: path }))}><FolderOpen /></button>
          </div>
        </label>
        <label className="field">
          <span>Формат</span>
          <select value={recording.format} onChange={(event) => patch({ format: event.target.value as RecordingConfig["format"] })}>
            <option value="mkv">MKV</option>
            <option value="mp4">MP4</option>
          </select>
        </label>
        <NumberField label="Сегмент, мин" integer value={recording.segmentMinutes} min={1} max={240} onChange={(segmentMinutes) => patch({ segmentMinutes })} />
      </div>
      <div className="record-meta">
        <div className="setting-line"><span>Метаданные: IP, ONVIF, время, телеметрия поворотки</span><Toggle value={recording.includeMetadata} onChange={(includeMetadata) => patch({ includeMetadata })} /></div>
        <div className="setting-line warning"><span>Пароли в зашифрованном manifest</span><Toggle value={recording.includeEncryptedSecrets} onChange={(includeEncryptedSecrets) => patch({ includeEncryptedSecrets })} /></div>
        <p className="hint">Пароли никогда не записываются открытым текстом.</p>
      </div>
      <button className="record-start" type="button" disabled title="FFmpeg-запись ещё не подключена к новому клиенту">
        <CircleDot /> Начать запись
        <small>не подключено</small>
      </button>
    </div>
  );
}

export function SystemDrawer({ tab, setTab, config, setConfig, modules, probes, probing, onProbe, onProbeResults, testLog, onTestRecords, onReport, jog, rocking, notify, onClose }: {
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
        {tab === "tests" && (
          <TestsPanel config={config} setConfig={setConfig} modules={modules} testLog={testLog} onRecords={onTestRecords} onProbeResults={onProbeResults} onReport={onReport} notify={notify} />
        )}
        {tab === "record" && <RecordPanel config={config} setConfig={setConfig} />}
      </div>
    </section>
  );
}
