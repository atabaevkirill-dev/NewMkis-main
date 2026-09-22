import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { ChevronRight } from "lucide-react";

export function Toggle({ value, onChange, label, title, disabled }: {
  value: boolean;
  onChange: (value: boolean) => void;
  label?: string;
  title?: string;
  disabled?: boolean;
}) {
  return (
    <button className={`toggle ${value ? "is-on" : ""}`} onClick={() => onChange(!value)} type="button" aria-pressed={value} title={title} disabled={disabled}>
      <span />
      {label && <em>{label}</em>}
    </button>
  );
}

/** Numeric input that lets the operator type freely ("-", "", "1.") and commits only finite numbers. */
export function NumberField({ value, onChange, label, unit, min, max, integer, className = "", title }: {
  value: number;
  onChange: (value: number) => void;
  label?: string;
  unit?: string;
  min?: number;
  max?: number;
  integer?: boolean;
  className?: string;
  title?: string;
}) {
  const [draft, setDraft] = useState(String(value));
  useEffect(() => {
    setDraft((current) => (Number(current.replace(",", ".")) === value ? current : String(value)));
  }, [value]);
  const invalid = (min !== undefined && value < min) || (max !== undefined && value > max);
  const change = (text: string) => {
    setDraft(text);
    const parsed = Number(text.replace(",", "."));
    if (text.trim() !== "" && Number.isFinite(parsed)) onChange(integer ? Math.round(parsed) : parsed);
  };
  return (
    <label className={`number-field ${invalid ? "invalid" : ""} ${className}`} title={title}>
      {label && <span>{label}</span>}
      <div>
        <input inputMode="decimal" value={draft} onChange={(event) => change(event.target.value)} onBlur={() => setDraft(String(value))} spellCheck={false} />
        {unit && <em>{unit}</em>}
      </div>
    </label>
  );
}

export function Section({ title, badge, open, onToggle, children }: {
  title: string;
  badge?: string;
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <section className={`drawer-section ${open ? "open" : ""}`}>
      <button className="section-toggle" onClick={onToggle} type="button" aria-expanded={open}>
        <ChevronRight className="chevron" />
        <span>{title}</span>
        {badge && <small>{badge}</small>}
      </button>
      {open && <div className="section-body">{children}</div>}
    </section>
  );
}

/** Two-step action for destructive or motion-causing buttons: the first click arms, the second confirms. */
export function useConfirm(timeoutMs = 3500): [armed: boolean, trigger: (action: () => void) => void] {
  const [armed, setArmed] = useState(false);
  const timer = useRef<number | null>(null);
  useEffect(() => () => {
    if (timer.current !== null) window.clearTimeout(timer.current);
  }, []);
  const trigger = (action: () => void) => {
    if (timer.current !== null) window.clearTimeout(timer.current);
    if (armed) {
      setArmed(false);
      action();
      return;
    }
    setArmed(true);
    timer.current = window.setTimeout(() => setArmed(false), timeoutMs);
  };
  return [armed, trigger];
}

/** Time left until `endsAt` (epoch ms) as h:mm:ss / m:ss, ticking once a second. */
export function Countdown({ endsAt }: { endsAt: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const total = Math.max(0, Math.ceil((endsAt - now) / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor(total / 60) % 60;
  const seconds = String(total % 60).padStart(2, "0");
  return <span className="countdown">{hours > 0 ? `${hours}:${String(minutes).padStart(2, "0")}:${seconds}` : `${minutes}:${seconds}`}</span>;
}
