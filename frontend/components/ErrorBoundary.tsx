"use client";

import { Component, ReactNode } from "react";

interface Props { children: ReactNode }
interface State { error: Error | null }

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex items-center justify-center h-screen bg-[var(--background)]">
          <div className="max-w-md text-center px-6">
            <div className="text-4xl mb-4">⚠️</div>
            <h2 className="text-lg font-semibold text-[var(--text)] mb-2">Something went wrong</h2>
            <p className="text-sm text-[var(--text-muted)] mb-6">{this.state.error.message}</p>
            <button
              onClick={() => this.setState({ error: null })}
              className="bg-[var(--accent)] text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-[var(--accent-light)] transition-colors"
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
