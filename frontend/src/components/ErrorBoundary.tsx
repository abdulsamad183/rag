import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("UI error", error, info.componentStack);
  }

  render(): ReactNode {
    if (this.state.error) {
      return (
        <div className="page">
          <div className="card" style={{ borderColor: "rgba(248, 113, 113, 0.4)" }}>
            <h2>Something went wrong</h2>
            <p className="dim" style={{ marginTop: 8 }}>
              {this.state.error.message}
            </p>
            <button
              className="btn"
              style={{ marginTop: 14 }}
              onClick={() => this.setState({ error: null })}
            >
              Try again
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
