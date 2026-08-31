import React, { useState } from 'react';
import { 
  BrainCircuit, 
  Search, 
  Filter, 
  ArrowRight, 
  FileText, 
  ShieldAlert, 
  TrendingUp, 
  Sparkles, 
  AlertOctagon, 
  Layers, 
  CheckCircle2, 
  ExternalLink, 
  ChevronDown, 
  RotateCcw, 
  Activity, 
  AlertTriangle, 
  Radio, 
  Cpu, 
  HelpCircle,
  Database,
  Info,
  Sliders
} from 'lucide-react';
import { EmergingRisk, GlobalFilterState, LineageStageId } from '../types';
import { GlobalFilterBar } from '../components/GlobalFilterBar';
import { filterRisks, INITIAL_FILTER_STATE } from '../utils/filterUtils';
import { EvidenceLineageModal } from '../components/EvidenceLineageModal';
import { getRiskMethodology } from '../utils/methodologyUtils';

interface IntelligenceCenterViewProps {
  risks: EmergingRisk[];
  globalFilter?: GlobalFilterState;
  onFilterChange?: (filter: GlobalFilterState) => void;
  onSelectRisk: (riskId: string) => void;
  onOpenEvidence: (evidence: any) => void;
  onNavigateToInterventions: () => void;
}

export const IntelligenceCenterView: React.FC<IntelligenceCenterViewProps> = ({
  risks,
  globalFilter = INITIAL_FILTER_STATE,
  onFilterChange = (_f?: GlobalFilterState) => {},
  onSelectRisk,
  onOpenEvidence,
  onNavigateToInterventions
}) => {
  const [activeTab, setActiveTab] = useState<'emerging' | 'predictions' | 'anomalies' | 'patterns' | 'drivers'>('emerging');
  const [selectedRiskForLineage, setSelectedRiskForLineage] = useState<EmergingRisk | null>(null);
  const [selectedLineageStage, setSelectedLineageStage] = useState<LineageStageId>('prediction');
  const [showProbConfExplainer, setShowProbConfExplainer] = useState(false);

  // Real-time filtered data
  const filteredRisks = filterRisks(risks, globalFilter);
  const availableCategoriesList = Array.from(new Set(risks.map(r => r.category)));

  const handleOpenLineage = (risk: EmergingRisk, stageId: LineageStageId = 'prediction') => {
    setSelectedRiskForLineage(risk);
    setSelectedLineageStage(stageId);
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-200">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-white/5 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl sm:text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
              <BrainCircuit className="w-6 h-6 text-blue-400" />
              <span>Intelligence Center</span>
            </h1>
            <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-blue-600/10 text-blue-300 border border-blue-500/20">
              Multi-Model Predictive Engine
            </span>
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-800 font-bold">
              DEMO
            </span>
          </div>
          <p className="text-xs sm:text-sm text-slate-400 mt-1 max-w-3xl leading-relaxed">
            Multi-source causal reasoning engines processing field telemetry, incident registers, contractor logs, and verified international standards.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowProbConfExplainer(!showProbConfExplainer)}
            className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-semibold text-slate-200 transition-colors flex items-center gap-1.5"
          >
            <HelpCircle className="w-3.5 h-3.5 text-cyan-400" />
            <span>Probability vs. Confidence</span>
          </button>

          <button
            onClick={onNavigateToInterventions}
            className="px-3.5 py-2 rounded-lg bg-amber-950/40 hover:bg-amber-900/60 border border-amber-800/60 text-amber-300 text-xs font-semibold transition-colors flex items-center gap-2"
          >
            <ShieldAlert className="w-4 h-4 text-amber-400" />
            <span>Active Interventions ({filteredRisks.length > 0 ? 3 : 0})</span>
          </button>
        </div>
      </div>

      {/* Probability vs Confidence Explainer Banner */}
      {showProbConfExplainer && (
        <div className="p-4 rounded-xl bg-blue-950/30 border border-blue-500/30 space-y-2 animate-in fade-in duration-150">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-bold text-blue-300 flex items-center gap-1.5">
              <Info className="w-4 h-4 text-blue-400" />
              <span>Scientific Distinction: Estimated Probability vs. Model Confidence</span>
            </h4>
            <button
              onClick={() => setShowProbConfExplainer(false)}
              className="text-xs text-slate-400 hover:text-white"
            >
              Dismiss
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs text-slate-300 pt-1">
            <div className="p-3 rounded-lg bg-[#16181D] border border-white/5">
              <strong className="text-blue-300 block mb-1">Probability</strong>
              <p className="text-[11px] text-slate-300 leading-relaxed">
                The <strong>estimated likelihood</strong> of the modeled risk condition occurring within the defined forecast horizon (e.g. 30-90 days), based on active precursors and baseline exposures.
              </p>
            </div>
            <div className="p-3 rounded-lg bg-[#16181D] border border-white/5">
              <strong className="text-emerald-300 block mb-1">Confidence Score</strong>
              <p className="text-[11px] text-slate-300 leading-relaxed">
                The <strong>analytical assessment confidence</strong> derived from data quality, evidence strength, sample completeness, and inter-model consensus. <em>Does not imply an X% chance of an accident.</em>
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Mandatory Scientific Interpretation Notice */}
      <div className="p-3.5 rounded-xl bg-amber-950/20 border border-amber-500/30 flex items-start gap-2.5 text-amber-200 text-xs">
        <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
        <p className="leading-relaxed">
          <strong>Scientific Interpretation Notice:</strong> Predictions are analytical risk indicators, not guarantees that an incident will occur. They should support—not replace—professional HSE judgement.
        </p>
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

      {/* Navigation Tabs */}
      <div className="flex items-center gap-2 border-b border-white/5 overflow-x-auto pb-1">
        {[
          { id: 'emerging', label: `Emerging Risks (${filteredRisks.length})` },
          { id: 'predictions', label: 'Predictions Table (30-90D)' },
          { id: 'anomalies', label: 'Anomalies & IoT Outliers' },
          { id: 'patterns', label: 'Recurring Patterns' },
          { id: 'drivers', label: 'Risk Drivers & Causal Factors' },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            className={`px-4 py-2 text-xs font-semibold rounded-t-lg transition-colors border-b-2 whitespace-nowrap ${
              activeTab === tab.id
                ? 'border-blue-400 text-blue-300 bg-[#16181D]'
                : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-[#16181D]/40'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* TAB 1: Emerging Risks Cards */}
      {activeTab === 'emerging' && (
        <div className="space-y-4">
          {filteredRisks.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              {filteredRisks.map((risk) => {
                const meth = getRiskMethodology(risk);
                return (
                  <div
                    key={risk.id}
                    className="p-5 sm:p-6 rounded-xl bg-[#16181D] border border-white/5 hover:border-blue-500/40 shadow-md transition-all flex flex-col justify-between group"
                  >
                    <div>
                      {/* Header Row */}
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded uppercase tracking-wider ${
                              risk.level === 'Critical'
                                ? 'bg-red-950/70 text-red-300 border border-red-500/70'
                                : risk.level === 'High'
                                ? 'bg-orange-950/70 text-orange-300 border border-orange-500/70'
                                : risk.level === 'Moderate'
                                ? 'bg-amber-950/70 text-amber-300 border border-amber-500/70'
                                : 'bg-emerald-950/70 text-emerald-300 border border-emerald-500/70'
                            }`}>
                              {risk.level} Priority
                            </span>
                            <span className="text-xs text-slate-400 font-mono">
                              {risk.location}
                            </span>
                            <span className="text-[10px] font-mono text-slate-500">
                              • {meth.modelVersion}
                            </span>
                          </div>
                          <h3 className="text-base font-bold text-white mt-1.5 group-hover:text-blue-300 transition-colors">
                            {risk.category}
                          </h3>
                          <p className="text-xs text-slate-300 font-medium mt-0.5 line-clamp-1">
                            {risk.title}
                          </p>
                        </div>

                        <div className="text-right shrink-0">
                          <div className="text-[11px] font-semibold text-slate-400">Risk Trajectory</div>
                          <div className="text-xs font-mono font-bold mt-0.5 flex items-center justify-end gap-1">
                            <span className={risk.trajectory === 'Increasing' ? 'text-red-400' : risk.trajectory === 'Decreasing' ? 'text-emerald-400' : 'text-slate-400'}>
                              {risk.trajectory} ({risk.trendPercentage > 0 ? `+${risk.trendPercentage}%` : `${risk.trendPercentage}%`})
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Prob & Confidence Metrics with Data Quality */}
                      <div className="grid grid-cols-3 gap-2.5 my-4 p-3 rounded-lg bg-[#09090B] border border-white/5">
                        <div>
                          <span className="text-[9px] text-slate-400 uppercase tracking-wider block font-semibold">
                            Probability
                          </span>
                          <div className="text-xl font-extrabold text-blue-400 font-mono mt-0.5">
                            {risk.probability}%
                          </div>
                          <span className="text-[9px] text-slate-400 font-mono block">Est. Likelihood</span>
                        </div>
                        <div>
                          <span className="text-[9px] text-slate-400 uppercase tracking-wider block font-semibold">
                            Confidence
                          </span>
                          <div className="text-xl font-extrabold text-emerald-400 font-mono mt-0.5">
                            {risk.confidence}%
                          </div>
                          <span className="text-[9px] text-slate-400 font-mono block">Model Certainty</span>
                        </div>
                        <div>
                          <span className="text-[9px] text-slate-400 uppercase tracking-wider block font-semibold">
                            Data Quality
                          </span>
                          <div className="text-xl font-extrabold text-white font-mono mt-0.5">
                            {meth.dataQualityScore}%
                          </div>
                          <span className="text-[9px] text-slate-400 font-mono block">Hist: {meth.historicalCoverage}%</span>
                        </div>
                      </div>

                      {/* Drivers List */}
                      <div className="space-y-1.5 mb-4">
                        <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
                          Key Risk Drivers & Precursors:
                        </span>
                        {risk.drivers.slice(0, 3).map((drv, idx) => (
                          <div key={idx} className="flex items-start gap-2 text-xs text-slate-300">
                            <span className="w-1.5 h-1.5 rounded-full bg-blue-400 mt-1.5 shrink-0" />
                            <span className="line-clamp-1">{drv}</span>
                          </div>
                        ))}
                      </div>

                      {/* Evidence & Methodology Badges */}
                      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400 pb-4 border-b border-white/5">
                        <div className="flex items-center gap-2">
                          <span className="flex items-center gap-1 font-mono text-blue-300 text-[11px]">
                            <FileText className="w-3.5 h-3.5 text-blue-400" />
                            <span>{risk.orgRecordsCount} records</span>
                          </span>
                          <span>•</span>
                          <span className="flex items-center gap-1 font-mono text-purple-300 text-[11px]">
                            <Sparkles className="w-3.5 h-3.5 text-purple-400" />
                            <span>{risk.externalSourcesCount} standards</span>
                          </span>
                        </div>
                        <button
                          onClick={() => handleOpenLineage(risk, 'prediction')}
                          className="text-[10px] font-mono text-cyan-400 hover:text-cyan-300 hover:underline flex items-center gap-1"
                        >
                          <Layers className="w-3 h-3" />
                          <span>Trace Lineage</span>
                        </button>
                      </div>
                    </div>

                    {/* Bottom Actions */}
                    <div className="flex items-center justify-between pt-4 gap-2">
                      <button
                        onClick={() => onSelectRisk(risk.id)}
                        className="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow transition-colors flex items-center gap-1.5"
                      >
                        <span>Investigate Risk</span>
                        <ArrowRight className="w-3.5 h-3.5" />
                      </button>
                      
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleOpenLineage(risk, 'analytical-method')}
                          className="px-2.5 py-1.5 rounded-lg bg-[#09090B] hover:bg-white/5 border border-white/10 text-slate-200 text-xs font-medium transition-colors"
                        >
                          Methodology
                        </button>
                        <button
                          onClick={onNavigateToInterventions}
                          className="px-2.5 py-1.5 rounded-lg bg-amber-950/40 hover:bg-amber-900/60 border border-amber-800/60 text-amber-300 text-xs font-medium transition-colors"
                        >
                          Intervene
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="py-16 text-center rounded-xl bg-[#16181D] border border-white/5">
              <div className="w-12 h-12 rounded-full bg-white/5 flex items-center justify-center mx-auto text-slate-400 mb-3">
                <Search className="w-6 h-6" />
              </div>
              <h4 className="text-sm font-bold text-white mb-1">No Risk Insights Found</h4>
              <p className="text-xs text-slate-400 max-w-md mx-auto mb-4">
                No emerging risks match the active filter criteria. Try broadening severity levels or resetting filters.
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
      )}

      {/* TAB 2: Predictions Table */}
      {activeTab === 'predictions' && (
        <div className="p-5 rounded-xl bg-[#16181D] border border-white/5 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                <Activity className="w-4 h-4 text-blue-400" />
                <span>Predicted Exposure Horizon Table (30-90 Days)</span>
              </h3>
              <p className="text-[11px] text-slate-400">
                Scientific prediction models calibrated with Bayesian probability and cross-validated analytical confidence
              </p>
            </div>
            <div className="text-xs font-mono text-blue-400 flex items-center gap-2">
              <span>{filteredRisks.length} Models in Scope</span>
              <span>•</span>
              <span className="text-slate-400">Avg Quality: 94%</span>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-white/5 text-slate-500 font-semibold uppercase tracking-wider text-[10px]">
                  <th className="py-2.5 px-3">Hazard Identifier</th>
                  <th className="py-2.5 px-3">Domain</th>
                  <th className="py-2.5 px-3">Location</th>
                  <th className="py-2.5 px-3">Severity Level</th>
                  <th className="py-2.5 px-3">Probability (Likelihood)</th>
                  <th className="py-2.5 px-3">Confidence (Certainty)</th>
                  <th className="py-2.5 px-3">Data Quality</th>
                  <th className="py-2.5 px-3">Forecast Window</th>
                  <th className="py-2.5 px-3 text-right">Scientific Lineage</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5 text-slate-300">
                {filteredRisks.map((risk) => {
                  const meth = getRiskMethodology(risk);
                  return (
                    <tr 
                      key={risk.id}
                      onClick={() => onSelectRisk(risk.id)}
                      className="hover:bg-white/5 transition-colors cursor-pointer group"
                    >
                      <td className="py-3 px-3 font-mono text-blue-400 font-semibold">
                        {risk.id}
                      </td>
                      <td className="py-3 px-3 font-semibold text-slate-100 group-hover:text-blue-300">
                        {risk.category}
                      </td>
                      <td className="py-3 px-3 text-slate-400 text-[11px]">
                        {risk.location}
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
                      <td className="py-3 px-3 font-mono font-bold text-blue-400">
                        {risk.probability}%
                      </td>
                      <td className="py-3 px-3 font-mono font-bold text-emerald-400">
                        {risk.confidence}%
                      </td>
                      <td className="py-3 px-3 font-mono text-slate-300 text-[11px]">
                        {meth.dataQualityScore}%
                      </td>
                      <td className="py-3 px-3 text-slate-400 text-[11px]">
                        {meth.forecastPeriod}
                      </td>
                      <td className="py-3 px-3 text-right">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleOpenLineage(risk, 'prediction');
                          }}
                          className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-cyan-300 text-xs font-semibold inline-flex items-center gap-1 border border-slate-700 transition-all mr-1.5"
                        >
                          <Layers className="w-3 h-3" />
                          <span>Lineage</span>
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onSelectRisk(risk.id);
                          }}
                          className="px-2.5 py-1 rounded bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold inline-flex items-center gap-1 shadow-sm transition-all"
                        >
                          <span>Examine</span>
                          <ArrowRight className="w-3 h-3" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 3: Anomalies & IoT Outliers */}
      {activeTab === 'anomalies' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="p-5 rounded-xl bg-[#16181D] border border-white/5 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Radio className="w-4 h-4 text-red-400 animate-pulse" />
                <h4 className="text-sm font-bold text-white">Sensor Telemetry Surge (Lifting Gear)</h4>
              </div>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-red-950/70 text-red-400 border border-red-800/60">
                +42% Variance
              </span>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              Vibration and load cycle telemetry on Crane #4 showed 18 anomalous load peak spikes during shift transitions over the past 14 days.
            </p>
            <div className="p-3 rounded-lg bg-[#09090B] border border-white/5 flex items-center justify-between text-xs font-mono">
              <span className="text-slate-400">Data Source: IoT Telemetry Feed</span>
              <span className="text-red-400">Flagged Today</span>
            </div>
          </div>

          <div className="p-5 rounded-xl bg-[#16181D] border border-white/5 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Radio className="w-4 h-4 text-amber-400" />
                <h4 className="text-sm font-bold text-white">Permit-to-Work Duration Outlier</h4>
              </div>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-950/70 text-amber-400 border border-amber-800/60">
                +3.5h Average
              </span>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              SIMOPS confined space work permits averaged 3.5 hours longer than standard risk assessment envelopes, indicating scope creep.
            </p>
            <div className="p-3 rounded-lg bg-[#09090B] border border-white/5 flex items-center justify-between text-xs font-mono">
              <span className="text-slate-400">Data Source: ERP / SAP EHS</span>
              <span className="text-amber-400">3 Days Ago</span>
            </div>
          </div>
        </div>
      )}

      {/* TAB 4: Recurring Patterns */}
      {activeTab === 'patterns' && (
        <div className="p-5 rounded-xl bg-[#16181D] border border-white/5 space-y-4">
          <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
            <Layers className="w-4 h-4 text-blue-400" />
            <span>Cross-Site Safety Correlation Patterns</span>
          </h3>
          <p className="text-xs text-slate-400">
            Automated clustering discovered 3 persistent behavioral and operational patterns matching your filter parameters.
          </p>

          <div className="space-y-3">
            <div className="p-4 rounded-lg bg-[#09090B] border border-white/5 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <div className="font-semibold text-xs text-white">Subcontractor Turnover vs. Near Miss Velocity</div>
                <div className="text-xs text-slate-400 mt-1">When subcontractor crews rotate &gt;30% in a 14-day window, observation frequency increases by 2.8x.</div>
              </div>
              <div className="text-xs font-mono text-emerald-400 shrink-0">94% Pattern Confidence</div>
            </div>

            <div className="p-4 rounded-lg bg-[#09090B] border border-white/5 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <div className="font-semibold text-xs text-white">Pre-Task Tool Box Talk Quality Index Correlation</div>
                <div className="text-xs text-slate-400 mt-1">Sites with lower TBT engagement scores showed 41% higher incidence of rigging tag errors.</div>
              </div>
              <div className="text-xs font-mono text-emerald-400 shrink-0">89% Pattern Confidence</div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 5: Risk Drivers */}
      {activeTab === 'drivers' && (
        <div className="p-5 rounded-xl bg-[#16181D] border border-white/5 space-y-4">
          <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-amber-400" />
            <span>Top Causal Precursors and Drivers Across Filtered Scope</span>
          </h3>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {[
              { name: 'Rigging Equipment Wear & Tear', weight: 88, source: 'Observations' },
              { name: 'Subcontractor Crew Familiarity Gap', weight: 82, source: 'Training Logs' },
              { name: 'SIMOPS High-Density Congestion', weight: 75, source: 'Operational Schedule' },
              { name: 'Weather Wind Speed Alerts', weight: 68, source: 'IoT Telemetry' },
              { name: 'Overdue Corrective Actions', weight: 64, source: 'Audit Registry' },
              { name: 'Night Shift Fatigue Index', weight: 58, source: 'Time Tracking' },
            ].map((driver, idx) => (
              <div key={idx} className="p-4 rounded-lg bg-[#09090B] border border-white/5">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] font-mono text-blue-400">{driver.source}</span>
                  <span className="text-xs font-mono font-bold text-amber-400">{driver.weight}% Impact</span>
                </div>
                <div className="text-xs font-semibold text-slate-200">{driver.name}</div>
                <div className="w-full bg-slate-800 h-1.5 rounded-full mt-3 overflow-hidden">
                  <div className="bg-blue-500 h-full rounded-full" style={{ width: `${driver.weight}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Evidence Lineage Modal */}
      {selectedRiskForLineage && (
        <EvidenceLineageModal
          isOpen={!!selectedRiskForLineage}
          onClose={() => setSelectedRiskForLineage(null)}
          risk={selectedRiskForLineage}
          initialStageId={selectedLineageStage}
          onNavigateToInterventions={onNavigateToInterventions}
          onOpenEvidenceRecord={onOpenEvidence}
        />
      )}
    </div>
  );
};

