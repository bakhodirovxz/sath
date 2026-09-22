import { Component, type ErrorInfo, type ReactNode } from "react";

/** Xatolar chegarasi (F12): bitta panel render xatosi butun dispetcher sahifasini oq ekranga aylantirmaydi —
 * faqat shu panel o'rniga qisqa xato va «Qayta urinish». Xato konsolga yoziladi (yutilmaydi). */
export default class ErrorBoundary extends Component<{ name?: string; children: ReactNode; compact?: boolean }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`[panel:${this.props.name ?? "?"}]`, error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className={`panel error-boundary ${this.props.compact ? "small" : ""}`} role="alert" data-testid="panel-error">
          <b>{this.props.name ?? "Panel"}</b> ishlamadi: <span className="mono">{this.state.error.message}</span>
          <button className="btn sm" style={{ marginLeft: 8 }} onClick={() => this.setState({ error: null })}>Qayta urinish</button>
        </div>
      );
    }
    return this.props.children;
  }
}
