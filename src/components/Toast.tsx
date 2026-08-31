import React from 'react';
import { CheckCircle2, AlertCircle, Info, X } from 'lucide-react';

export interface ToastNotification {
  id: string;
  type: 'success' | 'warning' | 'info' | 'error';
  title: string;
  message: string;
}

export type ToastMessage = ToastNotification;

interface ToastProps {
  toasts: ToastNotification[];
  onDismiss?: (id: string) => void;
  onRemove?: (id: string) => void;
}

export const ToastContainer: React.FC<ToastProps> = ({ toasts, onDismiss, onRemove }) => {
  const dismiss = onRemove || onDismiss || (() => {});
  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2 max-w-md w-full pointer-events-none">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`pointer-events-auto flex items-start gap-3 p-4 rounded-xl shadow-2xl border backdrop-blur-md transition-all duration-200 animate-in fade-in slide-in-from-bottom-2 ${
            toast.type === 'success'
              ? 'bg-[#16181D]/95 border-emerald-500/30 text-emerald-100'
              : toast.type === 'warning'
              ? 'bg-[#16181D]/95 border-amber-500/30 text-amber-100'
              : toast.type === 'error'
              ? 'bg-[#16181D]/95 border-red-500/30 text-red-100'
              : 'bg-[#16181D]/95 border-blue-500/30 text-blue-100'
          }`}
        >
          <div className="mt-0.5 shrink-0">
            {toast.type === 'success' && <CheckCircle2 className="w-5 h-5 text-emerald-400" />}
            {toast.type === 'warning' && <AlertCircle className="w-5 h-5 text-amber-400" />}
            {toast.type === 'error' && <AlertCircle className="w-5 h-5 text-red-400" />}
            {toast.type === 'info' && <Info className="w-5 h-5 text-blue-400" />}
          </div>
          <div className="flex-1 min-w-0">
            <h4 className="text-sm font-semibold text-white">{toast.title}</h4>
            <p className="text-xs text-slate-300 mt-0.5 leading-relaxed">{toast.message}</p>
          </div>
          <button
            onClick={() => dismiss(toast.id)}
            className="text-slate-400 hover:text-white p-1 rounded transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      ))}
    </div>
  );
};

