import React, { ErrorInfo, ReactNode } from 'react';
import { AlertOctagon, RotateCcw } from 'lucide-react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = {
      hasError: false,
      error: null
    };
  }

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Uncaught error caught by ErrorBoundary:', error, errorInfo);
  }

  private handleReload = () => {
    this.setState({ hasError: false, error: null });
    window.location.reload();
  };

  public render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-[#09090B] text-slate-100 flex items-center justify-center p-6">
          <div className="max-w-md w-full p-6 rounded-xl bg-[#16181D] border border-red-500/30 shadow-2xl text-center space-y-4">
            <div className="w-12 h-12 rounded-xl bg-red-950/60 border border-red-500/40 flex items-center justify-center mx-auto text-red-400">
              <AlertOctagon className="w-6 h-6" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white tracking-tight">System Encountered an Issue</h2>
              <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                An unexpected exception occurred during rendering. You can reset the interface to continue.
              </p>
            </div>
            {this.state.error?.message && (
              <div className="p-3 rounded-lg bg-[#09090B] border border-white/5 text-[11px] font-mono text-red-300 text-left overflow-auto max-h-24">
                {this.state.error.message}
              </div>
            )}
            <button
              onClick={this.handleReload}
              className="w-full py-2.5 px-4 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold flex items-center justify-center gap-2 transition-all shadow-md shadow-blue-600/20"
            >
              <RotateCcw className="w-4 h-4" />
              <span>Reload Safelytic Platform</span>
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

