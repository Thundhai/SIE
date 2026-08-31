import React, { useState } from 'react';
import { 
  BrainCircuit, 
  HelpCircle, 
  Database, 
  Sparkles, 
  Calendar, 
  Sliders, 
  FileText, 
  Activity, 
  ShieldAlert, 
  ArrowRight, 
  CheckCircle2, 
  AlertTriangle, 
  Info,
  ShieldCheck,
  Layers,
  ChevronDown,
  ChevronUp,
  Cpu,
  BarChart3
} from 'lucide-react';
import { EmergingRisk, LineageStageId } from '../types';
import { getRiskMethodology, LINEAGE_STAGES } from '../utils/methodologyUtils';

interface PredictionMethodologyCardProps {
  risk: EmergingRisk;
  onOpenLineageStage: (stageId: LineageStageId) => void;
  compact?: boolean;
}

export const PredictionMethodologyCard: React.FC<PredictionMethodologyCardProps> = ({
  risk,
  onOpenLineageStage,
  compact = false
}) => {
  const [showProbabilityExplainer, setShowProbabilityExplainer] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const methodology = getRiskMethodology(risk);

  return (
    <div className="rounded-xl bg-[#16181D] border border-white/10 shadow-lg overflow-hidden space-y-0">
      {/* Header Banner */}
      <div className="p-5 border-b border-white/5 bg-[#09090B]/60 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-blue-600/10 border border-blue-500/20 flex items-center justify-center text-blue-400">
            <BrainCircuit className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm sm:text-base font-bold text-white tracking-tight">
                Prediction Methodology &amp; Scientific Lineage
              </h3>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-blue-950 text-blue-300 border border-blue-800 font-bold uppercase">
                {methodology.modelVersion}
              </span>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-950/70 text-amber-300 border border-amber-800/70 font-semibold">
                DEMO
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Transparent, multi-source analytical synthesis derived from empirical records, statistical hazard models, and statutory standards.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowProbabilityExplainer(!showProbabilityExplainer)}
            className="px-2.5 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-xs font-semibold text-slate-200 transition-colors flex items-center gap-1.5"
            title="Explain difference between Probability and Confidence"
          >
            <HelpCircle className="w-3.5 h-3.5 text-cyan-400" />
            <span>Probability vs. Confidence</span>
          </button>

          <button
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white transition-colors"
          >
            {isCollapsed ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {!isCollapsed && (
        <div className="p-5 sm:p-6 space-y-6">
          {/* SECTION 1: PROBABILITY VS CONFIDENCE SCIENTIFIC SEPARATION & DATA QUALITY */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
            {/* Left: Prob vs Conf explicit metrics & explanations */}
            <div className="lg:col-span-7 grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Calculated Probability */}
              <div className="p-4 rounded-xl bg-[#09090B] border border-blue-500/20 relative overflow-hidden flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                    <span>Calculated Probability</span>
                    <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-blue-950 text-blue-300 border border-blue-800">
                      Likelihood
                    </span>
                  </div>
                  <div className="text-3xl font-extrabold text-blue-400 font-mono mt-1">
                    {risk.probability}%
                  </div>
                  <p className="text-xs text-slate-300 font-medium mt-1">
                    Estimated likelihood of the modeled risk condition occurring.
                  </p>
                </div>
                <div className="mt-3 pt-2.5 border-t border-white/5 text-[10px] text-slate-400 leading-snug">
                  Forecast Window: <strong className="text-slate-200 font-mono">{methodology.forecastPeriod}</strong> • Computed via Bayesian prior updates on {methodology.dataWindow} telemetry.
                </div>
              </div>

              {/* Model Confidence */}
              <div className="p-4 rounded-xl bg-[#09090B] border border-emerald-500/20 relative overflow-hidden flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                    <span>Model Confidence</span>
                    <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
                      Certainty
                    </span>
                  </div>
                  <div className="text-3xl font-extrabold text-emerald-400 font-mono mt-1">
                    {risk.confidence}%
                  </div>
                  <p className="text-xs text-slate-300 font-medium mt-1">
                    Confidence in analytical assessment based on data quality, evidence strength &amp; model performance.
                  </p>
                </div>
                <div className="mt-3 pt-2.5 border-t border-white/5 text-[10px] text-emerald-400/90 leading-snug font-medium">
                  Note: Indicates analytical robustness. Does NOT imply an X% chance of an accident.
                </div>
              </div>
            </div>

            {/* Right: Data Quality, Evidence Strength, Historical Coverage */}
            <div className="lg:col-span-5 p-4 rounded-xl bg-[#09090B] border border-white/5 flex flex-col justify-between space-y-3">
              <div>
                <div className="flex items-center justify-between text-xs font-bold text-slate-200 mb-2">
                  <span className="flex items-center gap-1.5">
                    <Database className="w-3.5 h-3.5 text-cyan-400" />
                    <span>Data Quality &amp; Foundation Metrics</span>
                  </span>
                  <span className="text-[10px] font-mono text-emerald-400 font-bold">Verified Feed</span>
                </div>

                <div className="grid grid-cols-3 gap-2">
                  <div className="p-2.5 rounded-lg bg-[#16181D] border border-white/5 text-center">
                    <div className="text-[10px] text-slate-400 uppercase font-semibold">Data Quality</div>
                    <div className="text-lg font-bold text-white font-mono mt-0.5">
                      {methodology.dataQualityScore}%
                    </div>
                    <div className="text-[9px] text-slate-500">Completeness</div>
                  </div>

                  <div className="p-2.5 rounded-lg bg-[#16181D] border border-white/5 text-center">
                    <div className="text-[10px] text-slate-400 uppercase font-semibold">Evidence</div>
                    <div className="text-lg font-bold text-emerald-400 font-mono mt-0.5">
                      {methodology.evidenceStrength}
                    </div>
                    <div className="text-[9px] text-slate-500">Multi-Source</div>
                  </div>

                  <div className="p-2.5 rounded-lg bg-[#16181D] border border-white/5 text-center">
                    <div className="text-[10px] text-slate-400 uppercase font-semibold">Hist. Coverage</div>
                    <div className="text-lg font-bold text-cyan-400 font-mono mt-0.5">
                      {methodology.historicalCoverage}%
                    </div>
                    <div className="text-[9px] text-slate-500">90D Baseline</div>
                  </div>
                </div>
              </div>

              <div className="text-[11px] text-slate-400 flex items-center justify-between pt-2 border-t border-white/5">
                <span>Tenant Isolation: <strong className="text-slate-300">Active</strong></span>
                <span className="font-mono text-blue-400">{methodology.orgRecordsAnalyzed.toLocaleString()} Records Ingested</span>
              </div>
            </div>
          </div>

          {/* Collapsible Explainer: Probability vs Confidence */}
          {showProbabilityExplainer && (
            <div className="p-4 rounded-xl bg-blue-950/30 border border-blue-500/30 space-y-2 animate-in fade-in duration-150">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold text-blue-300 flex items-center gap-1.5">
                  <Info className="w-4 h-4 text-blue-400" />
                  <span>Understanding the Scientific Distinction: Probability vs. Confidence</span>
                </h4>
                <button
                  onClick={() => setShowProbabilityExplainer(false)}
                  className="text-xs text-slate-400 hover:text-white"
                >
                  Dismiss
                </button>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs text-slate-300 pt-1">
                <div className="p-3 rounded-lg bg-[#16181D]/80 border border-white/5">
                  <strong className="text-blue-300 block mb-1">Probability ({risk.probability}%)</strong>
                  <p className="text-[11px] text-slate-300 leading-relaxed">
                    Represents the <strong>estimated likelihood</strong> of the modeled risk condition or precursor chain manifesting during the forecast period ({methodology.forecastPeriod}), assuming operational tempo continues without preventive intervention.
                  </p>
                </div>
                <div className="p-3 rounded-lg bg-[#16181D]/80 border border-white/5">
                  <strong className="text-emerald-300 block mb-1">Confidence ({risk.confidence}%)</strong>
                  <p className="text-[11px] text-slate-300 leading-relaxed">
                    Represents <strong>confidence in the analytical assessment</strong> based on data quality ({methodology.dataQualityScore}%), empirical evidence strength, sample completeness, and inter-model consensus. It measures statistical reliability—<strong>not</strong> the probability of an accident.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* SECTION 2: PREDICTION METHODOLOGY PARAMETERS TABLE / GRID */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                <Activity className="w-3.5 h-3.5 text-blue-400" />
                <span>Prediction Methodology Parameters</span>
              </h4>
              <span className="text-[11px] font-mono text-slate-400">
                Generated: {methodology.generatedDate}
              </span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
              {/* Prediction Type */}
              <div className="p-3 rounded-lg bg-[#09090B] border border-white/5">
                <div className="text-[10px] text-slate-500 uppercase font-semibold">Prediction Type</div>
                <div className="text-xs font-bold text-white mt-1">
                  {methodology.predictionType}
                </div>
                <div className="text-[10px] font-mono text-blue-400 mt-0.5">Multi-Factor Precursor</div>
              </div>

              {/* Forecast Period */}
              <div className="p-3 rounded-lg bg-[#09090B] border border-white/5">
                <div className="text-[10px] text-slate-500 uppercase font-semibold">Forecast Period</div>
                <div className="text-xs font-bold text-white mt-1">
                  {methodology.forecastPeriod}
                </div>
                <div className="text-[10px] font-mono text-slate-400 mt-0.5">Rolling Lookahead</div>
              </div>

              {/* Data Window */}
              <div className="p-3 rounded-lg bg-[#09090B] border border-white/5">
                <div className="text-[10px] text-slate-500 uppercase font-semibold">Data Window</div>
                <div className="text-xs font-bold text-white mt-1">
                  {methodology.dataWindow}
                </div>
                <div className="text-[10px] font-mono text-slate-400 mt-0.5">Ingested Horizon</div>
              </div>

              {/* Organization Records */}
              <div className="p-3 rounded-lg bg-[#09090B] border border-white/5">
                <div className="text-[10px] text-slate-500 uppercase font-semibold">Organization Records</div>
                <div className="text-xs font-bold text-cyan-400 font-mono mt-1">
                  {methodology.orgRecordsAnalyzed.toLocaleString()}
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5">Field cards &amp; logs</div>
              </div>

              {/* External Knowledge Sources */}
              <div className="p-3 rounded-lg bg-[#09090B] border border-white/5">
                <div className="text-[10px] text-slate-500 uppercase font-semibold">External Sources</div>
                <div className="text-xs font-bold text-purple-400 font-mono mt-1">
                  {methodology.externalKnowledgeSources} Standards
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5">OSHA / HSE UK / API</div>
              </div>

              {/* Contributing Factors */}
              <div className="p-3 rounded-lg bg-[#09090B] border border-white/5">
                <div className="text-[10px] text-slate-500 uppercase font-semibold">Contributing Factors</div>
                <div className="text-xs font-bold text-white font-mono mt-1">
                  {methodology.contributingFactorsCount} Ranked Drivers
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5">Variance weighted</div>
              </div>

              {/* Analytical Models */}
              <div className="p-3 rounded-lg bg-[#09090B] border border-white/5">
                <div className="text-[10px] text-slate-500 uppercase font-semibold">Analytical Models</div>
                <div className="text-xs font-bold text-emerald-400 font-mono mt-1">
                  {methodology.analyticalModelsCount} Ensemble Models
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5">Cross-validated</div>
              </div>

              {/* Model / Method Used */}
              <div className="col-span-2 sm:col-span-3 p-3 rounded-lg bg-[#09090B] border border-white/5">
                <div className="text-[10px] text-slate-500 uppercase font-semibold">Model / Method Used</div>
                <div className="text-xs font-semibold text-slate-200 mt-1 line-clamp-1">
                  {methodology.modelMethod}
                </div>
                <div className="text-[10px] font-mono text-cyan-400 mt-0.5 flex items-center justify-between">
                  <span>Version: {methodology.modelVersion}</span>
                  <span>Bayesian + NLP + Cox Hazard</span>
                </div>
              </div>
            </div>
          </div>

          {/* SECTION 3: CLICKABLE EVIDENCE LINEAGE */}
          <div className="space-y-3 pt-2">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                  <Layers className="w-3.5 h-3.5 text-blue-400" />
                  <span>Interactive Evidence Lineage</span>
                </h4>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  Click any stage in the lineage chain to inspect empirical datasets, mathematical formulas, and underlying assumptions.
                </p>
              </div>
              <span className="text-[10px] font-mono text-cyan-400 px-2 py-0.5 rounded bg-cyan-950/60 border border-cyan-800">
                Clickable Trace Engine
              </span>
            </div>

            {/* Interactive Rail */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 pt-1">
              {LINEAGE_STAGES.map((stage, idx) => (
                <button
                  key={stage.id}
                  onClick={() => onOpenLineageStage(stage.id)}
                  className="p-3 rounded-xl bg-[#09090B] hover:bg-blue-950/30 border border-white/5 hover:border-blue-500/50 transition-all text-left group flex flex-col justify-between min-h-[90px]"
                >
                  <div>
                    <div className="flex items-center justify-between text-[10px] font-mono text-slate-500 mb-1">
                      <span className="font-bold text-blue-400">0{stage.stepNumber}</span>
                      <span className="group-hover:text-blue-300 font-semibold text-[9px] uppercase">
                        Inspect
                      </span>
                    </div>
                    <div className="text-xs font-bold text-white group-hover:text-blue-300 transition-colors flex items-center gap-1">
                      <span>{stage.label}</span>
                      <ArrowRight className="w-3 h-3 text-slate-500 group-hover:text-blue-400 group-hover:translate-x-0.5 transition-transform" />
                    </div>
                  </div>
                  <p className="text-[10px] text-slate-400 mt-1 line-clamp-2 leading-tight">
                    {stage.shortDescription}
                  </p>
                </button>
              ))}
            </div>
          </div>

          {/* SECTION 4: MANDATORY SCIENTIFIC INTERPRETATION WARNING */}
          <div className="p-4 rounded-xl bg-amber-950/20 border border-amber-500/30 flex items-start gap-3 text-amber-200">
            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <span className="text-xs font-bold text-amber-300 uppercase tracking-wide">
                Scientific Interpretation Warning
              </span>
              <p className="text-xs text-amber-200/90 leading-relaxed font-medium">
                Predictions are analytical risk indicators, not guarantees that an incident will occur. They should support—not replace—professional HSE judgement.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
