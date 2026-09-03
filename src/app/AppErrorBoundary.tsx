import { AlertTriangle, RotateCcw } from 'lucide-react';
import { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * Top-level error boundary for the new SIE application. A restyled,
 * restrained sibling of the legacy `src/components/ErrorBoundary.tsx`
 * (which is left untouched) — same responsibility, but light/professional
 * presentation with no hardcoded product branding.
 */
export class AppErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Unhandled error in SIE application:', error, errorInfo);
  }

  private handleReload = () => {
    window.location.assign('/');
  };

  render() {
    if (this.state.hasError) {
      return (
        <div data-sie-app className="min-h-screen flex items-center justify-center bg-background p-6">
          <div className="max-w-md w-full rounded-lg border border-border bg-surface shadow-sm p-6 text-center">
            <div className="mx-auto mb-4 flex h-10 w-10 items-center justify-center rounded-full bg-critical-surface text-critical">
              <AlertTriangle className="h-5 w-5" aria-hidden="true" />
            </div>
            <h1 className="text-base font-semibold text-text-primary">Something went wrong</h1>
            <p className="mt-1.5 text-sm text-text-secondary">
              An unexpected error occurred while displaying this page. You can return to Home and try again.
            </p>
            {this.state.error?.message && (
              <p className="mt-3 rounded-md border border-border bg-surface-muted p-2.5 text-left text-xs text-text-muted break-words">
                {this.state.error.message}
              </p>
            )}
            <button
              type="button"
              onClick={this.handleReload}
              className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-md bg-navy-800 px-4 py-2 text-sm font-medium text-white hover:bg-navy-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600"
            >
              <RotateCcw className="h-4 w-4" aria-hidden="true" />
              Return to Home
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
