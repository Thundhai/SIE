import React from 'react';
import { 
  Bell, 
  X, 
  AlertTriangle, 
  BookCheck, 
  Sparkles, 
  ArrowRight,
  ShieldAlert,
  CheckCircle2,
  Trash2,
  Sliders
} from 'lucide-react';
import { NotificationItem } from '../types';

interface NotificationDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  notifications: NotificationItem[];
  onMarkAsRead?: (id: string) => void;
  onMarkAllRead?: () => void;
  onClearAll?: () => void;
  onSelectNotification?: (notif: NotificationItem) => void;
  onSelectRisk?: (riskId: string) => void;
  onSelectDoc?: (docId: string) => void;
  onNavigateToSettings?: () => void;
}

export const NotificationDrawer: React.FC<NotificationDrawerProps> = ({
  isOpen,
  onClose,
  notifications,
  onMarkAsRead,
  onMarkAllRead,
  onClearAll,
  onSelectNotification,
  onSelectRisk,
  onSelectDoc,
  onNavigateToSettings
}) => {
  if (!isOpen) return null;

  const handleClear = onClearAll || onMarkAllRead || (() => {});

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-xs animate-in fade-in">
      <div className="w-full max-w-md bg-[#16181D] border-l border-white/10 h-full flex flex-col shadow-2xl animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="p-4 border-b border-white/5 flex items-center justify-between bg-[#0F1117]">
          <div className="flex items-center gap-2">
            <Bell className="w-4 h-4 text-blue-400" />
            <h3 className="text-sm font-bold text-white">Live Safety Signals & Alerts</h3>
            <span className="text-[10px] font-mono px-1.5 py-0.2 rounded-full bg-blue-600/10 text-blue-400 border border-blue-500/20">
              {notifications.filter(n => !n.isRead).length} new
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleClear}
              className="text-xs text-slate-400 hover:text-blue-300 transition-colors"
              title="Mark all as read"
            >
              Clear All
            </button>
            <button
              onClick={onClose}
              className="p-1 rounded text-slate-400 hover:text-white hover:bg-white/5"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Subheader with Thresholds link */}
        <div className="px-4 py-2 bg-[#16181D] border-b border-white/5 flex items-center justify-between text-xs">
          <span className="text-slate-400 text-[11px]">Threshold-Driven Safety Alerts</span>
          {onNavigateToSettings && (
            <button
              onClick={() => {
                onNavigateToSettings();
                onClose();
              }}
              className="flex items-center gap-1.5 text-blue-400 hover:text-blue-300 font-medium text-[11px] hover:underline"
            >
              <Sliders className="w-3 h-3" />
              <span>Configure Thresholds</span>
            </button>
          )}
        </div>

        {/* Notifications List */}
        <div className="flex-1 overflow-y-auto p-3 space-y-2.5 custom-scrollbar">
          {notifications.map((n) => (
            <div
              key={n.id}
              onClick={() => {
                if (onSelectNotification) onSelectNotification(n);
                if (onMarkAsRead) onMarkAsRead(n.id);
              }}
              className={`p-3 rounded-lg border transition-all cursor-pointer ${
                !n.isRead 
                  ? 'bg-[#09090B] border-blue-500/30 shadow-md' 
                  : 'bg-[#0F1117] border-white/5 text-slate-400'
              }`}
            >
              <div className="flex items-start gap-2.5">
                <div className="mt-0.5 shrink-0">
                  {(n.category === 'Risk Alert' || (n as any).type === 'risk_alert') && <AlertTriangle className="w-4 h-4 text-red-400" />}
                  {(n.category === 'Knowledge Update' || (n as any).type === 'knowledge_update') && <BookCheck className="w-4 h-4 text-blue-400" />}
                  {(n.category === 'Intervention' || (n as any).type === 'intervention_update') && <ShieldAlert className="w-4 h-4 text-amber-400" />}
                  {(n.category === 'Data Stream' || (n as any).type === 'data_anomaly') && <Sparkles className="w-4 h-4 text-purple-400" />}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-semibold text-white truncate">{n.title}</h4>
                    <span className="text-[10px] font-mono text-slate-500 shrink-0 ml-1">{n.timestamp}</span>
                  </div>
                  <p className="text-xs text-slate-300 mt-1 leading-relaxed">{n.message}</p>
                  
                  {/* Action Link */}
                  {n.relatedRiskId && (
                    <div className="mt-2 text-[11px] font-medium text-blue-400 hover:text-blue-300 flex items-center gap-1 group">
                      <span>Investigate Risk Prediction</span>
                      <ArrowRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="p-3 bg-[#0F1117] border-t border-white/5 text-[11px] text-slate-500 flex items-center justify-between">
          <span>Real-time stream active</span>
          <span className="font-mono text-emerald-400">SIE Gateway: OK</span>
        </div>
      </div>
    </div>
  );
};

