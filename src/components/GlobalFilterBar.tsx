import React, { useState } from 'react';
import { 
  Filter, 
  Calendar, 
  Search, 
  X, 
  RotateCcw, 
  ChevronDown, 
  SlidersHorizontal,
  Check,
  Activity,
  Layers,
  Sparkles,
  ShieldAlert,
  Database
} from 'lucide-react';
import { GlobalFilterState, RiskLevel, DataSourceFilter, DateRangePreset } from '../types';
import { getPresetDateRange, INITIAL_FILTER_STATE } from '../utils/filterUtils';

interface GlobalFilterBarProps {
  filter?: GlobalFilterState;
  onChange?: (newFilter: GlobalFilterState) => void;
  totalCount?: number;
  filteredCount?: number;
  availableCategories?: string[];
  showCategoryFilter?: boolean;
  compact?: boolean;
}

export const GlobalFilterBar: React.FC<GlobalFilterBarProps> = ({
  filter,
  onChange,
  totalCount = 8,
  filteredCount = 8,
  availableCategories,
  showCategoryFilter = true,
  compact = false
}) => {
  const [isExpanded, setIsExpanded] = useState(!compact);
  const [showDateDropdown, setShowDateDropdown] = useState(false);
  const [showSourcesDropdown, setShowSourcesDropdown] = useState(false);

  const activeFilter: GlobalFilterState = {
    ...INITIAL_FILTER_STATE,
    ...(filter || {})
  };

  const handleUpdate = (updated: GlobalFilterState) => {
    if (onChange) {
      onChange(updated);
    }
  };

  const datePresets: { id: DateRangePreset; label: string }[] = [
    { id: '7d', label: 'Last 7 Days' },
    { id: '30d', label: 'Last 30 Days' },
    { id: '90d', label: 'Last 90 Days' },
    { id: '180d', label: 'Last 180 Days' },
    { id: 'ytd', label: 'Year to Date (2026)' },
    { id: 'custom', label: 'Custom Date Range...' }
  ];

  const riskLevelOptions: { level: RiskLevel; color: string; activeClass: string; dotColor: string }[] = [
    { level: 'Critical', color: 'text-red-400', activeClass: 'bg-red-950/70 border-red-500/80 text-red-300 ring-1 ring-red-500/50', dotColor: 'bg-red-500' },
    { level: 'High', color: 'text-orange-400', activeClass: 'bg-orange-950/70 border-orange-500/80 text-orange-300 ring-1 ring-orange-500/50', dotColor: 'bg-orange-500' },
    { level: 'Moderate', color: 'text-amber-400', activeClass: 'bg-amber-950/70 border-amber-500/80 text-amber-300 ring-1 ring-amber-500/50', dotColor: 'bg-amber-500' },
    { level: 'Low', color: 'text-emerald-400', activeClass: 'bg-emerald-950/70 border-emerald-500/80 text-emerald-300 ring-1 ring-emerald-500/50', dotColor: 'bg-emerald-500' }
  ];

  const dataSourceOptions: { id: DataSourceFilter; label: string; iconLabel: string }[] = [
    { id: 'Observation', label: 'Observations (Field)', iconLabel: '👁️' },
    { id: 'Near Miss', label: 'Near Misses (HiPo)', iconLabel: '⚠️' },
    { id: 'Incident', label: 'Incidents & Injuries', iconLabel: '🚨' },
    { id: 'Audit Finding', label: 'Audits & Inspections', iconLabel: '📋' },
    { id: 'Permit Exception', label: 'Permit-to-Work Exceptions', iconLabel: '📑' },
    { id: 'External Standard', label: 'External Standards (HSE/OSHA)', iconLabel: '📚' },
    { id: 'IoT Telemetry', label: 'IoT Sensors & Telematics', iconLabel: '📡' }
  ];

  // Helper functions
  const handleToggleRiskLevel = (level: RiskLevel) => {
    let newLevels: RiskLevel[];
    const currentLevels = activeFilter.riskLevels || [];
    if (currentLevels.includes(level)) {
      newLevels = currentLevels.filter(l => l !== level);
    } else {
      newLevels = [...currentLevels, level];
    }
    handleUpdate({ ...activeFilter, riskLevels: newLevels });
  };

  const handleToggleDataSource = (source: DataSourceFilter) => {
    let newSources: DataSourceFilter[];
    const currentSources = activeFilter.dataSources || [];
    if (currentSources.includes(source)) {
      newSources = currentSources.filter(s => s !== source);
    } else {
      newSources = [...currentSources, source];
    }
    handleUpdate({ ...activeFilter, dataSources: newSources });
  };

  const handleResetAll = () => {
    handleUpdate({
      dateRangePreset: '90d',
      customStartDate: '2026-06-01',
      customEndDate: '2026-08-31',
      riskLevels: [],
      dataSources: [],
      searchQuery: '',
      selectedCategory: null
    });
  };

  const activeFiltersCount = 
    ((activeFilter.riskLevels && activeFilter.riskLevels.length > 0) ? 1 : 0) +
    ((activeFilter.dataSources && activeFilter.dataSources.length > 0) ? 1 : 0) +
    (activeFilter.searchQuery ? 1 : 0) +
    (activeFilter.selectedCategory ? 1 : 0) +
    (activeFilter.dateRangePreset !== '90d' ? 1 : 0);

  const selectedPresetLabel = datePresets.find(p => p.id === activeFilter.dateRangePreset)?.label || 'Last 90 Days';

  return (
    <div className="rounded-xl bg-[#16181D] border border-white/10 shadow-lg overflow-hidden transition-all duration-200">
      {/* Top Main Filter Toolbar */}
      <div className="p-3.5 sm:p-4 flex flex-col lg:flex-row lg:items-center justify-between gap-3 bg-[#111317]/80 border-b border-white/5">
        {/* Search & Quick Controls Left */}
        <div className="flex flex-1 items-center gap-2.5 flex-wrap sm:flex-nowrap">
          {/* Keyword Search Input */}
          <div className="relative flex-1 min-w-[200px] sm:min-w-[260px]">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5 pointer-events-none" />
            <input
              type="text"
              placeholder="Filter by keyword, equipment, driver, site..."
              value={activeFilter.searchQuery || ''}
              onChange={(e) => handleUpdate({ ...activeFilter, searchQuery: e.target.value })}
              className="w-full bg-[#09090B] border border-white/10 rounded-lg pl-9 pr-8 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-500/80 focus:ring-1 focus:ring-blue-500/40 transition-all"
            />
            {activeFilter.searchQuery && (
              <button
                onClick={() => handleUpdate({ ...activeFilter, searchQuery: '' })}
                className="absolute right-2.5 top-2.5 text-slate-400 hover:text-white"
                title="Clear search"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {/* Date Range Selector Dropdown */}
          <div className="relative">
            <button
              onClick={() => {
                setShowDateDropdown(!showDateDropdown);
                setShowSourcesDropdown(false);
              }}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-medium transition-all ${
                activeFilter.dateRangePreset !== '90d'
                  ? 'bg-blue-600/15 border-blue-500/50 text-blue-300'
                  : 'bg-[#09090B] border-white/10 text-slate-200 hover:bg-white/5 hover:border-white/20'
              }`}
            >
              <Calendar className="w-3.5 h-3.5 text-blue-400 shrink-0" />
              <span className="truncate max-w-[130px] sm:max-w-none">{selectedPresetLabel}</span>
              <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
            </button>

            {showDateDropdown && (
              <div className="absolute left-0 mt-1.5 w-64 rounded-xl bg-[#16181D] border border-white/15 shadow-2xl p-2 z-50 animate-in fade-in zoom-in-95">
                <div className="text-[10px] font-semibold text-slate-400 px-2 py-1 uppercase tracking-wider border-b border-white/5">
                  Select Time Horizon
                </div>
                <div className="mt-1 space-y-0.5">
                  {datePresets.map((preset) => (
                    <button
                      key={preset.id}
                      onClick={() => {
                        handleUpdate({ ...activeFilter, dateRangePreset: preset.id });
                        if (preset.id !== 'custom') {
                          setShowDateDropdown(false);
                        }
                      }}
                      className={`w-full text-left px-2.5 py-1.5 rounded-lg text-xs transition-colors flex items-center justify-between ${
                        activeFilter.dateRangePreset === preset.id
                          ? 'bg-blue-600/20 text-blue-300 font-semibold'
                          : 'text-slate-300 hover:bg-white/5 hover:text-white'
                      }`}
                    >
                      <span>{preset.label}</span>
                      {activeFilter.dateRangePreset === preset.id && (
                        <Check className="w-3.5 h-3.5 text-blue-400" />
                      )}
                    </button>
                  ))}
                </div>

                {/* Custom Date Pickers */}
                {activeFilter.dateRangePreset === 'custom' && (
                  <div className="mt-2.5 pt-2.5 border-t border-white/10 px-2 space-y-2">
                    <div>
                      <label className="text-[10px] text-slate-400 uppercase font-semibold block mb-1">
                        From Date
                      </label>
                      <input
                        type="date"
                        value={activeFilter.customStartDate || '2026-06-01'}
                        onChange={(e) => handleUpdate({ ...activeFilter, customStartDate: e.target.value })}
                        className="w-full bg-[#09090B] border border-white/10 rounded-md px-2 py-1 text-xs text-white focus:outline-none focus:border-blue-500"
                      />
                    </div>
                    <div>
                      <label className="text-[10px] text-slate-400 uppercase font-semibold block mb-1">
                        To Date
                      </label>
                      <input
                        type="date"
                        value={activeFilter.customEndDate || '2026-08-31'}
                        onChange={(e) => handleUpdate({ ...activeFilter, customEndDate: e.target.value })}
                        className="w-full bg-[#09090B] border border-white/10 rounded-md px-2 py-1 text-xs text-white focus:outline-none focus:border-blue-500"
                      />
                    </div>
                    <button
                      onClick={() => setShowDateDropdown(false)}
                      className="w-full mt-1 py-1 rounded bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium transition-colors"
                    >
                      Apply Custom Range
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Category Dropdown (if enabled) */}
          {showCategoryFilter && availableCategories && availableCategories.length > 0 && (
            <div className="relative">
              <select
                value={activeFilter.selectedCategory || 'ALL'}
                onChange={(e) => handleUpdate({
                  ...activeFilter,
                  selectedCategory: e.target.value === 'ALL' ? null : e.target.value
                })}
                className="bg-[#09090B] border border-white/10 text-xs text-slate-200 rounded-lg px-3 py-1.5 focus:outline-none focus:border-blue-500/80 cursor-pointer"
              >
                <option value="ALL">All Risk Disciplines</option>
                {availableCategories.map(cat => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* Right Stats & Reset Action */}
        <div className="flex items-center gap-3 justify-between sm:justify-end">
          {/* Matched Count Counter */}
          <div className="flex items-center gap-1.5 text-xs text-slate-400 font-medium">
            <Activity className="w-3.5 h-3.5 text-blue-400" />
            <span>
              Showing <strong className="text-white font-mono">{filteredCount}</strong> of{' '}
              <span className="font-mono text-slate-500">{totalCount}</span>
            </span>
          </div>

          {/* Reset Filters CTA */}
          {activeFiltersCount > 0 && (
            <button
              onClick={handleResetAll}
              className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-red-950/40 hover:bg-red-900/60 border border-red-800/50 text-red-300 text-xs font-semibold transition-all"
              title="Reset all active filters"
            >
              <RotateCcw className="w-3 h-3" />
              <span>Reset ({activeFiltersCount})</span>
            </button>
          )}

          {/* Expand/Collapse Toggle */}
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/5 transition-colors"
            title={isExpanded ? 'Collapse filter trays' : 'Expand filter trays'}
          >
            <SlidersHorizontal className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Expanded Multi-Select Trays: Risk Levels & Data Sources */}
      {isExpanded && (
        <div className="p-3.5 sm:p-4 space-y-3.5 bg-[#16181D]">
          {/* Risk Level Filter Chips Row */}
          <div className="flex flex-col sm:flex-row sm:items-center gap-2">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5 shrink-0 w-28">
              <ShieldAlert className="w-3.5 h-3.5 text-blue-400" />
              <span>Risk Level:</span>
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              {/* All Levels Button */}
              <button
                onClick={() => handleUpdate({ ...activeFilter, riskLevels: [] })}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
                  (!activeFilter.riskLevels || activeFilter.riskLevels.length === 0)
                    ? 'bg-blue-600 text-white font-semibold shadow-sm'
                    : 'bg-[#09090B] text-slate-400 border border-white/5 hover:border-white/15 hover:text-slate-200'
                }`}
              >
                All Levels
              </button>

              {/* Individual Risk Level Chips */}
              {riskLevelOptions.map((opt) => {
                const isActive = activeFilter.riskLevels && activeFilter.riskLevels.includes(opt.level);
                return (
                  <button
                    key={opt.level}
                    onClick={() => handleToggleRiskLevel(opt.level)}
                    className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium border transition-all ${
                      isActive
                        ? opt.activeClass
                        : 'bg-[#09090B] border-white/5 text-slate-400 hover:border-white/20 hover:text-slate-200'
                    }`}
                  >
                    <span className={`w-2 h-2 rounded-full ${opt.dotColor}`} />
                    <span>{opt.level}</span>
                    {isActive && <Check className="w-3 h-3 ml-0.5" />}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Data Sources Multi-Select Row */}
          <div className="flex flex-col sm:flex-row sm:items-start gap-2 pt-2 border-t border-white/5">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5 shrink-0 w-28 mt-1">
              <Database className="w-3.5 h-3.5 text-emerald-400" />
              <span>Data Sources:</span>
            </div>

            <div className="flex items-center gap-1.5 flex-wrap">
              {/* All Sources Button */}
              <button
                onClick={() => handleUpdate({ ...activeFilter, dataSources: [] })}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-all ${
                  (!activeFilter.dataSources || activeFilter.dataSources.length === 0)
                    ? 'bg-emerald-600/30 text-emerald-300 border border-emerald-500/50 font-semibold'
                    : 'bg-[#09090B] text-slate-400 border border-white/5 hover:border-white/15 hover:text-slate-200'
                }`}
              >
                All Ingestion Streams
              </button>

              {/* Individual Source Pills */}
              {dataSourceOptions.map((src) => {
                const isSelected = activeFilter.dataSources && activeFilter.dataSources.includes(src.id);
                return (
                  <button
                    key={src.id}
                    onClick={() => handleToggleDataSource(src.id)}
                    className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium border transition-all ${
                      isSelected
                        ? 'bg-emerald-950/70 border-emerald-500/80 text-emerald-300 ring-1 ring-emerald-500/40 shadow-sm'
                        : 'bg-[#09090B] border-white/5 text-slate-400 hover:border-white/20 hover:text-slate-200'
                    }`}
                  >
                    <span className="text-xs">{src.iconLabel}</span>
                    <span>{src.label}</span>
                    {isSelected && <Check className="w-3 h-3 ml-0.5 text-emerald-400" />}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Active Filter Badges Summary Strip (if any active) */}
          {activeFiltersCount > 0 && (
            <div className="pt-2 border-t border-white/5 flex items-center gap-2 flex-wrap text-xs">
              <span className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">
                Active Criteria:
              </span>

              {activeFilter.dateRangePreset !== '90d' && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-600/10 text-blue-300 border border-blue-500/30 text-[11px]">
                  Time: {selectedPresetLabel}
                  <button
                    onClick={() => handleUpdate({ ...activeFilter, dateRangePreset: '90d' })}
                    className="hover:text-white"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              )}

              {activeFilter.riskLevels && activeFilter.riskLevels.map(lvl => (
                <span
                  key={lvl}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-red-950/60 text-red-300 border border-red-800/60 text-[11px]"
                >
                  Level: {lvl}
                  <button
                    onClick={() => handleToggleRiskLevel(lvl)}
                    className="hover:text-white"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}

              {activeFilter.dataSources && activeFilter.dataSources.map(src => (
                <span
                  key={src}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-950/60 text-emerald-300 border border-emerald-800/60 text-[11px]"
                >
                  Source: {src}
                  <button
                    onClick={() => handleToggleDataSource(src)}
                    className="hover:text-white"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}

              {activeFilter.selectedCategory && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-purple-950/60 text-purple-300 border border-purple-800/60 text-[11px]">
                  Discipline: {activeFilter.selectedCategory}
                  <button
                    onClick={() => handleUpdate({ ...activeFilter, selectedCategory: null })}
                    className="hover:text-white"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              )}

              {activeFilter.searchQuery && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-white/10 text-white border border-white/20 text-[11px]">
                  "{activeFilter.searchQuery}"
                  <button
                    onClick={() => handleUpdate({ ...activeFilter, searchQuery: '' })}
                    className="hover:text-red-400"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              )}

              <button
                onClick={handleResetAll}
                className="text-[11px] text-slate-400 hover:text-white underline underline-offset-2 ml-1"
              >
                Clear all
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
