import React, { Component } from 'react';
import { AlertTriangle, RotateCcw } from 'lucide-react';

export class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught an unhandled rendering error:', error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center min-h-[60vh] p-8 text-center">
          <div className="w-12 h-12 rounded-full bg-rose-500/10 border border-rose-500/20 flex items-center justify-center mb-4">
            <AlertTriangle className="w-6 h-6 text-rose-400" />
          </div>
          <h2 className="text-xl font-semibold text-content-primary mb-2">Something went wrong</h2>
          <p className="text-sm text-content-secondary max-w-md mb-6 leading-relaxed">
            An unexpected client error occurred while rendering this interface.
          </p>
          <div className="p-3 mb-6 bg-background-subtle border border-border-subtle rounded text-xs font-mono text-content-muted max-w-lg overflow-x-auto">
            {this.state.error?.message || 'Unknown error'}
          </div>
          <button
            onClick={this.handleReset}
            className="inline-flex items-center gap-2 px-4 py-2 bg-background-card hover:bg-background-hover border border-border-subtle rounded-md text-sm font-medium text-content-primary transition-colors"
          >
            <RotateCcw className="w-4 h-4" />
            Reload Application
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
