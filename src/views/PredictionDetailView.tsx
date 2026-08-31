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
  ChevronDown
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
import { EmergingRisk } from '../types';
import { HISTORICAL_COMPARISON_DATA } from '../mockData';

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
            </div>
            <h1 className="text-xl sm:text-2xl font-bold text-white tracking-tight mt-0.5">
              {risk.category} Analysis
            </h1>
          </div>
        </div>

        {/* Switch Risk Dropdown */}
        <div className="flex items-center gap-2">
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

      {/* Hero Prediction Summary Card */}
      <div className="p-6 rounded-xl bg-slate-900/90 border border-slate-800 shadow-xl relative overflow-hidden">
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
            </div>

            <h2 className="text-lg sm:text-xl font-bold text-white tracking-tight">
              {risk.title}
            </h2>
            <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
              {risk.summary}
            </p>

            <div className="flex flex-wrap items-center gap-6 pt-1 text-xs">
              <div>
                <span className="text-slate-400 block text-[10px] uppercase">Probability</span>
                <span className="text-2xl font-extrabold text-rose-400 font-mono">{risk.probability}%</span>
              </div>
              <div>
                <span className="text-slate-400 block text-[10px] uppercase">Confidence</span>
                <span className="text-2xl font-extrabold text-emerald-400 font-mono">{risk.confidence}%</span>
              </div>
              <div>
                <span className="text-slate-400 block text-[10px] uppercase">Trajectory</span>
                <span className="text-base font-bold text-slate-200 font-mono mt-1 block">
                  {risk.trajectory} (+{risk.trendPercentage}%)
                </span>
              </div>
              <div>
                <span className="text-slate-400 block text-[10px] uppercase">Evidence Base</span>
                <span className="text-xs font-mono text-cyan-300 mt-1.5 block">
                  {risk.orgRecordsCount} Org Records • {risk.externalSourcesCount} Standards
                </span>
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
          </div>
        </div>
      </div>

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
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800">
            Automated Causal Graph
          </span>
        </div>

        {/* Visual Causal Flow Diagram */}
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3 pt-2">
          {risk.causalChain.map((node, index) => (
            <div key={node.step} className="relative flex flex-col">
              <div className="p-4 rounded-lg bg-slate-950/80 border border-slate-800 hover:border-cyan-600/50 transition-all flex-1 flex flex-col justify-between group">
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
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <Sliders className="w-4 h-4 text-cyan-400" />
              <span>Ranked Contributing Factors</span>
            </h3>
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
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <FileText className="w-4 h-4 text-cyan-400" />
              <span>Organization Evidence ({risk.organizationEvidence.length} Key Records)</span>
            </h3>
            <p className="text-[11px] text-slate-400">Internal observations, near misses, and overdue audit findings driving this risk</p>
          </div>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
            Source: Safelytic Core Ingestion
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
          {risk.organizationEvidence.map((ev) => (
            <div
              key={ev.id}
              onClick={() => onOpenEvidence(ev)}
              className="p-3.5 rounded-lg bg-slate-950/70 hover:bg-slate-800/60 border border-slate-800 hover:border-cyan-500/50 cursor-pointer transition-all flex flex-col justify-between group"
            >
              <div>
                <div className="flex items-center justify-between text-[10px] font-mono text-slate-400">
                  <span className="font-bold text-cyan-400">{ev.id}</span>
                  <span className={`px-1.5 py-0.2 rounded ${
                    ev.severity === 'High' ? 'bg-rose-950 text-rose-300 border border-rose-800' : 'bg-amber-950 text-amber-300 border border-amber-800'
                  }`}>
                    {ev.severity}
                  </span>
                </div>
                <h4 className="text-xs font-semibold text-slate-100 mt-2 group-hover:text-cyan-300 transition-colors line-clamp-2">
                  {ev.title}
                </h4>
                <p className="text-[11px] text-slate-400 mt-1 line-clamp-3 leading-relaxed">
                  {ev.details}
                </p>
              </div>

              <div className="mt-3 pt-2 border-t border-slate-800/80 flex items-center justify-between text-[10px] text-slate-500">
                <span>{ev.date}</span>
                <span className="font-mono text-cyan-400 flex items-center gap-1 group-hover:underline">
                  <span>Inspect</span>
                  <ExternalLink className="w-2.5 h-2.5" />
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* SECTION 5: External Verified Evidence */}
      <div className="p-6 rounded-xl bg-slate-900/90 border border-slate-800 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-purple-400" />
              <span>External Verified Knowledge Evidence ({risk.externalEvidence.length} Citations)</span>
            </h3>
            <p className="text-[11px] text-slate-400">Regulatory standards and research benchmarks grounding the predictive model (Demo / Simulated Sources)</p>
          </div>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-950 text-purple-300 border border-purple-800">
            External Standards Verified
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {risk.externalEvidence.map((ext) => (
            <div
              key={ext.id}
              onClick={() => onOpenEvidence(ext)}
              className="p-4 rounded-lg bg-slate-950/70 hover:bg-slate-800/60 border border-slate-800 hover:border-purple-500/50 cursor-pointer transition-all flex flex-col justify-between group"
            >
              <div>
                <div className="flex items-center justify-between text-[10px] font-mono text-slate-400">
                  <span className="font-semibold text-purple-300">{ext.publisher}</span>
                  <span className="text-emerald-400 font-bold">{ext.reliability} Reliability</span>
                </div>
                <h4 className="text-xs font-bold text-slate-100 mt-2 group-hover:text-purple-300 transition-colors">
                  {ext.documentTitle}
                </h4>
                <div className="text-[10px] font-mono text-slate-500 mt-0.5">{ext.code} • {ext.publicationDate}</div>
                <div className="p-2.5 rounded bg-slate-900/90 border border-slate-800 mt-2 text-[11px] text-slate-300 italic leading-relaxed">
                  &ldquo;{ext.keyExcerpt}&rdquo;
                </div>
              </div>

              <div className="mt-3 pt-2 border-t border-slate-800/80 flex items-center justify-between text-[10px] text-slate-500">
                <span>{ext.jurisdiction}</span>
                <span className="text-purple-400 font-mono flex items-center gap-1 group-hover:underline">
                  <span>View Rule Details</span>
                  <ExternalLink className="w-2.5 h-2.5" />
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* SECTION 6: AI Reasoning */}
      <div className="p-6 rounded-xl bg-gradient-to-r from-slate-900 via-slate-900 to-cyan-950/40 border border-cyan-800/60 space-y-2.5">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-cyan-400" />
          <h3 className="text-sm font-bold text-white">AI Synthesis Reasoning Explanation</h3>
        </div>
        <p className="text-xs sm:text-sm text-slate-200 leading-relaxed">
          {risk.aiReasoning}
        </p>
        <div className="pt-2 text-[11px] text-slate-400 font-mono flex items-center justify-between">
          <span>Engine Model: Causal Synthesis Graph v4.6</span>
          <span className="text-cyan-400">Zero Black-Box Processing • Full Lineage Verifiable</span>
        </div>
      </div>
    </div>
  );
};
