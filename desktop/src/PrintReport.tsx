import { formatReportDate, type ReportModel } from "./report";

const VERDICTS: Record<ReportModel["verdict"], (model: ReportModel) => string> = {
  ok: (model) => `ИСПРАВНО — все проверки пройдены (${model.passed} из ${model.rows.length})`,
  fail: (model) => `НЕИСПРАВНОСТИ — не пройдено ${model.failed} из ${model.rows.length}`,
  incomplete: (model) => `ПРОВЕРКА НЕ ЗАВЕРШЕНА — не выполнено ${model.pending} из ${model.rows.length}`,
};

const STATUS: Record<"pass" | "fail" | "pending", string> = { pass: "✓ Пройдена", fail: "✗ Не пройдена", pending: "— Не выполнена" };

/** A4 protocol, visible only when printing (Save as PDF). Built strictly from executed checks. */
export function PrintReport({ model }: { model: ReportModel }) {
  return (
    <article className="print-report" aria-hidden="true">
      <header className="report-head">
        <div>
          <strong>MKIS100TEST</strong>
          <span>Программное обеспечение {model.version}</span>
        </div>
        <div className="report-stamp">Сформирован {formatReportDate(model.generatedAt)}</div>
      </header>

      <h1>Протокол проверки работоспособности</h1>
      <p className="report-product">{model.productTitle || "Полное наименование изделия не задано"}</p>

      <dl className="report-meta">
        <div><dt>Заводской №</dt><dd>{model.serialNumber || "________________"}</dd></div>
        <div><dt>Дата проверки</dt><dd>{formatReportDate(model.generatedAt).split(",")[0]}</dd></div>
        <div><dt>Проверку провёл</dt><dd>{model.operator || "________________"}</dd></div>
      </dl>

      {model.browserMode && (
        <p className="report-warning">Сформировано в браузерном режиме: оборудование не опрашивалось, протокол недействителен.</p>
      )}

      <section className={`report-verdict ${model.verdict}`}>
        <span>Заключение</span>
        <strong>{VERDICTS[model.verdict](model)}</strong>
        <small>Пройдено {model.passed} · не пройдено {model.failed} · не выполнено {model.pending}</small>
      </section>

      <table className="report-table">
        <thead>
          <tr>
            <th>№</th>
            <th>Устройство</th>
            <th>Адрес</th>
            <th>Проверка</th>
            <th>Результат</th>
            <th>Время</th>
          </tr>
        </thead>
        <tbody>
          {model.rows.map((row) => (
            <tr key={row.index} className={row.status}>
              <td>{row.index}</td>
              <td><b>{row.name}</b><small>{row.kind}</small></td>
              <td className="mono">{row.address}</td>
              <td>{row.check}</td>
              <td><b>{STATUS[row.status]}</b><small>{row.detail}</small></td>
              <td className="mono">{row.time}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="report-scope">
        Объём проверки: сетевая доступность каждого модуля по TCP и самодиагностика поворотного устройства
        (флаги ошибок осей $n / $N читаются сразу после запуска самодиагностики). Протокольные проверки ONVIF/RTSP,
        дальномера и Relay X3 в текущей версии ПО не выполняются. Скрытые в «Сводке» модули в протокол не включены.
      </p>

      <footer className="report-sign">
        <div><span>Проверку провёл</span><i /><em>подпись</em><i /><em>Ф. И. О.</em></div>
        <div><span>Дата</span><i /></div>
      </footer>
    </article>
  );
}
