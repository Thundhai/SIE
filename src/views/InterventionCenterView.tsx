import React, { useState } from 'react';
import { 
  ShieldAlert, 
  CheckCircle2, 
  Clock, 
  AlertTriangle, 
  UserCheck, 
  TrendingDown, 
  ChevronRight, 
  Sliders, 
  X, 
  Check, 
  Sparkles,
  ArrowRight,
  BarChart2
} from 'lucide-react';
import { InterventionItem, InterventionStatus } from '../types';
import { INTERVENTIONS } from '../mockData';

interface InterventionCenterViewProps {
  onNavigateToOutcome: (interventionId: string) => void;
  onSelectRisk: (riskId: string) => void;
}

export const InterventionCenterView: React.FC<InterventionCenterViewProps> = ({
  onNavigateToOutcome,
  onSelectRisk
}) => {
  const [interventionsList, setInterventionsList] = useState<InterventionItem[]>(INTERVENTIONS);
  const [activeTab, setActiveTab] = useState<'recommended' | 'active' | 'outcomes'>('recommended');
  const [selectedIntervention, setSelectedIntervention] = useState<InterventionItem | null>(INTERVENTIONS[0]);
  const [assigneeInput, setAssigneeInput] = useState('');
  const [showAssignModal, setShowAssignModal] = useState(false);

  const handleUpdateStatus = (id: string, status: InterventionStatus) => {
    setInterventionsList(prev => prev.map(item => {
      if (item.id === id) {
        return { ...item, status };
      }
      return item;
    }));
  };

  const handleToggleChecklist = (intId: string, actionId: number) => {
    setInterventionsList(prev => prev.map(item => {
      if (item.id === intId) {
        const updated = item.recommendedActions.map(a => {
          if (a.id === actionId) {
            return { ...a, completed: !a.completed };
          }
          return a;
        });
        return { ...item, recommendedActions: updated };
      }
      return item;
    }));
  };

  const filteredList = interventionsList.filter(item => {
    if (activeTab === 'recommended') return item.status === 'Recommended' || item.status === 'Active';
    if (activeTab === 'active') return item.status === 'Active';
    if (activeTab === 'outcomes') return item.outcomeData !== undefined;
    return true;
  });

  return (
    <div className="space-y-6 animate-in fade-in duration-200">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl sm:text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
              <ShieldAlert className="w-6 h-6 text-amber-400" />
              <span>Safety Intervention Center</span>
            </h1>
            <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-amber-950 text-amber-300 border border-amber-800">
              AI Prescriptive Engine
            </span>
          </div>
          <p className="text-xs sm:text-sm text-slate-400 mt-1 max-w-3xl leading-relaxed">
            Targeted engineering controls, supervisory campaigns, and competency actions dynamically tailored to emerging risk drivers.
          </p>
        </div>

        <button
          onClick={() => onNavigateToOutcome('INT-LIFT-2026-01')}
          className="px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-semibold transition-colors flex items-center gap-2 shrink-0"
        >
          <BarChart2 className="w-4 h-4 text-cyan-400" />
          <span>Intervention Effectiveness (Case Study)</span>
        </button>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-800 pb-1">
        <button
          onClick={() => setActiveTab('recommended')}
          className={`px-4 py-2 text-xs font-semibold rounded-t-lg transition-colors border-b-2 ${
            activeTab === 'recommended'
              ? 'border-amber-400 text-amber-300 bg-slate-900/80'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          All Recommendations ({interventionsList.length})
        </button>
        <button
          onClick={() => setActiveTab('active')}
          className={`px-4 py-2 text-xs font-semibold rounded-t-lg transition-colors border-b-2 ${
            activeTab === 'active'
              ? 'border-amber-400 text-amber-300 bg-slate-900/80'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          Active in Field ({interventionsList.filter(i => i.status === 'Active').length})
        </button>
        <button
          onClick={() => setActiveTab('outcomes')}
          className={`px-4 py-2 text-xs font-semibold rounded-t-lg transition-colors border-b-2 ${
            activeTab === 'outcomes'
              ? 'border-amber-400 text-amber-300 bg-slate-900/80'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          Evaluated Outcomes & Effectiveness
        </button>
      </div>

      {/* Main Interventions Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Interventions List (5 cols) */}
        <div className="lg:col-span-5 space-y-3">
          {filteredList.map((item) => {
            const isSelected = selectedIntervention?.id === item.id;
            return (
              <div
                key={item.id}
                onClick={() => setSelectedIntervention(item)}
                className={`p-4 rounded-xl border cursor-pointer transition-all ${
                  isSelected
                    ? 'bg-amber-950/40 border-amber-500 shadow-md ring-1 ring-amber-500/40'
                    : 'bg-slate-900/90 border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded uppercase ${
                    item.priority === 'Immediate'
                      ? 'bg-rose-950 text-rose-300 border border-rose-800'
                      : 'bg-amber-950 text-amber-300 border border-amber-800'
                  }`}>
                    {item.priority} Priority
                  </span>
                  <span className="text-[10px] font-mono text-slate-400">{item.status}</span>
                </div>

                <h3 className="text-sm font-bold text-white mt-2 leading-snug">
                  {item.title}
                </h3>
                <p className="text-xs text-slate-400 mt-1 line-clamp-2 leading-relaxed">
                  {item.reason}
                </p>

                <div className="mt-3 pt-2.5 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-400">
                  <span className="text-cyan-300 font-medium">{item.targetRiskCategory}</span>
                  <span className="font-mono text-slate-500">{item.recommendedActions.length} Actions</span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Right: Detailed Intervention Workspace (7 cols) */}
        {selectedIntervention ? (
          <div className="lg:col-span-7 p-6 rounded-xl bg-slate-900/90 border border-slate-800 space-y-5">
            {/* Header & Target Risk */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-800">
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono font-bold text-amber-400">{selectedIntervention.id}</span>
                  <span className="text-xs text-slate-400 font-mono">• Target: {selectedIntervention.targetRiskCategory}</span>
                </div>
                <h2 className="text-base sm:text-lg font-bold text-white mt-1">
                  {selectedIntervention.title}
                </h2>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => onSelectRisk(selectedIntervention.targetRiskId)}
                  className="text-xs text-cyan-400 hover:underline flex items-center gap-1 font-semibold"
                >
                  <span>View Causal Model</span>
                  <ChevronRight className="w-3 h-3" />
                </button>
              </div>
            </div>

            {/* AI Diagnosis Reason */}
            <div className="p-3.5 rounded-lg bg-slate-950/80 border border-slate-800">
              <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block mb-1">
                Trigger Rationale:
              </span>
              <p className="text-xs text-slate-200 leading-relaxed">
                {selectedIntervention.reason}
              </p>
            </div>

            {/* Recommended Action Checklist (Interactive) */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  <span>Prescribed Action Checklist ({selectedIntervention.recommendedActions.length} Steps)</span>
                </h3>
                <span className="text-[11px] text-slate-400 font-mono">
                  {selectedIntervention.recommendedActions.filter(a => a.completed).length} / {selectedIntervention.recommendedActions.length} Completed
                </span>
              </div>

              <div className="space-y-2">
                {selectedIntervention.recommendedActions.map((act) => (
                  <div
                    key={act.id}
                    onClick={() => handleToggleChecklist(selectedIntervention.id, act.id)}
                    className={`p-3.5 rounded-lg border text-xs cursor-pointer transition-all flex items-start gap-3 ${
                      act.completed
                        ? 'bg-emerald-950/30 border-emerald-800/60 text-slate-300'
                        : 'bg-slate-950/70 border-slate-800 text-slate-200 hover:border-slate-700'
                    }`}
                  >
                    <div className={`w-4 h-4 rounded mt-0.5 border flex items-center justify-center transition-colors ${
                      act.completed ? 'bg-emerald-600 border-emerald-500 text-white' : 'border-slate-600'
                    }`}>
                      {act.completed && <Check className="w-3 h-3" />}
                    </div>

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <span className={`font-semibold ${act.completed ? 'line-through text-slate-400' : 'text-slate-100'}`}>
                          {act.id}. {act.title}
                        </span>
                        <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-slate-900 text-slate-400 border border-slate-800">
                          {act.assignedRole}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">
                        {act.description}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Expected Impact Indicators */}
            <div className="p-4 rounded-lg bg-slate-950/80 border border-slate-800 space-y-2">
              <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
                Targeted Metric Shifts (Expected Indicators):
              </span>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 pt-1">
                {selectedIntervention.expectedIndicators.map((ind, i) => (
                  <div key={i} className="p-2.5 rounded bg-slate-900 border border-slate-800 text-xs">
                    <span className="text-slate-400 block text-[10px]">{ind.metric}</span>
                    <span className="font-mono font-bold text-emerald-400 mt-0.5 block">{ind.expectedShift}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Decision & Assignment Buttons (Screen 8 Required Buttons) */}
            <div className="pt-3 border-t border-slate-800 flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleUpdateStatus(selectedIntervention.id, 'Active')}
                  className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow transition-colors flex items-center gap-1.5"
                >
                  <Check className="w-3.5 h-3.5" />
                  <span>Accept Recommendation</span>
                </button>

                <button
                  onClick={() => handleUpdateStatus(selectedIntervention.id, 'Dismissed')}
                  className="px-3 py-2 rounded-lg bg-slate-800 hover:bg-rose-900/60 hover:text-rose-200 border border-slate-700 text-slate-300 text-xs font-medium transition-colors flex items-center gap-1.5"
                >
                  <X className="w-3.5 h-3.5" />
                  <span>Reject</span>
                </button>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => onNavigateToOutcome(selectedIntervention.id)}
                  className="px-3.5 py-2 rounded-lg bg-cyan-950/60 hover:bg-cyan-900/60 border border-cyan-800 text-cyan-300 text-xs font-medium transition-colors flex items-center gap-1.5"
                >
                  <span>View Outcome / Effectiveness</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
};
