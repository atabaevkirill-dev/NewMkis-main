import { KIND_LABELS } from "./config";
import type { AppConfig, ModuleView, ProbeResult, TestKind, TestRecord } from "./types";

export const testKey = (moduleId: string, kind: TestKind) => `${moduleId}:${kind}`;

export function tcpRecord(result: ProbeResult, at = new Date()): TestRecord {
  return {
    moduleId: result.id,
    kind: "tcp",
    ok: result.connected,
    detail: result.connected
      ? `связь установлена${result.latencyMs !== null ? ` · ${result.latencyMs} мс` : ""}`
      : `нет связи · ${result.error ?? "причина не указана"}`,
    at: at.toISOString(),
  };
}

/** Self-test passes only when both fault registers ($n / $N) are read back as zero. */
export function selfTestRecord(replies: string[], at = new Date()): TestRecord {
  const flags = (axis: "n" | "N") =>
    replies.map((reply) => new RegExp(`^\\$${axis},([0-9a-fA-F]{1,8})#$`).exec(reply.trim())?.[1]).find(Boolean);
  const pan = flags("n");
  const tilt = flags("N");
  if (!pan || !tilt) {
    return { moduleId: "platform", kind: "selftest", ok: false, detail: `флаги ошибок не получены · ${replies.join(" · ")}`, at: at.toISOString() };
  }
  const ok = parseInt(pan, 16) === 0 && parseInt(tilt, 16) === 0;
  return {
    moduleId: "platform",
    kind: "selftest",
    ok,
    detail: `флаги ошибок PAN 0x${pan.toUpperCase()} · TILT 0x${tilt.toUpperCase()}${ok ? " · ошибок нет" : " · есть ошибки"}`,
    at: at.toISOString(),
  };
}

export interface ReportRow {
  index: number;
  name: string;
  kind: string;
  address: string;
  check: string;
  status: "pass" | "fail" | "pending";
  detail: string;
  time: string;
}

export interface ReportModel {
  productTitle: string;
  serialNumber: string;
  operator: string;
  version: string;
  generatedAt: Date;
  browserMode: boolean;
  rows: ReportRow[];
  passed: number;
  failed: number;
  pending: number;
  verdict: "ok" | "fail" | "incomplete";
}

const CHECKS: Record<TestKind, string> = {
  tcp: "Сетевая доступность (TCP)",
  selftest: "Самодиагностика осей PAN/TILT",
};

const formatTime = (iso: string) =>
  new Date(iso).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });

/** Every visible module needs a TCP check; the platform additionally needs its self-test. */
export function buildReport(
  config: AppConfig,
  modules: ModuleView[],
  log: Record<string, TestRecord>,
  generatedAt: Date,
  version: string,
  browserMode: boolean,
): ReportModel {
  const rows: ReportRow[] = [];
  for (const module of modules.filter((item) => !item.hidden)) {
    const kinds: TestKind[] = module.id === "platform" ? ["tcp", "selftest"] : ["tcp"];
    for (const kind of kinds) {
      const record = log[testKey(module.id, kind)];
      rows.push({
        index: rows.length + 1,
        name: module.name,
        kind: `${KIND_LABELS[module.kind]} · ${module.protocol}`,
        address: `${module.ip}:${module.port}`,
        check: CHECKS[kind],
        status: record ? (record.ok ? "pass" : "fail") : "pending",
        detail: record?.detail ?? "проверка не выполнялась",
        time: record ? formatTime(record.at) : "—",
      });
    }
  }
  const passed = rows.filter((row) => row.status === "pass").length;
  const failed = rows.filter((row) => row.status === "fail").length;
  const pending = rows.length - passed - failed;
  const verdict = failed > 0 ? "fail" : pending > 0 || rows.length === 0 ? "incomplete" : "ok";
  return {
    productTitle: config.productTitle,
    serialNumber: config.report.serialNumber,
    operator: config.report.operator,
    version,
    generatedAt,
    browserMode,
    rows,
    passed,
    failed,
    pending,
    verdict,
  };
}

export const reportFileStamp = (date: Date) => {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}-${pad(date.getMinutes())}`;
};

export const formatReportDate = (date: Date) => formatTime(date.toISOString());
