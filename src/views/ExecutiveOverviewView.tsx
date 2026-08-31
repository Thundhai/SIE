import React, { useState } from 'react';
import { 
  AlertTriangle, 
  TrendingUp, 
  ShieldAlert, 
  CheckCircle2, 
  Clock, 
  Sparkles, 
  ArrowRight, 
  FileText, 
  ExternalLink,
  Filter,
  BarChart2,
  Activity,
  Layers,
  ChevronRight,
  Info,
  RotateCcw,
  ShieldCheck,
  Search
} from 'lucide-react';
import { 
  ResponsiveContainer, 
  LineChart, 
  Line, 
  XAxis, 
  YAxis, 
  Tooltip, 
  CartesianGrid, 
  Legend,
  AreaChart,
  Area
} from 'recharts';
import { EmergingRisk, GlobalFilterState } from '../types';
import { RISK_TREND_90_DAYS } from '../mockData';
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
  const baseCategories = [
    { name: 'Lifting Operations', riskScore: 78, level: 'High', count: 14, icon: '🏗️', delta: '+14%' },
    { name: 'Process Safety', riskScore: 69, level: 'High', count: 9, icon: '🔥', delta: '+11%' },
    { name: 'Contractor Management', riskScore: 65, level: 'High', count: 19, icon: '👷', delta: '+12%' },
    { name: 'Vehicle Movement', riskScore: 61, level: 'High', count: 8, icon: '🚚', delta: '+9%' },
    { name: 'Work at Height', riskScore: 54, level: 'Moderate', count: 6, icon: '🪜', delta: '+2%' },
    { name: 'Confined Space', riskScore: 48, level: 'Moderate', count: 4, icon: '🕳️', delta: '-6%' },
    { name: 'Electrical', riskScore: 42, level: 'Moderate', count: 2, icon: '⚡', delta: '0%' },
    { name: 'PPE Compliance', riskScore: 38, level: 'Low', count: 3, icon: '🦺', delta: '-8%' },
  ];

  // Dynamic real-time filtered risks
  const filteredRisks = filterRisks(risks, globalFilter);
  const filteredTrendData = filterTrendData(RISK_TREND_90_DAYS, globalFilter);
  const primaryRisk = filteredRisks[0] || risks[0];

  // Dynamic categories matching filtered data
  const availableCategoriesList = Array.from(new Set(risks.map(r => r.category)));

  // Dynamic recalculated KPI metrics based on filtered results
  const calculatedRiskScore = filteredRisks.length > 0 
    ? Math.round(filteredRisks.reduce((acc, r) => acc + r.probability, 0) / filteredRisks.length)
    : 0;
  
  const highRisksCount = filteredRisks.filter(r => r.level === 'High' || r.level === 'Critical').length;
  const criticalCount = filteredRisks.filter(r => r.probability >= 70).length;
  const totalEvidenceRecords = filteredRisks.reduce((acc, r) => acc + r.orgRecordsCount + r.externalSourcesCount, 0);

  const dateRangeInfo = getPresetDateRange(globalFilter.dateRangePreset);

  return (
    <div className="space-y-6 animate-in fade-in duration-200">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-white/5 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl sm:text-2xl font-bold text-white tracking-tight">
              Safety Intelligence Overview
            </h1>
            <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-blue-600/10 text-blue-400 border border-blue-500/20 font-semibold">
              Live Real-Time Engine
            </span>
          </div>
          <p className="text-xs sm:text-sm text-slate-400 mt-1 max-w-3xl leading-relaxed">
            Organization-wide safety intelligence generated from operational data, historical incidents, and verified external safety knowledge.
          </p>
        </div>

        {/* Quick Assistant CTA */}
        <button
          onClick={() => onNavigateToAssistant("Summarize the top safety priorities across Lagos Operations today.")}
          className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-lg shadow-blue-600/20 transition-all shrink-0"
        >
          <Sparkles className="w-4 h-4 text-blue-200" />
          <span>Ask SIE Assistant</span>
        </button>
      </div>

      {/* Interactive Global Real-Time Filter Bar */}
      <GlobalFilterBar
        filter={globalFilter}
        onChange={onFilterChange}
        totalCount={risks.length}
        filteredCount={filteredRisks.length}
        availableCategories={availableCategoriesList}
        showCategoryFilter={true}
      />

      {/* KPI Cards Grid - Recalculated Dynamically */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 sm:gap-4">
        {/* Overall Safety Intelligence */}
        <div className="p-4 rounded-xl bg-[#16181D] border border-white/5 shadow-sm relative overflow-hidden group hover:border-white/10 transition-all">
          <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
            Filtered Safety Index
          </div>
          <div className="flex items-baseline gap-1 mt-2">
            <span className="text-2xl sm:text-3xl font-extrabold text-blue-400 font-mono">
              {calculatedRiskScore > 0 ? calculatedRiskScore : '--'}
            </span>
            <span className="text-xs text-slate-500 font-mono">/ 100</span>
          </div>
          <div className="mt-2 text-[11px] text-amber-400 flex items-center gap-1 font-medium">
            <TrendingUp className="w-3 h-3" />
            <span>{calculatedRiskScore >= 60 ? 'Elevated Attention' : 'Controlled Baseline'}</span>
          </div>
          <div className="absolute top-0 right-0 w-16 h-16 bg-blue-500/5 rounded-full blur-xl pointer-events-none" />
        </div>

        {/* Emerging Risks */}
        <div 
          onClick={onNavigateToIntelligence}
          className="p-4 rounded-xl bg-[#16181D] border border-white/5 shadow-sm cursor-pointer hover:border-red-500/40 hover:bg-[#1C1F27] transition-all group"
        >
          <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider flex items-center justify-between">
            <span>Emerging Risks</span>
            <ChevronRight className="w-3.5 h-3.5 text-slate-600 group-hover:text-red-400 transition-transform group-hover:translate-x-0.5" />
          </div>
          <div className="mt-2 text-2xl sm:text-3xl font-extrabold text-red-400 font-mono">
            {filteredRisks.length}
          </div>
          <div className="mt-2 text-[11px] text-slate-400">
            <strong className="text-red-400">{criticalCount} Critical</strong> • {filteredRisks.length - criticalCount} Monitored
          </div>
        </div>

        {/* High-Risk Disciplines */}
        <div className="p-4 rounded-xl bg-[#16181D] border border-white/5 shadow-sm">
          <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
            High-Risk Disciplines
          </div>
          <div className="mt-2 text-2xl sm:text-3xl font-extrabold text-amber-400 font-mono">
            {highRisksCount}
          </div>
          <div className="mt-2 text-[11px] text-slate-400 truncate">
            {filteredRisks.slice(0, 2).map(r => r.category).join(', ') || 'No active alerts'}
          </div>
        </div>

        {/* Ingested Evidence Count */}
        <div className="p-4 rounded-xl bg-[#16181D] border border-white/5 shadow-sm">
          <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
            Evidence Records
          </div>
          <div className="mt-2 text-2xl sm:text-3xl font-extrabold text-emerald-400 font-mono">
            {totalEvidenceRecords}
          </div>
          <div className="mt-2 text-[11px] text-slate-400">
            Org & External Citations
          </div>
        </div>

        {/* Open Critical Actions */}
        <div 
          onClick={onNavigateToInterventions}
          className="p-4 rounded-xl bg-[#16181D] border border-white/5 shadow-sm cursor-pointer hover:border-amber-500/40 hover:bg-[#1C1F27] transition-all group"
        >
          <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider flex items-center justify-between">
            <span>Open Actions</span>
            <ChevronRight className="w-3.5 h-3.5 text-slate-600 group-hover:text-amber-400" />
          </div>
          <div className="mt-2 text-2xl sm:text-3xl font-extrabold text-amber-400 font-mono">
            14
          </div>
          <div className="mt-2 text-[11px] text-red-400">
            3 High Priority Rigging
          </div>
        </div>

        {/* Timeframe Scope */}
        <div className="p-4 rounded-xl bg-[#16181D] border border-white/5 shadow-sm">
          <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
            Time Horizon
          </div>
          <div className="mt-2 text-base sm:text-lg font-bold text-white font-mono flex items-center gap-1 truncate">
            <span>{globalFilter.dateRangePreset.toUpperCase()}</span>
          </div>
          <div className="mt-2 text-[11px] text-slate-400 truncate">
            {dateRangeInfo.label}
          </div>
        </div>
      </div>

      {/* AI Executive Insight Banner */}
      {primaryRisk && (
        <div className="p-5 sm:p-6 rounded-xl bg-[#16181D] border border-blue-500/25 shadow-xl relative overflow-hidden">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
            <div className="space-y-2.5 max-w-4xl">
              <div className="flex items-center gap-2">
                <div className="px-2 py-0.5 rounded bg-blue-600/10 border border-blue-500/20 text-blue-400 text-[10px] font-mono font-bold uppercase tracking-wider flex items-center gap-1.5">
                  <Sparkles className="w-3 h-3 text-blue-400" />
                  AI Executive Insight
                </div>
                <span className="text-xs text-slate-400 font-mono">• {currentSite} Real-time Synthesis</span>
              </div>

              <h2 className="text-base sm:text-lg font-bold text-white tracking-tight flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-red-400 shrink-0" />
                <span>Emerging risk detected in {primaryRisk.category.toLowerCase()}</span>
              </h2>

              <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                {primaryRisk.summary || primaryRisk.mainDriver}
              </p>

              <div className="flex flex-wrap items-center gap-4 text-xs pt-1">
                <div className="flex items-center gap-1.5 font-semibold text-slate-200">
                  <span className="text-slate-400 font-normal">Confidence:</span>
                  <span className="px-2 py-0.5 rounded bg-[#09090B] text-emerald-400 font-mono font-bold border border-white/5">
                    {primaryRisk.confidence}%
                  </span>
                </div>
                <div className="flex items-center gap-1.5 font-semibold text-slate-200">
                  <span className="text-slate-400 font-normal">Probability:</span>
                  <span className="px-2 py-0.5 rounded bg-red-950/60 text-red-400 font-mono font-bold border border-red-800/60">
                    {primaryRisk.probability}% ({primaryRisk.level})
                  </span>
                </div>
                <div className="text-slate-400 text-xs font-mono">
                  Identified: {primaryRisk.identifiedDate}
                </div>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex flex-col sm:flex-row lg:flex-col gap-2.5 shrink-0">
              <button
                onClick={() => onSelectRisk(primaryRisk.id)}
                className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-md shadow-blue-600/20 transition-colors flex items-center justify-center gap-2"
              >
                <span>View Prediction</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
              {primaryRisk.organizationEvidence && primaryRisk.organizationEvidence[0] && (
                <button
                  onClick={() => onOpenEvidence(primaryRisk.organizationEvidence[0])}
                  className="px-4 py-2 rounded-lg bg-[#09090B] hover:bg-white/5 border border-white/10 text-slate-200 text-xs font-semibold transition-colors flex items-center justify-center gap-2"
                >
                  <FileText className="w-3.5 h-3.5 text-blue-400" />
                  <span>View Evidence ({primaryRisk.orgRecordsCount} records)</span>
                </button>
              )}
              <button
                onClick={onNavigateToInterventions}
                className="px-4 py-2 rounded-lg bg-amber-950/40 hover:bg-amber-900/50 border border-amber-800/60 text-amber-300 text-xs font-semibold transition-colors flex items-center justify-center gap-2"
              >
                <ShieldAlert className="w-3.5 h-3.5 text-amber-400" />
                <span>Create Intervention</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Main Analytical Grid: Risk Landscape & Risk Trend Chart */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Risk Landscape (5 cols) */}
        <div className="lg:col-span-5 p-5 rounded-xl bg-[#16181D] border border-white/5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div>
                <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                  <Layers className="w-4 h-4 text-blue-400" />
                  <span>Risk Landscape</span>
                </h3>
                <p className="text-[11px] text-slate-400">Click a category to focus filter</p>
              </div>
              {globalFilter.selectedCategory && (
                <button
                  onClick={() => onFilterChange({ ...globalFilter, selectedCategory: null })}
                  className="text-[11px] text-blue-400 hover:underline flex items-center gap-1"
                >
                  <RotateCcw className="w-3 h-3" />
                  <span>Reset Category</span>
                </button>
              )}
            </div>

            {/* Category Cards / Matrix */}
            <div className="grid grid-cols-2 gap-2.5 mt-3">
              {baseCategories.map((cat) => {
                const isSelected = globalFilter.selectedCategory === cat.name;
                const matchesRisk = filteredRisks.some(r => r.category === cat.name);
                return (
                  <button
                    key={cat.name}
                    onClick={() => onFilterChange({
                      ...globalFilter,
                      selectedCategory: isSelected ? null : cat.name
                    })}
                    className={`p-3 rounded-lg border text-left transition-all relative ${
                      isSelected
                        ? 'bg-blue-600/20 border-blue-500 text-white shadow-md ring-1 ring-blue-500/40'
                        : matchesRisk
                        ? 'bg-[#09090B] hover:bg-white/5 border-white/10 text-slate-200'
                        : 'bg-[#09090B]/50 opacity-60 border-white/5 text-slate-400'
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <span className="text-base">{cat.icon}</span>
                      <span className={`text-[10px] font-mono px-1.5 py-0.2 rounded font-bold ${
                        cat.level === 'High'
                          ? 'bg-red-950/60 text-red-400 border border-red-800/60'
                          : cat.level === 'Moderate'
                          ? 'bg-amber-950/60 text-amber-400 border border-amber-800/60'
                          : 'bg-slate-800/80 text-emerald-400 border border-white/5'
                      }`}>
                        {cat.riskScore}%
                      </span>
                    </div>
                    <div className="font-semibold text-xs text-slate-100 mt-2 truncate">
                      {cat.name}
                    </div>
                    <div className="flex items-center justify-between text-[10px] text-slate-400 mt-1">
                      <span>{cat.count} Observations</span>
                      <span className={cat.delta.startsWith('+') ? 'text-red-400 font-mono' : 'text-emerald-400 font-mono'}>
                        {cat.delta}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-white/5 flex items-center justify-between text-[11px] text-slate-400">
            <span>Critical Threshold: 70%</span>
            <span className="font-mono text-blue-400">{filteredRisks.length} Matched in Scope</span>
          </div>
        </div>

        {/* Risk Trend Line Chart (7 cols) - Real-time adjusted */}
        <div className="lg:col-span-7 p-5 rounded-xl bg-[#16181D] border border-white/5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2">
              <div>
                <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                  <Activity className="w-4 h-4 text-blue-400" />
                  <span>Risk Trajectory ({dateRangeInfo.label})</span>
                </h3>
                <p className="text-[11px] text-slate-400">Live multi-series Bayesian causal trend progression</p>
              </div>
              <div className="text-[11px] font-mono px-2 py-0.5 rounded bg-[#09090B] text-slate-300 border border-white/5">
                {currentSite}
              </div>
            </div>

            {/* Chart Area */}
            <div className="h-64 sm:h-72 w-full mt-3">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={filteredTrendData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
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

          <div className="mt-2 pt-2 border-t border-white/5 flex items-center justify-between text-[11px] text-slate-400">
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-red-500"></span>
              <span>Visualizing {filteredTrendData.length} timeline snapshot intervals</span>
            </span>
            <button 
              onClick={onNavigateToIntelligence}
              className="text-blue-400 hover:text-blue-300 font-medium flex items-center gap-1"
            >
              <span>Full Analytics</span>
              <ChevronRight className="w-3 h-3" />
            </button>
          </div>
        </div>
      </div>

      {/* Top Emerging Risks Table (Real-Time Filtered) */}
      <div className="p-5 rounded-xl bg-[#16181D] border border-white/5">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-red-400" />
              <span>Emerging Risks Data Table</span>
            </h3>
            <p className="text-[11px] text-slate-400">
              Showing {filteredRisks.length} of {risks.length} risks matching active criteria
            </p>
          </div>
          <button
            onClick={onNavigateToIntelligence}
            className="text-xs font-semibold text-blue-400 hover:text-blue-300 flex items-center gap-1"
          >
            <span>Open Intelligence Center</span>
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Table or Empty State */}
        {filteredRisks.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-white/5 text-slate-500 font-semibold uppercase tracking-wider text-[10px]">
                  <th className="py-2.5 px-3">Risk Domain</th>
                  <th className="py-2.5 px-3">Level</th>
                  <th className="py-2.5 px-3">Probability</th>
                  <th className="py-2.5 px-3">Trend</th>
                  <th className="py-2.5 px-3">Main Driver</th>
                  <th className="py-2.5 px-3">Date Identified</th>
                  <th className="py-2.5 px-3">Confidence</th>
                  <th className="py-2.5 px-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5 text-slate-300">
                {filteredRisks.map((risk) => (
                  <tr 
                    key={risk.id} 
                    className="hover:bg-white/5 transition-colors group cursor-pointer"
                    onClick={() => onSelectRisk(risk.id)}
                  >
                    <td className="py-3 px-3 font-semibold text-slate-100 flex items-center gap-2">
                      <div className={`w-2 h-2 rounded-full ${
                        risk.level === 'Critical' ? 'bg-red-500 ring-2 ring-red-500/30' :
                        risk.level === 'High' ? 'bg-orange-500' :
                        risk.level === 'Moderate' ? 'bg-amber-500' : 'bg-emerald-500'
                      }`} />
                      <div>
                        <div className="group-hover:text-blue-300 transition-colors font-medium">{risk.category}</div>
                        <div className="text-[10px] text-slate-500 font-normal line-clamp-1 max-w-[200px]">{risk.location}</div>
                      </div>
                    </td>
                    <td className="py-3 px-3">
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
                    </td>
                    <td className="py-3 px-3 font-mono font-bold text-slate-100">
                      <span className={`px-2 py-0.5 rounded text-[11px] ${
                        risk.probability >= 70 ? 'bg-red-950/60 text-red-400 border border-red-800/60' : 'bg-amber-950/60 text-amber-400 border border-amber-800/60'
                      }`}>
                        {risk.probability}%
                      </span>
                    </td>
                    <td className="py-3 px-3 font-mono text-[11px]">
                      <span className={risk.trajectory === 'Increasing' ? 'text-red-400' : risk.trajectory === 'Decreasing' ? 'text-emerald-400' : 'text-slate-400'}>
                        {risk.trajectory === 'Increasing' ? `↑ +${risk.trendPercentage}%` : risk.trajectory === 'Decreasing' ? `↓ ${risk.trendPercentage}%` : '→ Stable'}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-slate-300 max-w-xs truncate text-[11px]">
                      {risk.mainDriver}
                    </td>
                    <td className="py-3 px-3 font-mono text-slate-400 text-[11px]">
                      {risk.identifiedDate}
                    </td>
                    <td className="py-3 px-3 font-mono text-slate-300 text-[11px]">
                      {risk.confidence}%
                    </td>
                    <td className="py-3 px-3 text-right">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectRisk(risk.id);
                        }}
                        className="px-2.5 py-1 rounded bg-white/5 hover:bg-blue-600 hover:text-white text-slate-300 text-xs font-medium transition-colors inline-flex items-center gap-1 border border-white/5"
                      >
                        <span>Investigate</span>
                        <ChevronRight className="w-3 h-3" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="py-12 text-center rounded-xl bg-[#09090B] border border-white/5">
            <div className="w-12 h-12 rounded-full bg-white/5 flex items-center justify-center mx-auto text-slate-400 mb-3">
              <Search className="w-6 h-6" />
            </div>
            <h4 className="text-sm font-bold text-white mb-1">No Risks Match Filter Criteria</h4>
            <p className="text-xs text-slate-400 max-w-md mx-auto mb-4">
              Try adjusting your date range, broadening risk severity levels, or resetting data source filters.
            </p>
            <button
              onClick={() => onFilterChange({
                dateRangePreset: '90d',
                customStartDate: '2026-06-01',
                customEndDate: '2026-08-31',
                riskLevels: [],
                dataSources: [],
                searchQuery: '',
                selectedCategory: null
              })}
              className="px-4 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold inline-flex items-center gap-1.5 shadow-sm transition-all"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Reset All Filters</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
