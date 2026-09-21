import { useCallback, useEffect, useMemo, useRef } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { platformJog, platformKeepalive, platformStop, type JogDirection } from "./api";
import type { JogConfig, Notify } from "./types";

const KEEPALIVE_MS = 250;
const LABELS: Record<JogDirection, string> = { left: "ВЛЕВО", right: "ВПРАВО", up: "ВВЕРХ", down: "ВНИЗ" };

export interface JogControl {
  /** Pointer handlers for a hold-to-move button. */
  bind: (direction: JogDirection) => {
    onPointerDown: (event: ReactPointerEvent<HTMLElement>) => void;
    onPointerUp: () => void;
    onPointerCancel: () => void;
    onLostPointerCapture: () => void;
  };
  /** Stops both axes even when no jog is active (STOP button, Esc). */
  stopNow: () => void;
}

/**
 * Dead-man jog: motion lasts only while the button is held. The pointer is captured, the native side is
 * confirmed every 250 ms, and releasing, cancelling, losing capture, blurring or hiding the window stops the axes.
 * If the view itself dies, the native watchdog stops the axes when confirmations cease.
 */
export function useJog(target: { ip: string; port: number; label: string }, speeds: JogConfig, notify: Notify): JogControl {
  const active = useRef<JogDirection | null>(null);
  const timer = useRef<number | null>(null);
  const latest = useRef({ target, speeds, notify });
  latest.current = { target, speeds, notify };

  const clearTimer = () => {
    if (timer.current !== null) window.clearInterval(timer.current);
    timer.current = null;
  };

  const stop = useCallback((force: boolean) => {
    const wasActive = active.current !== null;
    active.current = null;
    clearTimer();
    if (!wasActive && !force) return;
    const { target: { ip, port, label }, notify: report } = latest.current;
    platformStop(ip, port)
      .then(() => report(`${label} · СТОП`))
      .catch((error) => report(`${label} · стоп не доставлен: ${String(error)}`, "error"));
  }, []);

  const start = useCallback((direction: JogDirection) => {
    if (active.current === direction) return;
    active.current = direction;
    clearTimer();
    const { target: { ip, port, label }, speeds: { panSpeed, tiltSpeed }, notify: report } = latest.current;
    const speed = direction === "left" || direction === "right" ? panSpeed : tiltSpeed;
    timer.current = window.setInterval(() => void platformKeepalive().catch(() => undefined), KEEPALIVE_MS);
    platformJog(ip, port, direction, speed)
      .then((reply) => report(`${label} · ${LABELS[direction]} ${speed}°/с · ${reply}`))
      .catch((error) => {
        if (active.current === direction) {
          active.current = null;
          clearTimer();
        }
        report(`${label} · ${String(error)}`, "error");
      });
  }, []);

  useEffect(() => {
    const release = () => stop(false);
    const onVisibility = () => {
      if (document.hidden) stop(false);
    };
    window.addEventListener("blur", release);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.removeEventListener("blur", release);
      document.removeEventListener("visibilitychange", onVisibility);
      stop(false);
    };
  }, [stop]);

  return useMemo<JogControl>(() => ({
    bind: (direction) => ({
      onPointerDown: (event) => {
        if (event.button !== 0) return;
        event.currentTarget.setPointerCapture(event.pointerId);
        start(direction);
      },
      onPointerUp: () => stop(false),
      onPointerCancel: () => stop(false),
      onLostPointerCapture: () => stop(false),
    }),
    stopNow: () => stop(true),
  }), [start, stop]);
}
