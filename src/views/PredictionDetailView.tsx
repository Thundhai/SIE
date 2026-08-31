import React, { useState } from 'react';
import { 
  ArrowLeft, 
  BrainCircuit, 
  AlertTriangle, 
  CheckCircle2, 
  TrendingUp, 
  FileText, 
  ExternalLink, 
  ShieldAlert, 
  Sparkles,
  ArrowRight,
  Clock,
  Layers,
  BarChart2,
  Sliders,
  ChevronDown,
  Info,
  Database,
  HelpCircle,
  Activity,
  ShieldCheck
} from 'lucide-react';
import { 
  ResponsiveContainer, 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  Tooltip, 
  CartesianGrid, 
  Legend 
} from 'recharts';
import { EmergingRisk, LineageStageId } from '../types';
import { HISTORICAL_COMPARISON_DATA } from '../mockData';
import { PredictionMethodologyCard } from '../components/PredictionMethodologyCard';
import { EvidenceLineageModal } from '../components/EvidenceLineageModal';
import { getRiskMethodology } from '../utils/methodologyUtils';

interface PredictionDetailViewProps {
  risk: EmergingRisk;
  allRisks: EmergingRisk[];
  onSelectOtherRisk: (riskId: string) => void;
  onBack: () => void;
  onOpenEvidence: (evidence: any) => void;
  onNavigateToInterventions: () => void;
}

export const PredictionDetailView: React.FC<PredictionDetailViewProps> = ({
  risk,
  allRisks,
  onSelectOtherRisk,
  onBack,
  onOpenEvidence,
  onNavigateToInterventions
}) => {
  const [activeTab, setActiveTab] = useState<'causal' | 'historical' | 'factors' | 'evidence'>('causal');
  const [isLineageModalOpen, setIsLineageModalOpen] = useState(false);
  const [selectedLineageStage, setSelectedLineageStage] = useState<LineageStageId>('prediction');

  const methodology = getRiskMethodology(risk);

  const handleOpenLineageStage = (stageId: LineageStageId) => {
    setSelectedLineageStage(stageId);
    setIsLineageModalOpen(true);
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-200">
      {/* Top Breadcrumb & Risk Switcher */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-4">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
            title="Back to Intelligence Center"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <span>Intelligence Center</span>
              <span>/</span>
              <span className="text-slate-300 font-semibold">Emerging Risk Analysis</span>
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-amber-950 text-amber-300 border border-amber-800 font-bold">
                DEMO
              </span>
            </div>
            <h1 className="text-xl sm:text-2xl font-bold text-white tracking-tight mt-0.5">
              {risk.category} Analysis
            </h1>
          </div>
        </div>

        {/* Switch Risk Dropdown & Lineage Trigger */}
        <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap">
          <button
            onClick={() => handleOpenLineageStage('prediction')}
            className="px-3 py-1.5 rounded-lg bg-blue-600/10 hover:bg-blue-600/20 border border-blue-500/30 text-blue-300 text-xs font-semibold transition-colors flex items-center gap-1.5"
          >
            <Layers className="w-3.5 h-3.5 text-blue-400" />
            <span>Trace Lineage</span>
          </button>

          <div className="flex items-center gap-1.5">
            <span className="text-xs text-slate-400">Target Risk:</span>
            <select
              value={risk.id}
              onChange={(e) => onSelectOtherRisk(e.target.value)}
              className="bg-slate-900 border border-slate-700 text-slate-200 text-xs font-semibold rounded-lg px-3 py-1.5 focus:outline-none focus:border-cyan-500"
            >
              {allRisks.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.category} ({r.probability}% Prob)
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Hero Prediction Summary Card */}
      <div className="p-6 rounded-xl bg-slate-900/90 border border-slate-800 shadow-xl relative overflow-hidden space-y-4">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          <div className="space-y-3 max-w-3xl">
            <div className="flex flex-wrap items-center gap-2.5">
              <span className={`text-xs font-mono font-bold px-2.5 py-0.5 rounded uppercase tracking-wider ${
                risk.level === 'High' ? 'bg-rose-950 text-rose-300 border border-rose-800' : 'bg-amber-950 text-amber-300 border border-amber-800'
              }`}>
                Status: {risk.status}
              </span>
              <span className="text-xs text-slate-400 font-mono">ID: {risk.id}</span>
              <span className="text-xs text-slate-400 font-mono">• Location: {risk.location}</span>
              <span className="text-xs text-blue-400 font-mono">• Horizon: {methodology.forecastPeriod}</span>
            </div>

            <h2 className="text-lg sm:text-xl font-bold text-white tracking-tight">
              {risk.title}
            </h2>
            <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
              {risk.summary}
            </p>

            {/* Structured Probability vs Confidence and Data Quality Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 pt-2">
              <div className="p-3 rounded-lg bg-slate-950/70 border border-slate-800">
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">Probability</span>
                <span className="text-2xl font-extrabold text-blue-400 font-mono">{risk.probability}%</span>
                <span className="text-[10px] text-slate-400 block mt-0.5">Est. Likelihood</span>
              </div>

              <div className="p-3 rounded-lg bg-slate-950/70 border border-slate-800">
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">Confidence</span>
                <span className="text-2xl font-extrabold text-emerald-400 font-mono">{risk.confidence}%</span>
                <span className="text-[10px] text-emerald-400/90 block mt-0.5">Model Certainty</span>
              </div>

              <div className="p-3 rounded-lg bg-slate-950/70 border border-slate-800">
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">Data Quality</span>
                <span className="text-2xl font-extrabold text-white font-mono">{methodology.dataQualityScore}%</span>
                <span className="text-[10px] text-slate-400 block mt-0.5">High Integrity</span>
              </div>

              <div className="p-3 rounded-lg bg-slate-950/70 border border-slate-800">
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">Evidence Strength</span>
                <span className="text-lg font-extrabold text-purple-300 font-mono mt-1 block">{methodology.evidenceStrength}</span>
                <span className="text-[10px] text-slate-400 block mt-0.5">{methodology.externalKnowledgeSources} Sources</span>
              </div>

              <div className="p-3 rounded-lg bg-slate-950/70 border border-slate-800 col-span-2 sm:col-span-1">
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">Hist. Coverage</span>
                <span className="text-2xl font-extrabold text-cyan-400 font-mono">{methodology.historicalCoverage}%</span>
                <span className="text-[10px] text-slate-400 block mt-0.5">90D Baseline</span>
              </div>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row lg:flex-col gap-2.5 shrink-0">
            <button
              onClick={onNavigateToInterventions}
              className="px-5 py-2.5 rounded-lg bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 text-white text-xs font-semibold shadow-lg shadow-amber-900/30 transition-all flex items-center justify-center gap-2"
            >
              <ShieldAlert className="w-4 h-4" />
              <span>Generate Safety Intervention</span>
            </button>
            <button
              onClick={() => handleOpenLineageStage('prediction')}
              className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-700 transition-colors flex items-center justify-center gap-2"
            >
              <Activity className="w-3.5 h-3.5 text-cyan-400" />
              <span>Inspect Full Evidence Lineage</span>
            </button>
          </div>
        </div>

        {/* Interpretation Warning Banner */}
        <div className="p-3.5 rounded-lg bg-amber-950/25 border border-amber-500/30 flex items-start gap-2.5 text-amber-200 text-xs">
          <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
          <p className="leading-relaxed">
            <strong>Interpretation Notice:</strong> Predictions are analytical risk indicators, not guarantees that an incident will occur. They should support—not replace—professional HSE judgement.
          </p>
        </div>
      </div>

      {/* DEDICATED PREDICTION METHODOLOGY & EVIDENCE LINEAGE SECTION */}
      <PredictionMethodologyCard
        risk={risk}
        onOpenLineageStage={handleOpenLineageStage}
      />

      {/* SECTION 1: Why SIE Identified This Risk (Causal Factor Diagram) */}
      <div className="p-6 rounded-xl bg-slate-900/90 border border-slate-800 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <BrainCircuit className="w-4 h-4 text-cyan-400" />
              <span>Why SIE Identified This Risk (Causal Factor Chain)</span>
            </h3>
            <p className="text-[11px] text-slate-400">Step-by-step causal escalation derived from multi-layer data synthesis</p>
          </div>
          <button 
            onClick={() => handleOpenLineageStage('analytical-method')}
            className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800 hover:bg-cyan-900 transition-colors"
          >
            Automated Causal Graph • Inspect Algorithm
          </button>
        </div>

        {/* Visual Causal Flow Diagram */}
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3 pt-2">
          {risk.causalChain.map((node, index) => (
            <div key={node.step} className="relative flex flex-col">
              <div 
                onClick={() => handleOpenLineageStage(index === 0 ? 'prediction' : index === 1 ? 'risk-factors' : index === 2 ? 'org-evidence' : index === 3 ? 'external-evidence' : 'recommendation')}
                className="p-4 rounded-lg bg-slate-950/80 border border-slate-800 hover:border-cyan-600/50 cursor-pointer transition-all flex-1 flex flex-col justify-between group"
              >
                <div>
                  <div className="flex items-center justify-between text-[10px] font-mono text-slate-500 mb-1.5">
                    <span className="px-1.5 py-0.2 rounded bg-slate-900 text-cyan-400 border border-slate-800 font-bold">
                      STAGE {node.step}
                    </span>
                    {node.metricChange && (
                      <span className="text-rose-400 font-bold">{node.metricChange}</span>
                    )}
                  </div>
                  <h4 className="text-xs font-bold text-slate-100 group-hover:text-cyan-300 transition-colors">
                    {node.title}
                  </h4>
                  <p className="text-[11px] text-slate-400 mt-1.5 leading-relaxed">
                    {node.description}
                  </p>
                </div>
                <div className="mt-2 text-[9px] font-mono text-cyan-400 group-hover:underline">
                  Click to trace lineage &rarr;
                </div>
              </div>

              {/* Arrow Connector on desktop */}
              {index < risk.causalChain.length - 1 && (
                <div className="hidden md:flex absolute -right-2.5 top-1/2 -translate-y-1/2 z-10 w-5 h-5 rounded-full bg-slate-900 border border-slate-700 items-center justify-center text-slate-400">
                  <ArrowRight className="w-3 h-3" />
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* SECTION 2 & 3: Historical Pattern Comparison & Ranked Contributing Factors */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Historical Pattern Chart (7 cols) */}
        <div className="lg:col-span-7 p-6 rounded-xl bg-slate-900/90 border border-slate-800 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2">
              <div>
                <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                  <BarChart2 className="w-4 h-4 text-cyan-400" />
                  <span>Historical Pattern Comparison</span>
                </h3>
                <p className="text-[11px] text-slate-400">Comparison with similar operational surge campaigns in past projects</p>
              </div>
              <div className="text-[10px] font-mono text-slate-400 px-2 py-0.5 rounded bg-slate-800 border border-slate-700">
                4 Project Benchmarks
              </div>
            </div>

            <div className="h-64 w-full mt-4">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={HISTORICAL_COMPARISON_DATA} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="period" stroke="#64748b" fontSize={10} tickLine={false} />
                  <YAxis domain={[0, 100]} stroke="#64748b" fontSize={11} tickLine={false} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '8px', fontSize: '12px', color: '#f8fafc' }}
                  />
                  <Legend wrapperStyle={{ fontSize: '11px', paddingTop: '8px' }} />
                  <Bar dataKey="riskScore" name="Predictive Risk Score" fill="#38bdf8" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="observations" name="Unsafe Observations" fill="#f43f5e" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="nearMisses" name="Near Misses" fill="#f59e0b" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="mt-3 pt-2 border-t border-slate-800/80 text-[11px] text-slate-400 flex items-center justify-between">
            <span>Pattern match: Current tempo closely tracks Q4 2025 pre-incident trajectory</span>
            <span className="font-mono text-cyan-400 font-semibold">91% Statistical Correlation</span>
          </div>
        </div>

        {/* Contributing Factors (5 cols) */}
        <div className="lg:col-span-5 p-6 rounded-xl bg-slate-900/90 border border-slate-800 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-1">
              <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                <Sliders className="w-4 h-4 text-cyan-400" />
                <span>Ranked Contributing Factors</span>
              </h3>
              <button
                onClick={() => handleOpenLineageStage('risk-factors')}
                className="text-[10px] font-mono text-cyan-400 hover:underline"
              >
                Inspect Weights
              </button>
            </div>
            <p className="text-[11px] text-slate-400 mb-4">Calculated percentage impact on composite risk score</p>

            <div className="space-y-3">
              {risk.contributingFactors.map((factor) => (
                <div key={factor.name} className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="font-semibold text-slate-200">{factor.name}</span>
                    <span className="font-mono font-bold text-cyan-400">{factor.percentage}%</span>
                  </div>
                  {/* Progress Bar */}
                  <div className="w-full h-1.5 rounded-full bg-slate-800 overflow-hidden mb-1.5">
                    <div
                      className={`h-full rounded-full ${
                        factor.impact === 'High' ? 'bg-rose-500' : factor.impact === 'Medium' ? 'bg-amber-500' : 'bg-cyan-500'
                      }`}
                      style={{ width: `${factor.percentage}%` }}
                    />
                  </div>
                  <p className="text-[11px] text-slate-400 leading-snug">{factor.description}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-slate-800/80 text-[11px] text-slate-400 flex items-center justify-between">
            <span>Total Variance Accounted</span>
            <span className="font-mono text-emerald-400 font-semibold">100% Normalized</span>
          </div>
        </div>
      </div>

      {/* SECTION 4: Organization Evidence */}
      <div className="p-6 rounded-xl bg-slate-900/90 border border-slate-800 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                <FileText className="w-4 h-4 text-cyan-400" />
                <span>Organization Evidence ({risk.organizationEvidence.length} Ingested Records)</span>
              </h3>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-950/80 text-amber-300 border border-amber-800 font-bold">
                DEMO / SIMULATED
              </span>
            </div>
            <p className="text-[11px] text-slate-400">Internal operational telemetry, observations, near-misses, and permit records driving this risk</p>
          </div>
          <button
            onClick={() => handleOpenLineageStage('org-evidence')}
            className="text-[10px] font-mono px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors shrink-0"
          >
            Lineage Trace • Org Records
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {risk.organizationEvidence.map((ev) => (
            <div
              key={ev.id}
              onClick={() => onOpenEvidence(ev)}
              className="p-4 rounded-xl bg-slate-950/80 hover:bg-slate-850 border border-slate-800 hover:border-cyan-500/50 cursor-pointer transition-all flex flex-col justify-between group"
            >
              <div>
                <div className="flex items-center justify-between text-[10px] font-mono text-slate-400 border-b border-slate-800/80 pb-2">
                  <div className="flex items-center gap-1.5">
                    <span className="font-bold text-cyan-400">{ev.id}</span>
                    <span className="text-slate-500">•</span>
                    <span className="text-slate-300">{ev.type}</span>
                  </div>
                  <span className={`px-2 py-0.5 rounded font-bold ${
                    ev.severity === 'High' || ev.severity === 'Critical' 
                      ? 'bg-rose-950 text-rose-300 border border-rose-800' 
                      : 'bg-amber-950 text-amber-300 border border-amber-800'
                  }`}>
                    {ev.severity} Severity
                  </span>
                </div>

                <h4 className="text-xs font-bold text-slate-100 mt-2.5 group-hover:text-cyan-300 transition-colors line-clamp-1">
                  {ev.title}
                </h4>

                <div className="grid grid-cols-2 gap-1.5 mt-2.5 text-[10px] font-mono text-slate-400 bg-slate-900/60 p-2 rounded-lg border border-slate-800/50">
                  <div>
                    <span className="text-slate-500 block text-[9px] uppercase">Site / Location</span>
                    <span className="text-slate-300 truncate block">{ev.site || 'Lagos Operations'}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[9px] uppercase">Activity</span>
                    <span className="text-slate-300 truncate block">{ev.activity || 'Lifting Operation'}</span>
                  </div>
                  <div className="col-span-2 pt-1 border-t border-slate-800/40 flex items-center justify-between">
                    <span className="text-slate-500 text-[9px]">Source: {ev.sourceSystem || 'Intelex HSE'}</span>
                    <span className="text-emerald-400 text-[9px] font-bold">{ev.status || 'Active'}</span>
                  </div>
                </div>

                <p className="text-[11px] text-slate-300 mt-2 line-clamp-2 leading-relaxed">
                  {ev.details}
                </p>
              </div>

              <div className="mt-3 pt-2.5 border-t border-slate-800/80 flex items-center justify-between text-[10px] text-slate-500 font-mono">
                <span>{ev.date}</span>
                <span className="text-cyan-400 flex items-center gap-1 group-hover:underline">
                  <span>Provenance Record</span>
                  <ExternalLink className="w-2.5 h-2.5" />
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* SECTION 5: External Verified Evidence */}
      <div className="p-6 rounded-xl bg-slate-900/90 border border-slate-800 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-purple-400" />
                <span>External Verified Knowledge Evidence ({risk.externalEvidence.length} Standards)</span>
              </h3>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-950/80 text-amber-300 border border-amber-800 font-bold">
                DEMO / SIMULATED
              </span>
            </div>
            <p className="text-[11px] text-slate-400">International regulatory frameworks, approved codes of practice, and empirical benchmarks</p>
          </div>
          <button
            onClick={() => handleOpenLineageStage('external-evidence')}
            className="text-[10px] font-mono px-2.5 py-1 rounded bg-purple-950 hover:bg-purple-900 text-purple-300 border border-purple-800 transition-colors shrink-0"
          >
            Lineage Trace • External Standards
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {risk.externalEvidence.map((ext) => (
            <div
              key={ext.id}
              onClick={() => onOpenEvidence(ext)}
              className="p-4 rounded-xl bg-slate-950/80 hover:bg-slate-850 border border-slate-800 hover:border-purple-500/50 cursor-pointer transition-all flex flex-col justify-between group"
            >
              <div>
                <div className="flex items-center justify-between text-[10px] font-mono text-slate-400 border-b border-slate-800/80 pb-2">
                  <span className="font-bold text-purple-300">{ext.publisher}</span>
                  <span className="text-emerald-400 font-bold">{ext.reliability} Reliability</span>
                </div>

                <h4 className="text-xs font-bold text-slate-100 mt-2.5 group-hover:text-purple-300 transition-colors line-clamp-2">
                  {ext.documentTitle}
                </h4>

                <div className="grid grid-cols-2 gap-1.5 mt-2.5 text-[10px] font-mono text-slate-400 bg-slate-900/60 p-2 rounded-lg border border-slate-800/50">
                  <div>
                    <span className="text-slate-500 block text-[9px] uppercase">Code / Ref</span>
                    <span className="text-cyan-300 truncate block">{ext.code}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[9px] uppercase">Jurisdiction</span>
                    <span className="text-slate-300 truncate block">{ext.jurisdiction}</span>
                  </div>
                  <div className="col-span-2 pt-1 border-t border-slate-800/40 flex items-center justify-between">
                    <span className="text-slate-500 text-[9px]">Topic: {ext.topic}</span>
                    <span className="text-slate-400 text-[9px]">{ext.publicationDate}</span>
                  </div>
                </div>

                <div className="p-2.5 rounded-lg bg-slate-900/90 border border-slate-800/80 mt-2.5 text-[11px] text-purple-100/90 italic leading-relaxed">
                  &ldquo;{ext.keyExcerpt}&rdquo;
                </div>
              </div>

              <div className="mt-3 pt-2.5 border-t border-slate-800/80 flex items-center justify-between text-[10px] text-slate-500 font-mono">
                <span>{ext.sourceReference || ext.code}</span>
                <span className="text-purple-400 flex items-center gap-1 group-hover:underline">
                  <span>Inspect Norm</span>
                  <ExternalLink className="w-2.5 h-2.5" />
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* SECTION 6: Analytical Evidence & Baseline Deviation */}
      {risk.analyticalEvidence && (
        <div className="p-6 rounded-xl bg-slate-900/90 border border-slate-800 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                  <Activity className="w-4 h-4 text-cyan-400" />
                  <span>Analytical Evidence &amp; Statistical Baseline Deviation</span>
                </h3>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-950/80 text-amber-300 border border-amber-800 font-bold">
                  DEMO / SIMULATED
                </span>
              </div>
              <p className="text-[11px] text-slate-400">Quantitative trend metrics, historical baselines, and mathematical model techniques</p>
            </div>
            <button
              onClick={() => onOpenEvidence(risk.analyticalEvidence)}
              className="text-[10px] font-mono px-2.5 py-1 rounded bg-cyan-950 hover:bg-cyan-900 text-cyan-300 border border-cyan-800 transition-colors shrink-0"
            >
              Inspect Analytical Matrix
            </button>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-3.5 rounded-xl bg-slate-950/80 border border-slate-800">
              <span className="text-slate-400 text-[10px] font-mono uppercase block">Calculated Trend</span>
              <span className="text-rose-400 font-bold text-sm font-mono mt-1 block flex items-center gap-1">
                <TrendingUp className="w-3.5 h-3.5" />
                {risk.analyticalEvidence.trend}
              </span>
            </div>

            <div className="p-3.5 rounded-xl bg-slate-950/80 border border-slate-800">
              <span className="text-slate-400 text-[10px] font-mono uppercase block">Historical Baseline</span>
              <span className="text-slate-200 font-semibold text-xs mt-1 block">
                {risk.analyticalEvidence.baseline}
              </span>
            </div>

            <div className="p-3.5 rounded-xl bg-slate-950/80 border border-slate-800">
              <span className="text-slate-400 text-[10px] font-mono uppercase block">Current Observed Value</span>
              <span className="text-cyan-300 font-bold text-xs mt-1 block">
                {risk.analyticalEvidence.currentValue}
              </span>
            </div>

            <div className="p-3.5 rounded-xl bg-slate-950/80 border border-slate-800">
              <span className="text-slate-400 text-[10px] font-mono uppercase block">Statistical Deviation</span>
              <span className="text-amber-300 font-bold text-xs mt-1 block font-mono">
                {risk.analyticalEvidence.deviation}
              </span>
            </div>
          </div>

          <div className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800/80 text-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <span className="text-slate-400 font-mono text-[10px] uppercase">Historical Benchmark Pattern:</span>
              <p className="text-slate-200 mt-0.5">{risk.analyticalEvidence.historicalComparison}</p>
            </div>
            <div className="text-right shrink-0">
              <span className="text-[10px] font-mono text-cyan-400 block">{risk.analyticalEvidence.modelTechnique}</span>
              <span className="text-[10px] font-mono text-emerald-400">{risk.analyticalEvidence.confidenceInterval}</span>
            </div>
          </div>
        </div>
      )}

      {/* SECTION 7: AI Synthesis Reasoning */}
      <div className="p-6 rounded-xl bg-gradient-to-r from-slate-900 via-slate-900 to-cyan-950/40 border border-cyan-800/60 space-y-2.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-bold text-white">AI Synthesis Reasoning Explanation</h3>
          </div>
          <button
            onClick={() => handleOpenLineageStage('analytical-method')}
            className="text-[10px] font-mono text-cyan-300 hover:underline flex items-center gap-1"
          >
            <span>Model Formulation</span>
            <ArrowRight className="w-3 h-3" />
          </button>
        </div>
        <p className="text-xs sm:text-sm text-slate-200 leading-relaxed">
          {risk.aiReasoning}
        </p>
        <div className="pt-2 text-[11px] text-slate-400 font-mono flex items-center justify-between">
          <span>Engine Model: {methodology.modelVersion}</span>
          <span className="text-cyan-400">Zero Black-Box Processing • Full Lineage Verifiable</span>
        </div>
      </div>

      {/* Interactive Evidence Lineage Modal */}
      <EvidenceLineageModal
        isOpen={isLineageModalOpen}
        onClose={() => setIsLineageModalOpen(false)}
        risk={risk}
        initialStageId={selectedLineageStage}
        onNavigateToInterventions={onNavigateToInterventions}
        onOpenEvidenceRecord={onOpenEvidence}
      />
    </div>
  );
};
