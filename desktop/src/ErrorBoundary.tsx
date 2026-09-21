import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

/** Keeps a rendering bug from leaving the operator with a blank window. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("MKIS100TEST UI error", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="fatal" role="alert">
        <strong>Интерфейс остановлен из-за ошибки</strong>
        <code>{this.state.error.message}</code>
        <span>Движение TL.0009 остановлено сторожевым таймером.</span>
        <button type="button" onClick={() => window.location.reload()}>Перезапустить интерфейс</button>
      </div>
    );
  }
}
