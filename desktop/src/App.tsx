import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";
import type { CSSProperties, PointerEvent as ReactPointerEvent } from "react";
import { AlignCenter, ArrowLeftRight, CircleDot, Crosshair, GripVertical, PanelTopOpen, Pencil, Radio, Save, SlidersHorizontal, Square } from "lucide-react";
import { version } from "../package.json";
import { inTauri, loadConfig, onRecordingState, onRockingState, persistConfig, printPage, probeModules, startRecording, stopRecording } from "./api";
import { lensStep } from "./lens";
import { CameraDrawer } from "./CameraDrawer";
import { MAX_TITLE_LENGTH, OFF_STATS, createDefaultConfig, listModules, moduleName } from "./config";
import { PrintReport } from "./PrintReport";
import { ReticleLayer } from "./Reticle";
import { buildReport, reportFileStamp, testKey } from "./report";
import { SystemDrawer, type SystemTab } from "./SystemDrawer";
import { useJog, type JogControl } from "./useJog";
import type { AppConfig, CameraConfig, ModuleView, Notify, ProbeResult, RecordingEvent, ReticleConfig, RockingEvent, TestRecord, VideoStats } from "./types";
import { VideoSurface } from "./VideoSurface";
import { Countdown } from "./ui";
import { SplitRecorder, type SplitSource, type SplitStatus } from "./splitRecorder";
import { axisError, signed, within, type AxisError, type TargetFix } from "./alignment";

type Drawer = "camera1" | "camera2" | null;
type Notice = { text: string; tone: "info" | "error" };

const PROBE_INTERVAL_MS = 5000;
const NOTICE_MS = 5000;
/** A wheel event this large is one notch (Chromium on Windows reports 100 px per notch). */
const NOTCH_DELTA = 30;
/** Small deltas (touchpad) that add up to one step. */
const NOTCH_PIXELS = 100;

const VideoPane = memo(function VideoPane({ camera, label, variant, jog, streaming, restartKey, video, onVideoStats, measure, onTarget }: {
  camera: CameraConfig;
  label: string;
  variant: "optical" | "thermal";
  jog: JogControl;
  streaming: boolean;
  restartKey: number;
  video: VideoStats;
  onVideoStats: (id: CameraConfig["id"], stats: VideoStats) => void;
  measure: boolean;
  onTarget: (id: CameraConfig["id"], fix: TargetFix | null) => void;
}) {
  const paneRef = useRef<HTMLDivElement>(null);
  const cameraRef = useRef(camera);
  cameraRef.current = camera;
  const rightMouseDown = useRef(false);
  const indicatorTimer = useRef<number | null>(null);
  const [lensIndicator, setLensIndicator] = useState("");

  // Native listener: React registers wheel as passive, so preventDefault (no page zoom) needs this.
  useEffect(() => {
    const pane = paneRef.current;
    if (!pane) return;
    // Touchpads and smooth-scrolling wheels send small deltas: they add up to one step per notch.
    let smallDeltas = 0;
    const show = (message: string) => {
      setLensIndicator(message);
      if (indicatorTimer.current !== null) window.clearTimeout(indicatorTimer.current);
      indicatorTimer.current = window.setTimeout(() => setLensIndicator(""), 700);
    };
    const onWheel = (event: WheelEvent) => {
      if ((event.target as HTMLElement).closest(".video-dpad")) return;
      event.preventDefault();
      if (event.deltaY === 0) return;
      // A notch is one event of ≥ NOTCH_DELTA px (or in lines/pages): exactly one step.
      if (event.deltaMode !== WheelEvent.DOM_DELTA_PIXEL || Math.abs(event.deltaY) >= NOTCH_DELTA) {
        smallDeltas = 0;
      } else {
        smallDeltas += event.deltaY;
        if (Math.abs(smallDeltas) < NOTCH_PIXELS) return;
        smallDeltas = 0;
      }
      const direction = event.deltaY < 0 ? 1 : -1;
      const mode = rightMouseDown.current ? "focus" : "zoom";
      show(mode === "zoom" ? `ZOOM ${direction > 0 ? "+" : "−"}` : `FOCUS ${direction > 0 ? "FAR" : "NEAR"}`);
      lensStep(cameraRef.current, mode, direction, (error) => show(`ONVIF · ${String(error)}`));
    };
    pane.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      pane.removeEventListener("wheel", onWheel);
      if (indicatorTimer.current !== null) window.clearTimeout(indicatorTimer.current);
    };
  }, []);

  return (
    <div
      ref={paneRef}
      className={`video-pane ${variant}`}
      onContextMenu={(event) => event.preventDefault()}
      onPointerDown={(event) => { if (event.button === 2) rightMouseDown.current = true; }}
      onPointerUp={(event) => { if (event.button === 2) rightMouseDown.current = false; }}
      onPointerCancel={() => { rightMouseDown.current = false; }}
      onPointerLeave={() => { rightMouseDown.current = false; }}
    >
      {(video.state === "off" || video.state === "error") && <div className="video-placeholder" />}
      <VideoSurface camera={camera} active={streaming} restartKey={restartKey} onStats={onVideoStats} measure={measure} onTarget={onTarget} />
      <ReticleLayer reticles={camera.reticles} />
      {camera.osd && (
        <div className="camera-osd"><strong>{label}</strong><span className="fps">{video.fps !== null ? Math.round(video.fps) : "—"} FPS</span><span>ONVIF —</span></div>
      )}
      <div className="video-dpad" aria-label="Поворотка: удерживайте кнопку">
        <i /><button type="button" {...jog.bind("up")} aria-label="Поворотка вверх">▲</button><i />
        <button type="button" {...jog.bind("left")} aria-label="Поворотка влево">◀</button>
        <button type="button" className="stop" onClick={jog.stopNow} aria-label="Поворотка стоп">■</button>
        <button type="button" {...jog.bind("right")} aria-label="Поворотка вправо">▶</button>
        <i /><button type="button" {...jog.bind("down")} aria-label="Поворотка вниз">▼</button><i />
      </div>
      {lensIndicator && <div className="lens-indicator">{lensIndicator}</div>}
      {video.state !== "playing" && (
        <div className={`stream-state ${video.state}`} title={video.message}>
          <Radio />
          <span>{video.state === "connecting" ? "Подключение…" : video.state === "error" ? video.message || "Ошибка потока" : "Нет потока"}</span>
          <code>RTSP {camera.ip}:{camera.rtspPort}{camera.streamPath}</code>
        </div>
      )}
    </div>
  );
});

/** Full installation name next to the app name; click to edit in place. */
function ProductTitle({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const commit = () => {
    onChange(draft.trim().slice(0, MAX_TITLE_LENGTH));
    setEditing(false);
  };
  if (editing) {
    return (
      <input
        className="product-title-input"
        value={draft}
        maxLength={MAX_TITLE_LENGTH}
        autoFocus
        spellCheck={false}
        placeholder="Полное наименование изделия"
        aria-label="Полное наименование изделия"
        onChange={(event) => setDraft(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === "Enter") commit();
          if (event.key === "Escape") setEditing(false);
        }}
      />
    );
  }
  return (
    <button
      className={`product-title ${value ? "" : "empty"}`}
      onClick={() => {
        setDraft(value);
        setEditing(true);
      }}
      type="button"
      title={value ? `${value} · нажмите, чтобы изменить` : "Задать полное наименование изделия"}
    >
      <span>{value || "Полное наименование изделия"}</span>
      <Pencil />
    </button>
  );
}

interface AlignmentView {
  state: "off" | "noTarget" | "reference" | "measuring" | "aligned";
  optical: AxisError | null;
  reference: AxisError | null;
}

function alignmentLabel(config: AppConfig, view: AlignmentView): string {
  const reference = moduleName(config, "camera2");
  switch (view.state) {
    case "off":
      return "СВЕДЕНИЕ ВЫКЛ";
    case "noTarget":
      return view.reference ? `МИШЕНЬ НЕ НАЙДЕНА В ${moduleName(config, "camera1")}` : `МИШЕНЬ НЕ НАЙДЕНА В ${reference}`;
    case "reference":
      return `НАВЕДИТЕ ${reference}: ${signed(view.reference!.dx)} / ${signed(view.reference!.dy)}`;
    case "measuring":
      return "СВЕДЕНИЕ · ИЗМЕРЕНИЕ";
    case "aligned":
      return "СВЕДЕНО";
  }
}

function StatusBar({ config, modules, probes, video, alignment, rocking, notice }: {
  config: AppConfig;
  modules: ModuleView[];
  probes: Record<string, ProbeResult>;
  video: Record<CameraConfig["id"], VideoStats>;
  alignment: AlignmentView;
  rocking: RockingEvent | null;
  notice: Notice | null;
}) {
  const chips = modules.filter((module) => !module.hidden && module.id !== "camera1" && module.id !== "camera2");
  const camera = (id: "camera1" | "camera2", label: string, tone: string) => {
    const stats = video[id];
    const playing = stats.state === "playing";
    const title = playing ? "Видеопоток идёт" : stats.message || probes[id]?.error || (stats.state === "connecting" ? "Подключение к потоку" : "Видеопоток не подключён");
    return (
      <div className={`cam-status ${tone}`} title={title}>
        <i className={playing || probes[id]?.connected ? "on" : ""} />
        <b>{label}</b>
        <span className="fps">{playing && stats.fps !== null ? Math.round(stats.fps) : "—"} FPS</span>
        <span className="resolution">{playing && stats.width ? `${stats.width}×${stats.height}` : "—"}</span>
      </div>
    );
  };
  return (
    <footer className="status-bar">
      {camera("camera1", moduleName(config, "camera1"), "blue")}
      {camera("camera2", moduleName(config, "camera2"), "amber")}
      <div className="metrics">
        {["PAN", "TILT", "RANGE"].map((label) => (
          <div className="metric" key={label} title="Живая телеметрия ещё не подключена"><span>{label}</span><strong>—</strong></div>
        ))}
        <div className="metric delta" title={`Ошибка ${moduleName(config, "camera1")} относительно прицела, px видео`}>
          <span>ΔX/ΔY</span>
          <strong>{alignment.optical ? `${signed(alignment.optical.dx)} / ${signed(alignment.optical.dy)}` : "—"}</strong>
        </div>
      </div>
      <div className="module-chips">
        {chips.map((module) => {
          const probe = probes[module.id];
          return (
            <span key={module.id} className={`chip-status ${probe?.connected ? "on" : probe ? "off" : ""}`} title={`${module.ip}:${module.port}${probe?.error ? ` — ${probe.error}` : ""}`}>
              <i />{module.name}
            </span>
          );
        })}
        {rocking?.state === "running" && <span className="chip-status rocking"><i />КАЧКА {rocking.cycle}/{rocking.cycles}</span>}
      </div>
      <div className={`notice ${notice?.tone ?? ""}`} title={notice?.text}>{notice?.text}</div>
      <div
        className={`align-state ${config.alignment.enabled ? "on" : ""} ${alignment.state === "aligned" ? "aligned" : ""}`}
        title={`Мишень ищется как самое горячее пятно. ${moduleName(config, "camera2")} — эталон: сначала наведите мишень в его прицел. Допуск ±${config.alignment.tolerancePx} px в течение ${config.alignment.stableMs} мс.`}
      >
        <Crosshair />
        {alignmentLabel(config, alignment)}
      </div>
    </footer>
  );
}

export default function App() {
  const [config, setConfig] = useState<AppConfig>(createDefaultConfig);
  const [savedSnapshot, setSavedSnapshot] = useState<string | null>(null);
  const [drawer, setDrawer] = useState<Drawer>(null);
  const [systemOpen, setSystemOpen] = useState(false);
  const [systemTab, setSystemTab] = useState<SystemTab>("summary");
  const [probes, setProbes] = useState<Record<string, ProbeResult>>({});
  const [probing, setProbing] = useState(false);
  const [split, setSplit] = useState(50);
  const [swapped, setSwapped] = useState(false);
  const [rocking, setRocking] = useState<RockingEvent | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [testLog, setTestLog] = useState<Record<string, TestRecord>>({});
  const [reportAt, setReportAt] = useState(() => new Date());
  const [video, setVideo] = useState<Record<CameraConfig["id"], VideoStats>>({ camera1: OFF_STATS, camera2: OFF_STATS });
  // Operator override of «Автоподключение» for this session; unset follows the config.
  const [streamOverride, setStreamOverride] = useState<Partial<Record<CameraConfig["id"], boolean>>>({});
  const [restartKeys, setRestartKeys] = useState<Record<CameraConfig["id"], number>>({ camera1: 0, camera2: 0 });
  const [recordingActive, setRecordingActive] = useState(false);
  /** When the auto-stop timer ends the recording (epoch ms), or null for a manual stop. */
  const [recordingEndsAt, setRecordingEndsAt] = useState<number | null>(null);
  const [recordingFiles, setRecordingFiles] = useState<Partial<Record<CameraConfig["id"], RecordingEvent>>>({});
  const stageRef = useRef<HTMLDivElement>(null);
  const noticeTimer = useRef<number | null>(null);
  const probeInFlight = useRef(false);
  const configRef = useRef(config);
  configRef.current = config;

  const notify = useCallback<Notify>((text, tone = "info") => {
    setNotice({ text, tone });
    if (noticeTimer.current !== null) window.clearTimeout(noticeTimer.current);
    noticeTimer.current = window.setTimeout(() => setNotice(null), NOTICE_MS);
  }, []);

  useEffect(() => {
    let alive = true;
    loadConfig()
      .then(({ config: loaded, recoveredFrom }) => {
        if (!alive) return;
        setConfig(loaded);
        setSavedSnapshot(JSON.stringify(loaded));
        if (recoveredFrom) notify(`Конфигурация была повреждена — копия: ${recoveredFrom}; загружены значения по умолчанию`, "error");
      })
      .catch((error) => notify(`Конфигурация не загружена: ${String(error)}`, "error"));
    return () => {
      alive = false;
    };
  }, [notify]);

  const modules = useMemo(() => listModules(config), [config]);
  const targetsKey = JSON.stringify(modules.filter((module) => !module.hidden).map(({ id, ip, port }) => [id, ip, port]));

  const mergeProbes = useCallback((results: ProbeResult[]) => {
    setProbes((current) => ({ ...current, ...Object.fromEntries(results.map((result) => [result.id, result])) }));
  }, []);

  const runProbe = useCallback(async (manual: boolean) => {
    if (probeInFlight.current) return;
    probeInFlight.current = true;
    if (manual) setProbing(true);
    try {
      const targets = (JSON.parse(targetsKey) as [string, string, number][]).map(([id, ip, port]) => ({ id, ip, port }));
      const results = await probeModules(targets);
      setProbes(Object.fromEntries(results.map((result) => [result.id, result])));
      if (manual) notify(`Опрос: на связи ${results.filter((result) => result.connected).length} из ${results.length}`);
    } catch (error) {
      if (manual) notify(`Опрос не выполнен: ${String(error)}`, "error");
    } finally {
      probeInFlight.current = false;
      if (manual) setProbing(false);
    }
  }, [targetsKey, notify]);

  // Live link status; the first probe after an address edit waits for typing to settle.
  useEffect(() => {
    const first = window.setTimeout(() => void runProbe(false), 600);
    const timer = window.setInterval(() => {
      if (!document.hidden) void runProbe(false);
    }, PROBE_INTERVAL_MS);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(timer);
    };
  }, [runProbe]);

  useEffect(() => {
    let disposed = false;
    let unlisten: (() => void) | undefined;
    onRockingState((event) => {
      setRocking(event);
      if (event.state === "failed") notify(`Качка прервана: ${event.message ?? "ошибка связи"}`, "error");
      if (event.state === "completed") notify(event.message ? `Качка завершена, стоп не доставлен: ${event.message}` : "Качка завершена", event.message ? "error" : "info");
    })
      .then((stop) => {
        if (disposed) stop();
        else unlisten = stop;
      })
      .catch(() => undefined);
    return () => {
      disposed = true;
      unlisten?.();
    };
  }, [notify]);

  useEffect(() => {
    let disposed = false;
    let unlisten: (() => void) | undefined;
    onRecordingState((event) => {
      setRecordingFiles((current) => ({ ...current, [event.cameraId]: event }));
      if (event.state === "error") notify(`Запись ${moduleName(configRef.current, event.cameraId)}: ${event.message ?? "ошибка"}`, "error");
    })
      .then((stop) => {
        if (disposed) stop();
        else unlisten = stop;
      })
      .catch(() => undefined);
    return () => {
      disposed = true;
      unlisten?.();
    };
  }, [notify]);

  const splitRecorder = useRef<SplitRecorder | null>(null);
  const [splitStatus, setSplitStatus] = useState<SplitStatus | null>(null);
  const swappedRef = useRef(false);

  const recordingControl = useMemo(() => {
    const stopAll = async () => {
      await Promise.allSettled([stopRecording(), splitRecorder.current?.stop()]);
      splitRecorder.current = null;
      setRecordingActive(false);
      setRecordingEndsAt(null);
    };
    return {
      active: recordingActive,
      files: recordingFiles,
      split: splitStatus,
      video,
      start: () => {
        const current = configRef.current;
        const { layout } = current.recording;
        const run = async () => {
          let directory = current.recording.directory;
          if (layout !== "split") directory = await startRecording(current);
          if (layout !== "separate") {
            // Reticles are read live, so an adjustment during recording shows up in the file too.
            const source = (id: CameraConfig["id"]): SplitSource | null => {
              const canvas = document.querySelector<HTMLCanvasElement>(`canvas.video-canvas[data-camera="${id}"]`);
              const latest = configRef.current;
              const camera = latest.cameras.find((item) => item.id === id);
              return canvas ? { canvas, reticles: latest.recording.splitReticles && camera ? camera.reticles : null } : null;
            };
            // Same order as on screen: after a swap CAM 02 is on the left.
            const recorder = new SplitRecorder(
              () => (swappedRef.current ? [source("camera2"), source("camera1")] : [source("camera1"), source("camera2")]),
              {
                directory,
                title: current.productTitle,
                camera1Name: moduleName(current, swappedRef.current ? "camera2" : "camera1"),
                camera2Name: moduleName(current, swappedRef.current ? "camera1" : "camera2"),
                utcOffsetMinutes: -new Date().getTimezoneOffset(),
              },
              current.recording.segmentMinutes,
              (status) => {
                setSplitStatus(status);
                if (status.state === "error") notify(`Сплит-запись: ${status.message ?? "ошибка"}`, "error");
              },
            );
            splitRecorder.current = recorder;
            directory = await recorder.start();
          }
          return directory;
        };
        setRecordingFiles({});
        setSplitStatus(null);
        run()
          .then((directory) => {
            // Without a chosen directory the native side picked «Videos/MKIS100TEST»: remember it.
            setConfig((latest) => (latest.recording.directory === directory ? latest : { ...latest, recording: { ...latest.recording, directory } }));
            setRecordingActive(true);
            const minutes = current.recording.stopAfterMinutes;
            setRecordingEndsAt(minutes > 0 ? Date.now() + minutes * 60_000 : null);
            notify(`Запись начата в ${directory}`);
          })
          .catch(async (error) => {
            await stopAll();
            notify(`Запись не начата: ${String(error)}`, "error");
          });
      },
      stop: () => {
        stopAll()
          .then(() => notify("Запись остановлена"))
          .catch((error) => notify(`Запись не остановлена: ${String(error)}`, "error"));
      },
      endsAt: recordingEndsAt,
    };
  }, [recordingActive, recordingFiles, splitStatus, video, notify, recordingEndsAt]);

  // Auto-stop timer: ends the recording at the time chosen when it started.
  const stopRecordingRef = useRef(recordingControl.stop);
  stopRecordingRef.current = recordingControl.stop;
  useEffect(() => {
    if (!recordingActive || recordingEndsAt === null) return;
    const timer = window.setTimeout(() => {
      notify("Таймер записи истёк");
      stopRecordingRef.current();
    }, Math.max(0, recordingEndsAt - Date.now()));
    return () => window.clearTimeout(timer);
  }, [recordingActive, recordingEndsAt, notify]);

  const platformLabel = moduleName(config, "platform");
  const platformTarget = useMemo(
    () => ({ ip: config.platformIp, port: config.platformPort, label: platformLabel }),
    [config.platformIp, config.platformPort, platformLabel],
  );
  const jog = useJog(platformTarget, config.jog, notify);

  const saveAll = useCallback(async () => {
    const current = configRef.current;
    try {
      await persistConfig(current);
      setSavedSnapshot(JSON.stringify(current));
      notify("Конфигурация сохранена");
    } catch (error) {
      notify(`Конфигурация не сохранена: ${String(error)}`, "error");
    }
  }, [notify]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !event.repeat) jog.stopNow();
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        void saveAll();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [jog, saveAll]);

  const patchCamera = useCallback((id: CameraConfig["id"], patch: Partial<CameraConfig>) => {
    setConfig((current) => ({ ...current, cameras: current.cameras.map((camera) => (camera.id === id ? { ...camera, ...patch } : camera)) as [CameraConfig, CameraConfig] }));
  }, []);

  const onVideoStats = useCallback((id: CameraConfig["id"], stats: VideoStats) => {
    setVideo((current) => ({ ...current, [id]: stats }));
  }, []);

  const [targets, setTargets] = useState<Record<CameraConfig["id"], TargetFix | null>>({ camera1: null, camera2: null });
  const onTarget = useCallback((id: CameraConfig["id"], fix: TargetFix | null) => {
    setTargets((current) => (current[id] === fix ? current : { ...current, [id]: fix }));
  }, []);
  // Since when both errors have been within tolerance; «СВЕДЕНО» needs it to last `stableMs`.
  const withinSince = useRef<number | null>(null);
  const alignment = useMemo<AlignmentView>(() => {
    const { enabled, tolerancePx, stableMs } = config.alignment;
    const optical = axisError(targets.camera1, config.cameras[0].reticles);
    const reference = axisError(targets.camera2, config.cameras[1].reticles);
    const inside = enabled && within(reference, tolerancePx) && within(optical, tolerancePx);
    if (!inside) withinSince.current = null;
    else withinSince.current ??= performance.now();
    if (!enabled) return { state: "off", optical: null, reference: null };
    if (!optical || !reference) return { state: "noTarget", optical, reference };
    if (!within(reference, tolerancePx)) return { state: "reference", optical, reference };
    const held = withinSince.current !== null && performance.now() - withinSince.current >= stableMs;
    return { state: held ? "aligned" : "measuring", optical, reference };
  }, [config.alignment, config.cameras, targets]);
  const restartStream = useCallback((id: CameraConfig["id"]) => {
    setRestartKeys((current) => ({ ...current, [id]: current[id] + 1 }));
  }, []);

  const recordTests = useCallback((records: TestRecord[]) => {
    setTestLog((current) => ({ ...current, ...Object.fromEntries(records.map((record) => [testKey(record.moduleId, record.kind), record])) }));
  }, []);

  const reportModel = useMemo(() => buildReport(config, modules, testLog, reportAt, version, !inTauri()), [config, modules, testLog, reportAt]);

  // The protocol page is always rendered for print media; stamp it, name the file, open the print dialog.
  const printReport = useCallback(async () => {
    const now = new Date();
    flushSync(() => setReportAt(now));
    const previousTitle = document.title;
    const restoreTitle = () => { document.title = previousTitle; };
    document.title = `Протокол проверки MKIS100TEST ${reportFileStamp(now)}`;
    window.addEventListener("afterprint", restoreTitle, { once: true });
    window.setTimeout(restoreTitle, 60_000);
    try {
      await printPage();
      notify("Протокол открыт в диалоге печати — выберите «Сохранить как PDF»");
    } catch (error) {
      restoreTitle();
      notify(`Печать недоступна: ${String(error)}`, "error");
    }
  }, [notify]);

  // Linked reticles: an edit in either drawer lands in both panes.
  const setReticles = useCallback((id: CameraConfig["id"], reticles: ReticleConfig[]) => {
    setConfig((current) => ({
      ...current,
      cameras: current.cameras.map((camera) => (current.reticlesLinked || camera.id === id ? { ...camera, reticles } : camera)) as [CameraConfig, CameraConfig],
    }));
  }, []);

  const linkReticles = useCallback((id: CameraConfig["id"], linked: boolean) => {
    const current = configRef.current;
    const source = current.cameras.find((camera) => camera.id === id)?.reticles ?? [];
    setConfig((latest) => ({
      ...latest,
      reticlesLinked: linked,
      cameras: linked ? (latest.cameras.map((camera) => ({ ...camera, reticles: source })) as [CameraConfig, CameraConfig]) : latest.cameras,
    }));
    notify(linked ? `Прицелы ${moduleName(current, id)} применены к обоим окнам` : "Прицелы снова настраиваются для каждого окна отдельно");
  }, [notify]);

  const probeOne = (id: string) => {
    const module = modules.find((item) => item.id === id);
    if (!module) return;
    probeModules([{ id, ip: module.ip, port: module.port }])
      .then((results) => {
        mergeProbes(results);
        const result = results[0];
        if (result?.connected) notify(`${module.name} · связь${result.latencyMs !== null ? ` ${result.latencyMs} мс` : ""}`);
        else notify(`${module.name} · нет связи: ${result?.error ?? "—"}`, "error");
      })
      .catch((error) => notify(`${module.name} · ${String(error)}`, "error"));
  };

  // During a drag only a CSS variable changes; React re-renders once, on release.
  const beginSplitDrag = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const stage = stageRef.current;
    if (event.button !== 0 || !stage) return;
    const handle = event.currentTarget;
    handle.setPointerCapture(event.pointerId);
    const bounds = stage.getBoundingClientRect();
    let latest = split;
    const move = (moveEvent: PointerEvent) => {
      latest = Math.max(24, Math.min(76, ((moveEvent.clientX - bounds.left) / bounds.width) * 100));
      stage.style.setProperty("--split", `${latest}%`);
    };
    const end = () => {
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", end);
      handle.removeEventListener("pointercancel", end);
      setSplit(latest);
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", end);
    handle.addEventListener("pointercancel", end);
  };

  const [camera1, camera2] = config.cameras;
  const label1 = moduleName(config, "camera1");
  const label2 = moduleName(config, "camera2");
  swappedRef.current = swapped;
  const left = swapped ? camera2 : camera1;
  const right = swapped ? camera1 : camera2;
  const dirty = savedSnapshot !== null && JSON.stringify(config) !== savedSnapshot;
  // Streams open only once the stored config is loaded, so defaults never hit a camera first.
  const streaming = (camera: CameraConfig) => savedSnapshot !== null && (streamOverride[camera.id] ?? camera.autoConnect);
  const pane = (camera: CameraConfig) => (
    // Keyed, so swapping the panes moves them instead of reopening both streams.
    <VideoPane
      key={camera.id}
      camera={camera}
      label={camera.id === "camera1" ? label1 : label2}
      variant={camera.id === "camera1" ? "optical" : "thermal"}
      jog={jog}
      streaming={streaming(camera)}
      restartKey={restartKeys[camera.id]}
      video={video[camera.id]}
      onVideoStats={onVideoStats}
      measure={config.alignment.enabled}
      onTarget={onTarget}
    />
  );
  const drawerStream = (camera: CameraConfig) => ({
    video: video[camera.id],
    streaming: streaming(camera),
    onStreamingChange: (on: boolean) => setStreamOverride((current) => ({ ...current, [camera.id]: on })),
    onRestartStream: () => restartStream(camera.id),
  });
  const toggleDrawer = (id: Exclude<Drawer, null>) => setDrawer((current) => (current === id ? null : id));
  const openSystem = (tab: SystemTab) => {
    setSystemTab(tab);
    setSystemOpen(true);
  };

  return (
    <>
    <main className="app-shell">
      <header className="top-bar">
        <button className={`cam-toggle blue ${drawer === "camera1" ? "active" : ""}`} onClick={() => toggleDrawer("camera1")} type="button" title={`Настройки ${label1}`}>
          <SlidersHorizontal /> {label1}
        </button>
        <div className="brand"><Crosshair /><strong>MKIS100TEST</strong></div>
        <ProductTitle value={config.productTitle} onChange={(productTitle) => setConfig((current) => ({ ...current, productTitle }))} />
        {!inTauri() && <span className="mode-badge" title="Команды оборудованию не отправляются">БРАУЗЕРНЫЙ РЕЖИМ</span>}
        <div className="top-spacer" />
        <nav className="top-actions">
          <button className={config.alignment.enabled ? "active" : ""} onClick={() => setConfig((current) => ({ ...current, alignment: { ...current.alignment, enabled: !current.alignment.enabled } }))} type="button" title="Режим сведения осей">
            <AlignCenter /> Сведение
          </button>
          <button className={`${systemOpen && systemTab === "record" ? "active" : ""} ${recordingActive ? "recording" : ""}`} onClick={() => openSystem("record")} type="button" title={recordingActive ? "Идёт запись" : "Настройки записи"}>
            <CircleDot /> {recordingActive ? "REC" : "Запись"}{recordingActive && recordingEndsAt !== null && <Countdown endsAt={recordingEndsAt} />}
          </button>
          <button className={systemOpen ? "active" : ""} onClick={() => setSystemOpen((open) => !open)} type="button" title="Модули, поворотка, тесты, запись">
            <PanelTopOpen /> Система
          </button>
          <button className={`save ${dirty ? "dirty" : ""}`} onClick={() => void saveAll()} type="button" title={dirty ? "Есть несохранённые изменения · Ctrl+S" : "Сохранить конфигурацию · Ctrl+S"}>
            <Save />
            {dirty && <i />}
          </button>
          <button className="estop" onClick={jog.stopNow} type="button" title={`Остановить ${platformLabel} и качку · Esc`}>
            <Square /> СТОП
          </button>
        </nav>
        <button className={`cam-toggle amber ${drawer === "camera2" ? "active" : ""}`} onClick={() => toggleDrawer("camera2")} type="button" title={`Настройки ${label2}`}>
          {label2} <SlidersHorizontal />
        </button>
      </header>

      {systemOpen && (
        <SystemDrawer
          tab={systemTab}
          setTab={setSystemTab}
          config={config}
          setConfig={setConfig}
          modules={modules}
          probes={probes}
          probing={probing}
          onProbe={() => void runProbe(true)}
          onProbeResults={mergeProbes}
          testLog={testLog}
          onTestRecords={recordTests}
          onReport={() => void printReport()}
          jog={jog}
          rocking={rocking}
          recording={recordingControl}
          notify={notify}
          onClose={() => setSystemOpen(false)}
        />
      )}

      <div className="workbench">
        {drawer === "camera1" && (
          <CameraDrawer
            camera={camera1}
            side="left"
            label={label1}
            otherLabel={label2}
            probe={probes.camera1}
            {...drawerStream(camera1)}
            reticlesLinked={config.reticlesLinked}
            onClose={() => setDrawer(null)}
            onChange={(patch) => patchCamera("camera1", patch)}
            onReticlesChange={(reticles) => setReticles("camera1", reticles)}
            onReticlesLinkedChange={(linked) => linkReticles("camera1", linked)}
            onProbe={() => probeOne("camera1")}
            notify={notify}
          />
        )}
        <div className="video-stage" ref={stageRef} style={{ "--split": `${split}%` } as CSSProperties}>
          {pane(left)}
          <div className="split">
            <button className="split-grip" onPointerDown={beginSplitDrag} onDoubleClick={() => setSplit(50)} type="button" title="Перетащите · двойной клик — поровну">
              <GripVertical />
            </button>
            <button className="split-swap" onClick={() => setSwapped((value) => !value)} type="button" title="Поменять камеры местами">
              <ArrowLeftRight />
            </button>
          </div>
          {pane(right)}
        </div>
        {drawer === "camera2" && (
          <CameraDrawer
            camera={camera2}
            side="right"
            label={label2}
            otherLabel={label1}
            probe={probes.camera2}
            {...drawerStream(camera2)}
            reticlesLinked={config.reticlesLinked}
            onClose={() => setDrawer(null)}
            onChange={(patch) => patchCamera("camera2", patch)}
            onReticlesChange={(reticles) => setReticles("camera2", reticles)}
            onReticlesLinkedChange={(linked) => linkReticles("camera2", linked)}
            onProbe={() => probeOne("camera2")}
            notify={notify}
          />
        )}
      </div>

      <StatusBar config={config} modules={modules} probes={probes} video={video} alignment={alignment} rocking={rocking} notice={notice} />
    </main>
    <PrintReport model={reportModel} />
    </>
  );
}
