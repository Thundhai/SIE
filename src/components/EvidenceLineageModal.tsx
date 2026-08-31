import React, { useState } from 'react';
import { 
  X, 
  BrainCircuit, 
  Sliders, 
  FileText, 
  Sparkles, 
  Activity, 
  ShieldAlert, 
  ArrowRight, 
  CheckCircle2, 
  AlertTriangle, 
  HelpCircle, 
  Database, 
  Scale, 
  ExternalLink,
  ChevronRight,
  Info,
  ShieldCheck,
  Cpu
} from 'lucide-react';
import { EmergingRisk, LineageStageId } from '../types';
import { LINEAGE_STAGES, LineageStageDetail, getRiskMethodology } from '../utils/methodologyUtils';

interface EvidenceLineageModalProps {
  isOpen: boolean;
  onClose: () => void;
  risk: EmergingRisk;
  initialStageId?: LineageStageId;
  onNavigateToInterventions?: () => void;
  onOpenEvidenceRecord?: (evidence: any) => void;
}

export const EvidenceLineageModal: React.FC<EvidenceLineageModalProps> = ({
  isOpen,
  onClose,
  risk,
  initialStageId = 'prediction',
  onNavigateToInterventions,
  onOpenEvidenceRecord
}) => {
  const [activeStageId, setActiveStageId] = useState<LineageStageId>(initialStageId);

  // Sync state if initialStageId changes
  React.useEffect(() => {
    if (initialStageId) {
      setActiveStageId(initialStageId);
    }
  }, [initialStageId]);

  if (!isOpen) return null;

  const activeStage = LINEAGE_STAGES.find(s => s.id === activeStageId) || LINEAGE_STAGES[0];
  const methodology = getRiskMethodology(risk);

  const getStageIcon = (id: LineageStageId) => {
    switch (id) {
      case 'prediction': return <BrainCircuit className="w-4 h-4" />;
      case 'risk-factors': return <Sliders className="w-4 h-4" />;
      case 'org-evidence': return <FileText className="w-4 h-4" />;
      case 'external-evidence': return <Sparkles className="w-4 h-4" />;
      case 'analytical-method': return <Activity className="w-4 h-4" />;
      case 'recommendation': return <ShieldAlert className="w-4 h-4" />;
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div 
        className="relative w-full max-w-4xl rounded-2xl bg-[#16181D] border border-white/10 shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-white/10 bg-[#09090B]/80">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400">
              <BrainCircuit className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-blue-950/80 text-blue-300 border border-blue-800 uppercase font-bold tracking-wider">
                  Scientific Evidence Lineage
                </span>
                <span className="text-[10px] font-mono text-slate-400">Risk ID: {risk.id}</span>
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-950/60 text-amber-300 border border-amber-800/60 font-semibold">
                  DEMO PROTOTYPE
                </span>
              </div>
              <h2 className="text-base sm:text-lg font-bold text-white tracking-tight mt-1">
                {risk.category}: Analytical Lineage &amp; Model Assumptions
              </h2>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Interactive Lineage Step Rail */}
        <div className="p-4 bg-[#09090B]/50 border-b border-white/5 overflow-x-auto">
          <div className="flex items-center justify-between min-w-[650px] gap-2">
            {LINEAGE_STAGES.map((stage, idx) => {
              const isActive = stage.id === activeStageId;
              return (
                <React.Fragment key={stage.id}>
                  <button
                    onClick={() => setActiveStageId(stage.id)}
                    className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold transition-all shrink-0 ${
                      isActive
                        ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/25 border border-blue-400'
                        : 'bg-[#16181D] text-slate-300 hover:text-white hover:bg-white/5 border border-white/5'
                    }`}
                  >
                    <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-mono font-bold ${
                      isActive ? 'bg-white text-blue-700' : 'bg-slate-800 text-slate-300'
                    }`}>
                      {stage.stepNumber}
                    </span>
                    <span>{stage.label}</span>
                  </button>

                  {idx < LINEAGE_STAGES.length - 1 && (
                    <ArrowRight className="w-3.5 h-3.5 text-slate-600 shrink-0" />
                  )}
                </React.Fragment>
              );
            })}
          </div>
        </div>

        {/* Body Content */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1 text-slate-200">
          {/* Stage Overview Banner */}
          <div className="p-4 rounded-xl bg-[#09090B] border border-white/5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className="p-2.5 rounded-lg bg-blue-500/10 border border-blue-500/20 text-blue-400 shrink-0 mt-0.5">
                {getStageIcon(activeStage.id)}
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-mono text-slate-500 uppercase tracking-wider font-bold">
                    Stage {activeStage.stepNumber} of 6 • {activeStage.category}
                  </span>
                </div>
                <h3 className="text-base font-bold text-white mt-0.5">
                  {activeStage.methodologyDetails.title}
                </h3>
                <p className="text-xs text-slate-400 mt-1 leading-relaxed max-w-2xl">
                  {activeStage.methodologyDetails.description}
                </p>
              </div>
            </div>

            <div className="text-right shrink-0 p-3 rounded-lg bg-[#16181D] border border-white/5">
              <div className="text-[10px] font-mono text-slate-400 uppercase">Stage Verification</div>
              <div className="text-xs font-bold text-emerald-400 flex items-center gap-1.5 justify-end mt-0.5">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Lineage Trace Valid</span>
              </div>
            </div>
          </div>

          {/* Key Inputs & Assumptions Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {/* Key Inputs */}
            <div className="p-4 rounded-xl bg-[#09090B]/70 border border-white/5 space-y-3">
              <div className="flex items-center gap-2 text-xs font-bold text-slate-200">
                <Database className="w-4 h-4 text-blue-400" />
                <span>Empirical &amp; Parameter Inputs</span>
              </div>
              <ul className="space-y-2 text-xs text-slate-300">
                {activeStage.methodologyDetails.keyInputs.map((input, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-blue-400 mt-1.5 shrink-0" />
                    <span>{input}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Model Assumptions */}
            <div className="p-4 rounded-xl bg-[#09090B]/70 border border-white/5 space-y-3">
              <div className="flex items-center gap-2 text-xs font-bold text-slate-200">
                <Scale className="w-4 h-4 text-amber-400" />
                <span>Explicit Analytical Assumptions</span>
              </div>
              <ul className="space-y-2 text-xs text-slate-300">
                {activeStage.methodologyDetails.assumptions.map((assumption, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-amber-400 mt-1.5 shrink-0" />
                    <span>{assumption}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* Mathematical / Algorithmic Formulation & Limitations */}
          <div className="grid grid-cols-1 md:grid-cols-12 gap-5">
            <div className="md:col-span-7 p-4 rounded-xl bg-[#09090B]/70 border border-white/5 space-y-2.5">
              <div className="flex items-center gap-2 text-xs font-bold text-slate-200">
                <Cpu className="w-4 h-4 text-cyan-400" />
                <span>Mathematical / Algorithmic Formulation</span>
              </div>
              <div className="p-3 rounded-lg bg-[#16181D] border border-cyan-900/40 font-mono text-xs text-cyan-300 overflow-x-auto">
                {activeStage.methodologyDetails.mathematicalMethod}
              </div>
              <p className="text-[11px] text-slate-400">
                Processed via deterministic parameter equations with Bayesian posterior updates.
              </p>
            </div>

            <div className="md:col-span-5 p-4 rounded-xl bg-[#09090B]/70 border border-white/5 space-y-2.5">
              <div className="flex items-center gap-2 text-xs font-bold text-slate-200">
                <AlertTriangle className="w-4 h-4 text-rose-400" />
                <span>Known Analytical Limitations</span>
              </div>
              <ul className="space-y-1.5 text-[11px] text-slate-400">
                {activeStage.methodologyDetails.limitations.map((limit, i) => (
                  <li key={i} className="flex items-start gap-1.5">
                    <span className="text-rose-400">•</span>
                    <span>{limit}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* Specific Stage Interactive Artifacts */}
          {activeStage.id === 'risk-factors' && (
            <div className="p-4 rounded-xl bg-[#09090B]/70 border border-white/5 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-white">Active Contributing Factors for {risk.id}</span>
                <span className="text-[10px] font-mono text-slate-400">100% Variance Normalization</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {risk.contributingFactors.map((factor) => (
                  <div key={factor.name} className="p-3 rounded-lg bg-[#16181D] border border-white/5">
                    <div className="flex items-center justify-between text-xs mb-1">
                      <span className="font-semibold text-slate-200">{factor.name}</span>
                      <span className="font-mono font-bold text-blue-400">{factor.percentage}%</span>
                    </div>
                    <div className="w-full h-1.5 rounded-full bg-slate-800 overflow-hidden mb-1">
                      <div
                        className={`h-full rounded-full ${
                          factor.impact === 'High' ? 'bg-rose-500' : 'bg-amber-500'
                        }`}
                        style={{ width: `${factor.percentage}%` }}
                      />
                    </div>
                    <p className="text-[10px] text-slate-400">{factor.description}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeStage.id === 'org-evidence' && (
            <div className="p-4 rounded-xl bg-[#09090B]/70 border border-white/5 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-white">Sample Linked Organization Records ({risk.organizationEvidence.length} Ingested)</span>
                <span className="text-[10px] font-mono text-slate-400">Click to Inspect Record</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {risk.organizationEvidence.slice(0, 4).map((ev) => (
                  <div 
                    key={ev.id}
                    onClick={() => onOpenEvidenceRecord && onOpenEvidenceRecord(ev)}
                    className="p-3 rounded-lg bg-[#16181D] border border-white/5 hover:border-blue-500/40 cursor-pointer transition-all"
                  >
                    <div className="flex items-center justify-between text-[10px] font-mono">
                      <span className="font-bold text-blue-400">{ev.id}</span>
                      <span className="text-slate-400">{ev.date}</span>
                    </div>
                    <h5 className="text-xs font-semibold text-white mt-1 line-clamp-1">{ev.title}</h5>
                    <p className="text-[10px] text-slate-400 mt-1 line-clamp-2">{ev.details}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeStage.id === 'external-evidence' && (
            <div className="p-4 rounded-xl bg-[#09090B]/70 border border-white/5 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-white">Verified External Knowledge Standards ({risk.externalEvidence.length} Citations)</span>
                <span className="text-[10px] font-mono text-purple-400">Verified Grounding</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {risk.externalEvidence.map((ext) => (
                  <div 
                    key={ext.id}
                    onClick={() => onOpenEvidenceRecord && onOpenEvidenceRecord(ext)}
                    className="p-3 rounded-lg bg-[#16181D] border border-white/5 hover:border-purple-500/40 cursor-pointer transition-all"
                  >
                    <div className="flex items-center justify-between text-[10px] font-mono">
                      <span className="font-semibold text-purple-300">{ext.publisher}</span>
                      <span className="text-emerald-400">{ext.reliability} Reliability</span>
                    </div>
                    <h5 className="text-xs font-bold text-white mt-1">{ext.documentTitle}</h5>
                    <div className="text-[10px] font-mono text-slate-500">{ext.code} • {ext.jurisdiction}</div>
                    <p className="text-[10px] text-slate-300 italic mt-1 line-clamp-2">&ldquo;{ext.keyExcerpt}&rdquo;</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Mandatory Scientific Interpretation Notice */}
          <div className="p-4 rounded-xl bg-amber-950/30 border border-amber-500/30 text-amber-200/90 text-xs flex items-start gap-3">
            <Info className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
            <div>
              <span className="font-bold text-amber-300 block mb-0.5">Scientific Interpretation Notice</span>
              <p className="leading-relaxed">
                Predictions are analytical risk indicators, not guarantees that an incident will occur. They should support—not replace—professional HSE judgement.
              </p>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-white/10 bg-[#09090B]/90 flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-3 text-xs text-slate-400 font-mono">
            <span>Model Version: {methodology.modelVersion}</span>
            <span>•</span>
            <span>Generated: {methodology.generatedDate}</span>
          </div>

          <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-lg bg-[#16181D] hover:bg-white/5 text-slate-300 text-xs font-semibold border border-white/10 transition-colors"
            >
              Close Lineage
            </button>
            {onNavigateToInterventions && (
              <button
                onClick={() => {
                  onClose();
                  onNavigateToInterventions();
                }}
                className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-md transition-colors flex items-center gap-1.5"
              >
                <ShieldAlert className="w-3.5 h-3.5" />
                <span>Review Recommended Interventions</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
