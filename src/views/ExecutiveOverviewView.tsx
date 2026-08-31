import React, { useState } from 'react';
import { 
  AlertTriangle, 
  TrendingUp, 
  TrendingDown,
  ShieldAlert, 
  CheckCircle2, 
  Clock, 
  Sparkles, 
  ArrowRight, 
  FileText, 
  ExternalLink,
  Activity,
  Layers,
  ChevronRight,
  Info,
  RotateCcw,
  ShieldCheck,
  Search,
  UserCheck,
  Calendar,
  AlertOctagon,
  BrainCircuit,
  Eye,
  CheckSquare
} from 'lucide-react';
import { 
  ResponsiveContainer, 
  LineChart, 
  Line, 
  XAxis, 
  YAxis, 
  Tooltip, 
  CartesianGrid, 
  Legend 
} from 'recharts';
import { EmergingRisk, GlobalFilterState, ManagementAttentionItem } from '../types';
import { RISK_TREND_90_DAYS, MANAGEMENT_ATTENTION_ITEMS } from '../mockData';
import { GlobalFilterBar } from '../components/GlobalFilterBar';
import { filterRisks, filterTrendData, getPresetDateRange, INITIAL_FILTER_STATE } from '../utils/filterUtils';

interface ExecutiveOverviewViewProps {
  risks: EmergingRisk[];
  globalFilter?: GlobalFilterState;
  onFilterChange?: (filter: GlobalFilterState) => void;
  onSelectRisk: (riskId: string) => void;
  onOpenEvidence: (evidence: any) => void;
  onNavigateToIntelligence: () => void;
  onNavigateToInterventions: () => void;
  onNavigateToAssistant: (prompt?: string) => void;
  currentSite: string;
}

export const ExecutiveOverviewView: React.FC<ExecutiveOverviewViewProps> = ({
  risks,
  globalFilter = INITIAL_FILTER_STATE,
  onFilterChange = (_f?: GlobalFilterState) => {},
  onSelectRisk,
  onOpenEvidence,
  onNavigateToIntelligence,
  onNavigateToInterventions,
  onNavigateToAssistant,
  currentSite
}) => {
  const [acknowledgedItems, setAcknowledgedItems] = useState<Record<string, boolean>>({});
  const [selectedRiskFocus, setSelectedRiskFocus] = useState<string | null>(null);

  // Dynamic real-time filtered risks
  const filteredRisks = filterRisks(risks, globalFilter);
  const filteredTrendData = filterTrendData(RISK_TREND_90_DAYS, globalFilter);
  
  // Primary featured risk for the brief (or user selected focus)
  const activeFocusRisk = selectedRiskFocus 
    ? filteredRisks.find(r => r.id === selectedRiskFocus) || filteredRisks[0] || risks[0]
    : filteredRisks[0] || risks[0];

  const availableCategoriesList = Array.from(new Set(risks.map(r => r.category)));

  // Recalculated dynamic status metrics
  const highAndCriticalCount = filteredRisks.filter(r => r.level === 'High' || r.level === 'Critical').length;
  const criticalOnlyCount = filteredRisks.filter(r => r.probability >= 70 || r.level === 'Critical').length;
  
  // Intelligence status logic
  const overallStatus = criticalOnlyCount >= 2 
    ? { title: 'Elevated Hazard Horizon', color: 'text-red-400', bg: 'bg-red-950/40', border: 'border-red-500/40', badge: 'Active Precursor Surge' }
    : highAndCriticalCount >= 1 
    ? { title: 'Moderate Risk Drift', color: 'text-amber-400', bg: 'bg-amber-950/40', border: 'border-amber-500/40', badge: 'Targeted Attention' }
    : { title: 'Controlled Baseline', color: 'text-emerald-400', bg: 'bg-emerald-950/40', border: 'border-emerald-500/40', badge: 'Stable Controls' };

  const dateRangeInfo = getPresetDateRange(globalFilter.dateRangePreset);

  const toggleAcknowledge = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setAcknowledgedItems(prev => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-200">
      
      {/* 1. Header & Quick Actions */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-white/5 pb-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl sm:text-2xl font-bold text-white tracking-tight">
              Executive Safety Intelligence Overview
            </h1>
            <span className="text-[11px] font-mono px-2.5 py-0.5 rounded-full bg-blue-600/15 text-blue-400 border border-blue-500/30 font-semibold flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse"></span>
              Live Predictive Horizon
            </span>
          </div>
          <p className="text-xs sm:text-sm text-slate-400 mt-1 max-w-3xl leading-relaxed">
            What leadership needs to know right now: emerging risks, causal drivers, executive actions, and verifiable evidence.
          </p>
        </div>

        <div className="flex items-center gap-2.5 shrink-0">
          <button
            onClick={() => onNavigateToAssistant("Summarize the top 3 safety decisions leadership must make today for " + currentSite)}
            className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-md shadow-blue-600/25 transition-all"
          >
            <Sparkles className="w-3.5 h-3.5 text-blue-200" />
            <span>Ask Executive Assistant</span>
          </button>
        </div>
      </div>

      {/* Real-time Global Filter Selectors */}
      <GlobalFilterBar
        filter={globalFilter}
        onChange={onFilterChange}
        totalCount={risks.length}
        filteredCount={filteredRisks.length}
        availableCategories={availableCategoriesList}
        showCategoryFilter={true}
      />

      {/* 2. Executive Safety Intelligence Status (Prominent Top Dashboard) */}
      <div className={`p-4 sm:p-5 rounded-xl border ${overallStatus.border} ${overallStatus.bg} bg-[#16181D]/90 backdrop-blur-sm relative overflow-hidden transition-all shadow-xl`}>
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-white/5 pb-3.5">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-[#09090B] border border-white/10 flex items-center justify-center text-blue-400 shrink-0">
              <BrainCircuit className="w-5 h-5" />
            </div>
            <div>
              <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400 font-semibold flex items-center gap-2">
                <span>Executive Safety Intelligence Status</span>
                <span className="text-slate-500">•</span>
                <span className="text-slate-300 font-normal">{currentSite}</span>
                <span className="text-slate-500">•</span>
                <span className="text-blue-400 font-normal">{dateRangeInfo.label}</span>
              </div>
              <div className="flex items-center gap-2.5 mt-0.5">
                <span className={`text-lg sm:text-xl font-extrabold ${overallStatus.color} tracking-tight`}>
                  {overallStatus.title}
                </span>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-[#09090B] text-slate-300 border border-white/10">
                  {overallStatus.badge}
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs text-slate-400 font-mono">
            <span>Core Focus:</span>
            <span className="text-slate-200 font-semibold">Tandem Lifts • Rigging Audits • Contractor SIMOPS</span>
          </div>
        </div>

        {/* Status Breakdown Grid (6 core executive intelligence indicators) */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 sm:gap-4 mt-3.5">
          {/* Overall Intelligence Status */}
          <div className="p-3 rounded-lg bg-[#09090B]/80 border border-white/5">
            <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
              Overall Status
            </div>
            <div className="mt-1.5 flex items-baseline gap-1.5">
              <span className={`text-base font-bold ${overallStatus.color}`}>
                {criticalOnlyCount >= 2 ? 'Elevated' : 'Monitored'}
              </span>
            </div>
            <div className="text-[10px] text-slate-400 mt-1 flex items-center gap-1">
              <AlertTriangle className="w-2.5 h-2.5 text-amber-400" />
              <span>Precursor Horizon</span>
            </div>
          </div>

          {/* Risk Direction */}
          <div className="p-3 rounded-lg bg-[#09090B]/80 border border-white/5">
            <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
              Risk Direction
            </div>
            <div className="mt-1.5 flex items-baseline gap-1.5">
              <span className="text-base font-bold text-red-400 font-mono flex items-center gap-1">
                <TrendingUp className="w-4 h-4" />
                <span>+14% Surge</span>
              </span>
            </div>
            <div className="text-[10px] text-slate-400 mt-1">
              Deteriorating 30d slope
            </div>
          </div>

          {/* Emerging Risk Count */}
          <div 
            onClick={onNavigateToIntelligence}
            className="p-3 rounded-lg bg-[#09090B]/80 border border-white/5 cursor-pointer hover:border-blue-500/40 transition-colors group"
          >
            <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider flex items-center justify-between">
              <span>Emerging Risks</span>
              <ChevronRight className="w-3 h-3 text-slate-500 group-hover:text-blue-400" />
            </div>
            <div className="mt-1.5 text-xl font-extrabold text-white font-mono">
              {filteredRisks.length}
            </div>
            <div className="text-[10px] text-slate-400 mt-1">
              Active causal forecasts
            </div>
          </div>

          {/* Critical Risk Count */}
          <div className="p-3 rounded-lg bg-[#09090B]/80 border border-red-500/20 bg-red-950/20">
            <div className="text-[10px] font-semibold text-red-300 uppercase tracking-wider">
              Critical Risk Count
            </div>
            <div className="mt-1.5 text-xl font-extrabold text-red-400 font-mono">
              {criticalOnlyCount}
            </div>
            <div className="text-[10px] text-red-300/80 mt-1">
              ≥ 70% Probability
            </div>
          </div>

          {/* Intervention Effectiveness */}
          <div 
            onClick={onNavigateToInterventions}
            className="p-3 rounded-lg bg-[#09090B]/80 border border-white/5 cursor-pointer hover:border-emerald-500/40 transition-colors group"
          >
            <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider flex items-center justify-between">
              <span>Interventions</span>
              <ChevronRight className="w-3 h-3 text-slate-500 group-hover:text-emerald-400" />
            </div>
            <div className="mt-1.5 text-xl font-extrabold text-emerald-400 font-mono">
              84%
            </div>
            <div className="text-[10px] text-slate-400 mt-1">
              Barrier integrity score
            </div>
          </div>

          {/* Data Confidence */}
          <div className="p-3 rounded-lg bg-[#09090B]/80 border border-white/5">
            <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
              Data Confidence
            </div>
            <div className="mt-1.5 text-xl font-extrabold text-blue-400 font-mono">
              91%
            </div>
            <div className="text-[10px] text-slate-400 mt-1">
              1,420 records analyzed
            </div>
          </div>
        </div>
      </div>

      {/* 3. Main Visual: Emerging Risk Landscape */}
      <div className="space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h2 className="text-base sm:text-lg font-bold text-white tracking-tight flex items-center gap-2">
              <Layers className="w-4 h-4 text-blue-400" />
              <span>Emerging Risk Landscape</span>
              <span className="text-xs font-normal text-slate-400">
                (Primary Forecast Visual)
              </span>
            </h2>
            <p className="text-xs text-slate-400">
              Ranked analytical risk horizons with causal drivers, likelihood, model confidence, and verifiable evidence.
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className="text-slate-400">Forecast Horizon:</span>
            <span className="px-2 py-0.5 rounded bg-[#16181D] text-slate-200 border border-white/10 font-mono font-semibold">
              Next 30 Days
            </span>
          </div>
        </div>

        {/* Risk Landscape Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredRisks.slice(0, 6).map((risk) => {
            const isSelected = activeFocusRisk?.id === risk.id;
            return (
              <div
                key={risk.id}
                onClick={() => setSelectedRiskFocus(risk.id)}
                className={`p-4 sm:p-5 rounded-xl border transition-all cursor-pointer relative flex flex-col justify-between ${
                  isSelected
                    ? 'bg-[#181B22] border-blue-500 shadow-lg shadow-blue-500/10 ring-1 ring-blue-500/30'
                    : 'bg-[#16181D] hover:bg-[#1A1D25] border-white/10 hover:border-white/20'
                }`}
              >
                {/* Card Top: Category, Level & Trajectory */}
                <div>
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <div className={`w-2.5 h-2.5 rounded-full ${
                        risk.level === 'Critical' ? 'bg-red-500 shadow-sm shadow-red-500/50 animate-pulse' :
                        risk.level === 'High' ? 'bg-orange-500' :
                        risk.level === 'Moderate' ? 'bg-amber-500' : 'bg-emerald-500'
                      }`} />
                      <span className="text-xs font-bold text-slate-200 uppercase tracking-wider font-mono">
                        {risk.category}
                      </span>
                    </div>

                    <div className="flex items-center gap-1.5">
                      <span className={`text-[10px] font-mono px-2 py-0.5 rounded font-bold ${
                        risk.level === 'Critical'
                          ? 'bg-red-950/70 text-red-300 border border-red-500/70'
                          : risk.level === 'High'
                          ? 'bg-orange-950/70 text-orange-300 border border-orange-500/70'
                          : risk.level === 'Moderate'
                          ? 'bg-amber-950/70 text-amber-300 border border-amber-500/70'
                          : 'bg-emerald-950/70 text-emerald-300 border border-emerald-500/70'
                      }`}>
                        {risk.level}
                      </span>
                      <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded font-semibold flex items-center gap-0.5 ${
                        risk.trajectory === 'Increasing'
                          ? 'bg-red-950/40 text-red-400 border border-red-800/40'
                          : 'bg-emerald-950/40 text-emerald-400 border border-emerald-800/40'
                      }`}>
                        {risk.trajectory === 'Increasing' ? <TrendingUp className="w-2.5 h-2.5" /> : <TrendingDown className="w-2.5 h-2.5" />}
                        {risk.trajectory === 'Increasing' ? `+${risk.trendPercentage}%` : `-${risk.trendPercentage}%`}
                      </span>
                    </div>
                  </div>

                  {/* Title & Location */}
                  <h3 className="text-sm font-bold text-white mt-2.5 line-clamp-1 group-hover:text-blue-300 transition-colors">
                    {risk.title}
                  </h3>
                  <div className="text-[11px] text-slate-400 mt-0.5 flex items-center gap-1.5 font-mono">
                    <span>{risk.location}</span>
                    <span>•</span>
                    <span className="text-slate-500">Forecast: Next 30 Days</span>
                  </div>

                  {/* Primary Driver */}
                  <div className="mt-3 p-2.5 rounded-lg bg-[#09090B] border border-white/5 text-[11px] text-slate-300 leading-relaxed">
                    <span className="font-semibold text-slate-200 block text-[10px] uppercase font-mono tracking-wider text-amber-400 mb-0.5">
                      Primary Driver:
                    </span>
                    <p className="line-clamp-2 text-slate-300">
                      {risk.mainDriver}
                    </p>
                  </div>
                </div>

                {/* Card Bottom: Probability, Confidence, Evidence & Actions */}
                <div className="mt-4 pt-3 border-t border-white/5 space-y-3">
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div className="p-1.5 rounded bg-[#09090B]/60 border border-white/5">
                      <div className="text-[9px] uppercase font-mono text-slate-400">Probability</div>
                      <div className="text-xs font-bold text-red-400 font-mono mt-0.5">
                        {risk.probability}%
                      </div>
                    </div>
                    <div className="p-1.5 rounded bg-[#09090B]/60 border border-white/5">
                      <div className="text-[9px] uppercase font-mono text-slate-400">Confidence</div>
                      <div className="text-xs font-bold text-emerald-400 font-mono mt-0.5">
                        {risk.confidence}%
                      </div>
                    </div>
                    <div className="p-1.5 rounded bg-[#09090B]/60 border border-white/5">
                      <div className="text-[9px] uppercase font-mono text-slate-400">Evidence</div>
                      <div className="text-xs font-bold text-blue-400 font-mono mt-0.5">
                        {risk.orgRecordsCount} Recs
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between gap-2 pt-1">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectRisk(risk.id);
                      }}
                      className="text-xs font-semibold text-blue-400 hover:text-blue-300 flex items-center gap-1 transition-colors"
                    >
                      <span>Investigate Model</span>
                      <ArrowRight className="w-3 h-3" />
                    </button>

                    <div className="flex items-center gap-1.5">
                      {risk.organizationEvidence && risk.organizationEvidence[0] && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onOpenEvidence(risk.organizationEvidence[0]);
                          }}
                          className="px-2 py-1 rounded bg-white/5 hover:bg-white/10 text-[10px] text-slate-300 font-mono border border-white/5 flex items-center gap-1"
                        >
                          <FileText className="w-3 h-3 text-slate-400" />
                          <span>Evidence</span>
                        </button>
                      )}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onNavigateToInterventions();
                        }}
                        className="px-2 py-1 rounded bg-amber-950/40 hover:bg-amber-900/50 text-[10px] text-amber-300 font-semibold border border-amber-800/50 flex items-center gap-1"
                      >
                        <ShieldAlert className="w-3 h-3 text-amber-400" />
                        <span>Action</span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 4. AI Executive Brief (Structured Intelligence Briefing) */}
      <div className="p-5 sm:p-6 rounded-xl bg-[#16181D] border border-blue-500/30 shadow-xl relative overflow-hidden">
        {/* Brief Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-white/10 pb-4">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-blue-600/15 border border-blue-500/30 text-blue-400">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-sm sm:text-base font-bold text-white tracking-tight uppercase font-mono">
                  Executive Safety Intelligence Brief
                </h2>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-blue-950/60 text-blue-300 border border-blue-800/50 font-bold">
                  v4.6.2 Causal Synthesis
                </span>
              </div>
              <p className="text-xs text-slate-400 font-mono">
                Scope: {currentSite} • Focal Domain: {activeFocusRisk.category} ({activeFocusRisk.location})
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => onSelectRisk(activeFocusRisk.id)}
              className="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-sm transition-colors flex items-center gap-1.5"
            >
              <span>View Full Prediction</span>
              <ArrowRight className="w-3 h-3" />
            </button>
          </div>
        </div>

        {/* Structured 6-Section Executive Intelligence Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 mt-5 text-xs">
          
          {/* 1. What Changed? */}
          <div className="p-4 rounded-lg bg-[#09090B] border border-white/5 space-y-2">
            <div className="flex items-center gap-1.5 text-blue-400 font-bold font-mono uppercase text-[11px]">
              <TrendingUp className="w-3.5 h-3.5 text-red-400" />
              <span>What Changed?</span>
            </div>
            <ul className="space-y-1.5 text-slate-300 leading-relaxed list-disc list-inside text-[11px]">
              <li>
                <strong className="text-slate-100">+28% surge in heavy crane lifts</strong> over the past 21 days due to module fabrication deadlines.
              </li>
              <li>
                <strong className="text-red-400">14 unsafe rigging observations</strong> logged (tag line omissions and pinch-point exposures).
              </li>
              <li>
                <strong className="text-amber-400">3 mandatory sling recertification actions</strong> are 12 days overdue in Yard 4.
              </li>
            </ul>
          </div>

          {/* 2. Why It Matters */}
          <div className="p-4 rounded-lg bg-[#09090B] border border-white/5 space-y-2">
            <div className="flex items-center gap-1.5 text-amber-400 font-bold font-mono uppercase text-[11px]">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
              <span>Why It Matters</span>
            </div>
            <p className="text-slate-300 leading-relaxed text-[11px]">
              Tandem and high-tonnage crane operations in high-traffic fabrication zones carry an elevated probability of 
              <strong className="text-red-300"> dropped load or sling parting event ({activeFocusRisk.probability}% likelihood)</strong>, 
              representing a potential catastrophic consequence to personnel and multi-million dollar asset downtime.
            </p>
          </div>

          {/* 3. What Is Driving It? */}
          <div className="p-4 rounded-lg bg-[#09090B] border border-white/5 space-y-2">
            <div className="flex items-center gap-1.5 text-orange-400 font-bold font-mono uppercase text-[11px]">
              <Activity className="w-3.5 h-3.5 text-orange-400" />
              <span>What Is Driving It?</span>
            </div>
            <ul className="space-y-1.5 text-slate-300 leading-relaxed list-disc list-inside text-[11px]">
              <li>Schedule compression leading to simultaneous operations (SIMOPS score 8.4/10).</li>
              <li>Increased subcontractor workforce turnover (+18% new riggers on Pier 2).</li>
              <li>Maintenance inspection backlog on rigging hardware and spreader bars.</li>
            </ul>
          </div>

          {/* 4. What Should Management Do? */}
          <div className="p-4 rounded-lg bg-[#09090B] border border-blue-500/20 bg-blue-950/10 space-y-2">
            <div className="flex items-center gap-1.5 text-emerald-400 font-bold font-mono uppercase text-[11px]">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
              <span>What Should Management Do?</span>
            </div>
            <ul className="space-y-1.5 text-slate-200 leading-relaxed text-[11px]">
              <li className="flex items-start gap-1.5">
                <span className="text-blue-400 font-bold">1.</span>
                <span>Mandate 100% pre-lift rigging inspection & halt tandem lifts in Yard 4 until lift-plan re-validation.</span>
              </li>
              <li className="flex items-start gap-1.5">
                <span className="text-blue-400 font-bold">2.</span>
                <span>Enforce mandatory hands-on verification before issuing rigging permits to 3rd-party crews.</span>
              </li>
              <li className="flex items-start gap-1.5">
                <span className="text-blue-400 font-bold">3.</span>
                <span>Clear the 3 overdue rigging CAPAs within 48 hours.</span>
              </li>
            </ul>
          </div>

          {/* 5. Evidence Base */}
          <div className="p-4 rounded-lg bg-[#09090B] border border-white/5 space-y-2">
            <div className="flex items-center gap-1.5 text-blue-300 font-bold font-mono uppercase text-[11px]">
              <FileText className="w-3.5 h-3.5 text-blue-400" />
              <span>Evidence Base</span>
            </div>
            <p className="text-slate-300 leading-relaxed text-[11px]">
              Grounded in <strong className="text-slate-100">{activeFocusRisk.orgRecordsCount} internal operational records</strong> (14 field reports, 2 high-potential near-misses, 3 overdue audits) correlated against 
              <strong className="text-slate-100"> {activeFocusRisk.externalSourcesCount} verified international standards</strong> (ASME B30.5, OSHA 1926.1400, ISO 45001).
            </p>
          </div>

          {/* 6. Confidence / Limitations */}
          <div className="p-4 rounded-lg bg-[#09090B] border border-white/5 space-y-2">
            <div className="flex items-center gap-1.5 text-slate-300 font-bold font-mono uppercase text-[11px]">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
              <span>Confidence & Limitations</span>
            </div>
            <p className="text-slate-400 leading-relaxed text-[11px]">
              <strong className="text-emerald-400">{activeFocusRisk.confidence}% Model Confidence</strong> derived from high data quality (94% completeness).
              <span className="block mt-1 text-[10px] text-slate-500 italic">
                *Prediction represents an analytical likelihood indicator based on reported digital telemetry and observations; does not replace qualified HSE professional judgement.
              </span>
            </p>
          </div>

        </div>
      </div>

      {/* 5. Management Attention Required (3-5 Items Only) */}
      <div className="p-5 rounded-xl bg-[#16181D] border border-white/10 shadow-lg space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-white/5 pb-3">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base sm:text-lg font-bold text-white tracking-tight flex items-center gap-2">
                <AlertOctagon className="w-4 h-4 text-red-400" />
                <span>Management Attention Required</span>
              </h2>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-red-950/60 text-red-300 border border-red-800/60 font-bold">
                5 Priority Directives
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              High-impact operational bottlenecks, control failures, and contractor risks requiring executive ownership.
            </p>
          </div>

          <div className="text-xs text-slate-400 font-mono">
            <span>Reviewed Today:</span>{' '}
            <span className="text-slate-200 font-semibold">{Object.values(acknowledgedItems).filter(Boolean).length} / {MANAGEMENT_ATTENTION_ITEMS.length} Acknowledged</span>
          </div>
        </div>

        {/* Priority Action Items List */}
        <div className="space-y-3">
          {MANAGEMENT_ATTENTION_ITEMS.map((item) => {
            const isAcknowledged = acknowledgedItems[item.id];
            return (
              <div
                key={item.id}
                className={`p-4 rounded-xl border transition-all ${
                  isAcknowledged
                    ? 'bg-[#09090B]/50 border-white/5 opacity-75'
                    : item.severity === 'Critical'
                    ? 'bg-[#1C181E] border-red-500/40 shadow-sm'
                    : item.severity === 'High'
                    ? 'bg-[#1B1A1D] border-amber-500/30'
                    : 'bg-[#16181D] border-white/10'
                }`}
              >
                <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                  {/* Left: Severity, Title, Trend, Driver */}
                  <div className="space-y-2 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded ${
                        item.severity === 'Critical'
                          ? 'bg-red-950/80 text-red-300 border border-red-500/80'
                          : item.severity === 'High'
                          ? 'bg-amber-950/80 text-amber-300 border border-amber-500/80'
                          : 'bg-blue-950/80 text-blue-300 border border-blue-500/80'
                      }`}>
                        {item.severity}
                      </span>
                      <span className="text-xs font-bold text-white">
                        {item.title}
                      </span>
                      <span className="text-slate-500 text-xs">•</span>
                      <span className="text-[11px] font-mono text-slate-400">
                        {item.scope}
                      </span>
                    </div>

                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-300">
                      <div className="flex items-center gap-1.5">
                        <span className="text-slate-500 font-mono text-[11px]">Trend:</span>
                        <span className="font-semibold text-slate-200">{item.trend}</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span className="text-slate-500 font-mono text-[11px]">Owner:</span>
                        <span className="font-semibold text-blue-400 flex items-center gap-1">
                          <UserCheck className="w-3 h-3" />
                          {item.owner}
                        </span>
                      </div>
                    </div>

                    {/* Recommended Action */}
                    <div className="p-2.5 rounded-lg bg-[#09090B] border border-white/5 text-xs text-slate-200">
                      <span className="font-bold text-amber-400 font-mono text-[10px] uppercase block mb-0.5">
                        Recommended Action:
                      </span>
                      <span>{item.recommendedAction}</span>
                    </div>
                  </div>

                  {/* Right: Due Date, Urgency & Action Buttons */}
                  <div className="flex lg:flex-col items-center lg:items-end justify-between gap-2.5 shrink-0 border-t lg:border-t-0 pt-2 lg:pt-0 border-white/5">
                    <div className="text-right">
                      <div className="flex items-center gap-1.5 text-xs text-slate-300 font-mono">
                        <Calendar className="w-3.5 h-3.5 text-slate-400" />
                        <span>Due: {item.dueDate}</span>
                      </div>
                      <span className={`inline-block mt-1 text-[10px] font-mono font-bold px-2 py-0.5 rounded ${
                        item.urgency === 'Within 48h' || item.urgency === 'Immediate'
                          ? 'bg-red-950/60 text-red-400 border border-red-800/60'
                          : 'bg-amber-950/60 text-amber-400 border border-amber-800/60'
                      }`}>
                        {item.urgency}
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        onClick={(e) => toggleAcknowledge(item.id, e)}
                        className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-1.5 border ${
                          isAcknowledged
                            ? 'bg-emerald-950/60 text-emerald-300 border-emerald-800/60'
                            : 'bg-white/5 hover:bg-white/10 text-slate-200 border-white/10'
                        }`}
                      >
                        <CheckSquare className="w-3.5 h-3.5" />
                        <span>{isAcknowledged ? 'Acknowledged' : 'Acknowledge'}</span>
                      </button>

                      <button
                        onClick={onNavigateToInterventions}
                        className="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-sm transition-colors flex items-center gap-1"
                      >
                        <span>Dispatch</span>
                        <ChevronRight className="w-3 h-3" />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 6. Multi-Series Risk Trajectory Line Chart (Trend Progression) */}
      <div className="p-5 rounded-xl bg-[#16181D] border border-white/5 space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <Activity className="w-4 h-4 text-blue-400" />
              <span>Multi-Series Risk Trajectory ({dateRangeInfo.label})</span>
            </h3>
            <p className="text-[11px] text-slate-400">
              Bayesian causal trend progression across key high-hazard disciplines at {currentSite}
            </p>
          </div>
          <button 
            onClick={onNavigateToIntelligence}
            className="text-xs font-semibold text-blue-400 hover:text-blue-300 flex items-center gap-1 self-start sm:self-auto"
          >
            <span>Open Intelligence Center</span>
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="h-64 sm:h-72 w-full pt-2">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={filteredTrendData} margin={{ top: 10, right: 15, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#262b36" />
              <XAxis dataKey="date" stroke="#64748b" fontSize={11} tickLine={false} />
              <YAxis domain={[30, 90]} stroke="#64748b" fontSize={11} tickLine={false} />
              <Tooltip
                contentStyle={{ backgroundColor: '#16181D', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '8px', fontSize: '12px', color: '#f8fafc' }}
              />
              <Legend wrapperStyle={{ fontSize: '11px', paddingTop: '10px' }} />
              <Line type="monotone" dataKey="overall" name="Overall Index" stroke="#3b82f6" strokeWidth={3} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="lifting" name="Lifting Ops" stroke="#f43f5e" strokeWidth={2} dot={{ r: 2 }} />
              <Line type="monotone" dataKey="processSafety" name="Process Safety" stroke="#f59e0b" strokeWidth={2} strokeDasharray="3 3" />
              <Line type="monotone" dataKey="vehicle" name="Vehicle Movement" stroke="#a855f7" strokeWidth={2} />
              <Line type="monotone" dataKey="height" name="Work at Height" stroke="#10b981" strokeWidth={1.5} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

    </div>
  );
};
