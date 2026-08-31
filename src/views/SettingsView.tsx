import React, { useState, useMemo } from 'react';
import {
  Sliders,
  Bell,
  ShieldAlert,
  Percent,
  SlidersHorizontal,
  Activity,
  CheckCircle2,
  AlertTriangle,
  Send,
  RotateCcw,
  Save,
  Download,
  Upload,
  Sparkles,
  Smartphone,
  Mail,
  Flame,
  Layers,
  Check,
  ChevronRight,
  Info,
  Clock,
  MapPin,
  UserCheck,
  FileCode,
  Zap,
  Radio
} from 'lucide-react';
import { AlertThresholdConfig, CategoryThresholdOverride, EmergingRisk, NotificationItem } from '../types';
import { 
  DEFAULT_ALERT_CONFIG, 
  SENSITIVITY_PRESETS, 
  evaluateAllRisks, 
  generatePersonalizedNotifications,
  RiskEvaluationResult 
} from '../utils/thresholdUtils';
import { SITES_LIST } from '../mockData';

interface SettingsViewProps {
  risks: EmergingRisk[];
  currentConfig: AlertThresholdConfig;
  onSaveConfig: (config: AlertThresholdConfig) => void;
  onTriggerAlerts: (newNotifications: NotificationItem[]) => void;
  onAddToast: (title: string, message: string, type?: 'success' | 'info' | 'warning' | 'error') => void;
  onSelectRisk?: (riskId: string) => void;
}

export const SettingsView: React.FC<SettingsViewProps> = ({
  risks,
  currentConfig,
  onSaveConfig,
  onTriggerAlerts,
  onAddToast,
  onSelectRisk
}) => {
  // Local state for editing form
  const [config, setConfig] = useState<AlertThresholdConfig>(currentConfig || DEFAULT_ALERT_CONFIG);
  const [activeTab, setActiveTab] = useState<'thresholds' | 'overrides' | 'channels' | 'profile'>('thresholds');
  const [hasChanges, setHasChanges] = useState(false);
  const [showJsonModal, setShowJsonModal] = useState(false);

  // Live evaluation of current risks against current editable threshold config
  const liveEvaluations: RiskEvaluationResult[] = useMemo(() => {
    return evaluateAllRisks(risks, config);
  }, [risks, config]);

  const triggeredCount = liveEvaluations.filter(e => e.isTriggered).length;

  const handleUpdate = (updater: (prev: AlertThresholdConfig) => AlertThresholdConfig) => {
    setConfig(prev => {
      const next = updater(prev);
      setHasChanges(true);
      return next;
    });
  };

  const handleApplyPreset = (presetKey: 'strict' | 'balanced' | 'conservative') => {
    const preset = SENSITIVITY_PRESETS[presetKey];
    handleUpdate(prev => ({
      ...prev,
      sensitivityPreset: presetKey,
      globalMinProbability: preset.globalMinProbability,
      globalMinConfidence: preset.globalMinConfidence,
      surgeDeltaThreshold: preset.surgeDeltaThreshold
    }));
    onAddToast(
      'Sensitivity Preset Loaded',
      `Applied ${preset.label}: ${preset.globalMinProbability}% prob / ${preset.globalMinConfidence}% conf.`,
      'info'
    );
  };

  const handleSave = () => {
    onSaveConfig(config);
    setHasChanges(false);
    onAddToast(
      'Threshold Configuration Saved',
      'HSE alert criteria and notification routing successfully updated across the intelligence pipeline.',
      'success'
    );
  };

  const handleReset = () => {
    setConfig(DEFAULT_ALERT_CONFIG);
    setHasChanges(true);
    onAddToast('Reset to Defaults', 'Standard HSE safety threshold parameters restored.', 'info');
  };

  const handleRunEvaluation = () => {
    const newAlerts = generatePersonalizedNotifications(risks, config);
    if (newAlerts.length > 0) {
      onTriggerAlerts(newAlerts);
      onAddToast(
        'Alert Evaluation Complete',
        `Dispatched ${newAlerts.length} personalized safety notifications matching your threshold criteria.`,
        'success'
      );
    } else {
      onAddToast(
        'No Threshold Violations',
        'None of the active operational risks currently meet the alert trigger criteria.',
        'info'
      );
    }
  };

  const handleSendTestNotification = () => {
    const testNotif: NotificationItem = {
      id: `TEST-ALERT-${Date.now()}`,
      title: `[Test Alert] Safety Threshold Protocol Verification`,
      category: 'Risk Alert',
      message: `Personalized test notification dispatched to ${config.userPreferences.recipientName} (${config.userPreferences.recipientRole}). Channels active: In-App, SMS, Email Digest.`,
      timestamp: 'Just now',
      severity: 'High',
      isRead: false,
      relatedRiskId: 'RISK-LIFT-01'
    };
    onTriggerAlerts([testNotif]);
    onAddToast(
      'Test Alert Dispatched',
      `Simulated alert successfully routed to notification drawer for ${config.userPreferences.recipientName}.`,
      'success'
    );
  };

  const handleExportJson = () => {
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(config, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute("href", dataStr);
    downloadAnchor.setAttribute("download", `safelytic-alert-thresholds-${new Date().toISOString().split('T')[0]}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
    onAddToast('Configuration Exported', 'Alert threshold rules downloaded as JSON.', 'info');
  };

  const handleToggleSite = (siteName: string) => {
    handleUpdate(prev => {
      const currentSites = prev.userPreferences.designatedSites;
      let newSites: string[];
      if (currentSites.includes(siteName)) {
        newSites = currentSites.filter(s => s !== siteName);
      } else {
        newSites = [...currentSites, siteName];
      }
      return {
        ...prev,
        userPreferences: {
          ...prev.userPreferences,
          designatedSites: newSites
        }
      };
    });
  };

  const handleUpdateOverride = (index: number, field: keyof CategoryThresholdOverride, value: any) => {
    handleUpdate(prev => {
      const updatedOverrides = [...prev.categoryOverrides];
      updatedOverrides[index] = {
        ...updatedOverrides[index],
        [field]: value
      };
      return {
        ...prev,
        categoryOverrides: updatedOverrides
      };
    });
  };

  return (
    <div className="space-y-6 pb-12 animate-in fade-in">
      {/* Top Banner Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[#16181D] p-6 rounded-xl border border-white/10 shadow-lg">
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-blue-400 font-semibold text-xs uppercase tracking-wider">
            <Sliders className="w-4 h-4 text-blue-400" />
            <span>HSE Manager Configuration</span>
          </div>
          <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-3">
            Risk Probability & Confidence Alert Thresholds
            {hasChanges && (
              <span className="text-[11px] font-medium bg-amber-500/20 text-amber-300 border border-amber-500/30 px-2.5 py-0.5 rounded-full">
                Unsaved Changes
              </span>
            )}
          </h2>
          <p className="text-xs text-slate-400 max-w-3xl leading-relaxed">
            Define mathematical trigger gates for Bayesian predictive probability, model confidence thresholds, velocity surges, and discipline-specific overrides to deliver personalized safety intelligence alerts.
          </p>
        </div>

        {/* Global Action Bar */}
        <div className="flex items-center gap-2.5 flex-wrap">
          <button
            onClick={handleReset}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-[#09090B] border border-white/10 text-xs font-medium text-slate-300 hover:text-white hover:bg-white/5 transition-colors"
            title="Restore default parameters"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Reset</span>
          </button>
          
          <button
            onClick={handleExportJson}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-[#09090B] border border-white/10 text-xs font-medium text-slate-300 hover:text-white hover:bg-white/5 transition-colors"
            title="Download threshold rules JSON"
          >
            <Download className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Export</span>
          </button>

          <button
            onClick={handleSendTestNotification}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-purple-600/20 border border-purple-500/40 text-xs font-medium text-purple-300 hover:bg-purple-600/30 transition-colors"
            title="Send a personalized sample notification to verify routing"
          >
            <Send className="w-3.5 h-3.5" />
            <span>Test Alert</span>
          </button>

          <button
            onClick={handleSave}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-semibold shadow-md transition-all ${
              hasChanges 
                ? 'bg-blue-600 hover:bg-blue-500 text-white shadow-blue-600/30 ring-2 ring-blue-400/40' 
                : 'bg-blue-600/80 hover:bg-blue-600 text-white'
            }`}
          >
            <Save className="w-3.5 h-3.5" />
            <span>Save Configuration</span>
          </button>
        </div>
      </div>

      {/* Main Grid: Left Settings Form (8 cols) & Right Live Simulation (4 cols) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Left Form: Tabs & Settings (8 cols) */}
        <div className="lg:col-span-8 space-y-6">
          
          {/* Navigation Sub-Tabs */}
          <div className="flex items-center gap-2 border-b border-white/10 pb-2 overflow-x-auto custom-scrollbar">
            <button
              onClick={() => setActiveTab('thresholds')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
                activeTab === 'thresholds'
                  ? 'bg-blue-600/20 text-blue-300 border border-blue-500/40 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
              }`}
            >
              <SlidersHorizontal className="w-4 h-4" />
              <span>Core Probability & Confidence</span>
            </button>

            <button
              onClick={() => setActiveTab('overrides')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
                activeTab === 'overrides'
                  ? 'bg-blue-600/20 text-blue-300 border border-blue-500/40 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
              }`}
            >
              <Layers className="w-4 h-4" />
              <span>Discipline Overrides ({config.categoryOverrides.filter(o => o.enabled).length})</span>
            </button>

            <button
              onClick={() => setActiveTab('channels')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
                activeTab === 'channels'
                  ? 'bg-blue-600/20 text-blue-300 border border-blue-500/40 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
              }`}
            >
              <Radio className="w-4 h-4" />
              <span>Channels & Escalation</span>
            </button>

            <button
              onClick={() => setActiveTab('profile')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
                activeTab === 'profile'
                  ? 'bg-blue-600/20 text-blue-300 border border-blue-500/40 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
              }`}
            >
              <UserCheck className="w-4 h-4" />
              <span>HSE Recipient & Scope</span>
            </button>
          </div>

          {/* TAB 1: CORE PROBABILITY & CONFIDENCE THRESHOLDS */}
          {activeTab === 'thresholds' && (
            <div className="space-y-6">
              
              {/* Sensitivity Presets Selector */}
              <div className="bg-[#16181D] p-5 rounded-xl border border-white/10 shadow-md space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-blue-400" />
                    Alert Sensitivity Profiles
                  </h3>
                  <span className="text-[11px] text-slate-400">
                    Quickly configure operational tolerance
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {(Object.keys(SENSITIVITY_PRESETS) as Array<keyof typeof SENSITIVITY_PRESETS>).map((key) => {
                    const preset = SENSITIVITY_PRESETS[key];
                    const isSelected = config.sensitivityPreset === key;
                    return (
                      <div
                        key={key}
                        onClick={() => handleApplyPreset(key)}
                        className={`p-3.5 rounded-lg border cursor-pointer transition-all ${
                          isSelected
                            ? 'bg-blue-600/15 border-blue-500/50 shadow-md shadow-blue-900/20'
                            : 'bg-[#09090B] border-white/5 hover:border-white/20 hover:bg-white/5'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className={`text-xs font-bold ${isSelected ? 'text-blue-300' : 'text-white'}`}>
                            {preset.label}
                          </span>
                          {isSelected && <CheckCircle2 className="w-4 h-4 text-blue-400" />}
                        </div>
                        <p className="text-[11px] text-slate-400 mt-1.5 line-clamp-2 leading-relaxed">
                          {preset.description}
                        </p>
                        <div className="mt-2.5 pt-2 border-t border-white/5 flex items-center justify-between text-[10px] font-mono text-slate-300">
                          <span>Prob ≥ {preset.globalMinProbability}%</span>
                          <span>Conf ≥ {preset.globalMinConfidence}%</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Threshold Sliders Card */}
              <div className="bg-[#16181D] p-5 rounded-xl border border-white/10 shadow-md space-y-6">
                <div className="border-b border-white/5 pb-3 flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-bold text-white">Global Alert Trigger Cutoffs</h3>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Risks exceeding these parameters will automatically trigger notifications to HSE leadership.
                    </p>
                  </div>
                  <span className="text-xs font-mono px-2 py-0.5 rounded bg-blue-600/10 text-blue-400 border border-blue-500/20">
                    Active Rule Gate
                  </span>
                </div>

                {/* 1. Risk Probability Slider */}
                <div className="space-y-2.5 bg-[#09090B] p-4 rounded-lg border border-white/5">
                  <div className="flex items-center justify-between">
                    <div>
                      <label className="text-xs font-bold text-slate-200 flex items-center gap-2">
                        <Activity className="w-4 h-4 text-red-400" />
                        Minimum Risk Probability Cutoff
                      </label>
                      <p className="text-[11px] text-slate-400">
                        Bayesian forecast probability of incident occurrence over 30-day lookahead window.
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-lg font-mono font-bold text-red-400">
                        {config.globalMinProbability}%
                      </span>
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <input
                      type="range"
                      min={30}
                      max={95}
                      step={1}
                      value={config.globalMinProbability}
                      onChange={(e) => {
                        const val = parseInt(e.target.value, 10);
                        handleUpdate(prev => ({
                          ...prev,
                          globalMinProbability: val,
                          sensitivityPreset: 'custom'
                        }));
                      }}
                      className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-red-500"
                    />
                    <div className="flex justify-between text-[10px] text-slate-500 font-mono">
                      <span>30% (High Volume / Low Barrier)</span>
                      <span>70% (Standard)</span>
                      <span>95% (Extreme Only)</span>
                    </div>
                  </div>
                </div>

                {/* 2. Model Confidence Slider */}
                <div className="space-y-2.5 bg-[#09090B] p-4 rounded-lg border border-white/5">
                  <div className="flex items-center justify-between">
                    <div>
                      <label className="text-xs font-bold text-slate-200 flex items-center gap-2">
                        <Percent className="w-4 h-4 text-blue-400" />
                        Minimum Model Confidence Threshold
                      </label>
                      <p className="text-[11px] text-slate-400">
                        Requires statistical multi-source evidence grounding (statutory standards + internal logs).
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-lg font-mono font-bold text-blue-400">
                        {config.globalMinConfidence}%
                      </span>
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <input
                      type="range"
                      min={40}
                      max={95}
                      step={1}
                      value={config.globalMinConfidence}
                      onChange={(e) => {
                        const val = parseInt(e.target.value, 10);
                        handleUpdate(prev => ({
                          ...prev,
                          globalMinConfidence: val,
                          sensitivityPreset: 'custom'
                        }));
                      }}
                      className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-blue-500"
                    />
                    <div className="flex justify-between text-[10px] text-slate-500 font-mono">
                      <span>40% (Exploratory / Sparse Data)</span>
                      <span>75% (Standard)</span>
                      <span>95% (High Statistical Rigor)</span>
                    </div>
                  </div>
                </div>

                {/* 3. Dynamic Velocity Surge & Action Overdues */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
                  {/* Velocity Surge Toggle */}
                  <div className="bg-[#09090B] p-4 rounded-lg border border-white/5 space-y-3">
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-2">
                        <Flame className="w-4 h-4 text-amber-400" />
                        <span className="text-xs font-bold text-white">Velocity Surge Trigger</span>
                      </div>
                      <label className="relative inline-flex items-center cursor-pointer">
                        <input
                          type="checkbox"
                          checked={config.alertOnSurgeDelta}
                          onChange={(e) => handleUpdate(prev => ({
                            ...prev,
                            alertOnSurgeDelta: e.target.checked
                          }))}
                          className="sr-only peer"
                        />
                        <div className="w-9 h-5 bg-slate-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-amber-500"></div>
                      </label>
                    </div>
                    <p className="text-[11px] text-slate-400">
                      Alert immediately if risk trajectory spikes by ≥ <span className="font-mono text-amber-300 font-bold">+{config.surgeDeltaThreshold}%</span> week-over-week.
                    </p>
                    {config.alertOnSurgeDelta && (
                      <div className="pt-2">
                        <div className="flex justify-between text-xs text-slate-300 mb-1">
                          <span>Surge Trigger Delta:</span>
                          <span className="font-mono font-bold text-amber-400">+{config.surgeDeltaThreshold}%</span>
                        </div>
                        <input
                          type="range"
                          min={5}
                          max={30}
                          step={1}
                          value={config.surgeDeltaThreshold}
                          onChange={(e) => {
                            const val = parseInt(e.target.value, 10);
                            handleUpdate(prev => ({ ...prev, surgeDeltaThreshold: val }));
                          }}
                          className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-amber-500"
                        />
                      </div>
                    )}
                  </div>

                  {/* Overdue Field Actions Toggle */}
                  <div className="bg-[#09090B] p-4 rounded-lg border border-white/5 space-y-3">
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-2">
                        <AlertTriangle className="w-4 h-4 text-red-400" />
                        <span className="text-xs font-bold text-white">Overdue Action Escalation</span>
                      </div>
                      <label className="relative inline-flex items-center cursor-pointer">
                        <input
                          type="checkbox"
                          checked={config.notifyOnOverdueActions}
                          onChange={(e) => handleUpdate(prev => ({
                            ...prev,
                            notifyOnOverdueActions: e.target.checked
                          }))}
                          className="sr-only peer"
                        />
                        <div className="w-9 h-5 bg-slate-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-red-500"></div>
                      </label>
                    </div>
                    <p className="text-[11px] text-slate-400">
                      Escalate risk severity when field inspections or audits have unresolved overdue CAPA items linked in the causal graph.
                    </p>
                    <div className="text-[10px] text-emerald-400 flex items-center gap-1 font-mono pt-1">
                      <CheckCircle2 className="w-3.5 h-3.5" /> Synchronized with ERP & Intelex DB
                    </div>
                  </div>
                </div>

              </div>
            </div>
          )}

          {/* TAB 2: DISCIPLINE-SPECIFIC OVERRIDES */}
          {activeTab === 'overrides' && (
            <div className="bg-[#16181D] p-5 rounded-xl border border-white/10 shadow-md space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-white/5 pb-3">
                <div>
                  <h3 className="text-sm font-bold text-white">Discipline-Specific Sensitivity Overrides</h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    High-hazard domains (e.g., Hydrocarbons/Process Safety) can be configured with more stringent threshold gates.
                  </p>
                </div>
                <span className="text-xs text-slate-400">
                  {config.categoryOverrides.filter(o => o.enabled).length} Overrides Active
                </span>
              </div>

              <div className="space-y-3">
                {config.categoryOverrides.map((override, idx) => (
                  <div
                    key={override.category}
                    className={`p-4 rounded-xl border transition-all ${
                      override.enabled
                        ? 'bg-[#09090B] border-blue-500/30 shadow-sm'
                        : 'bg-[#0F1117]/80 border-white/5 opacity-70'
                    }`}
                  >
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
                      
                      {/* Left: Category Info & Toggle */}
                      <div className="flex items-center gap-3">
                        <input
                          type="checkbox"
                          checked={override.enabled}
                          onChange={(e) => handleUpdateOverride(idx, 'enabled', e.target.checked)}
                          className="w-4 h-4 rounded bg-slate-900 border-white/20 text-blue-600 focus:ring-blue-500 focus:ring-1"
                        />
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-bold text-white">{override.category}</span>
                            {override.category === 'Process Safety' && (
                              <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-red-500/10 text-red-400 border border-red-500/20">
                                Major Accident Hazard
                              </span>
                            )}
                            {override.category === 'Lifting Operations' && (
                              <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
                                High Frequency SIMOPS
                              </span>
                            )}
                          </div>
                          <p className="text-[10px] text-slate-400 mt-0.5">
                            {override.enabled ? 'Custom threshold parameters enforced' : 'Using global threshold defaults'}
                          </p>
                        </div>
                      </div>

                      {/* Right: Sliders & Priority Routing */}
                      {override.enabled && (
                        <div className="flex items-center gap-4 flex-wrap">
                          {/* Min Prob */}
                          <div className="flex items-center gap-2 bg-[#16181D] px-2.5 py-1.5 rounded-lg border border-white/5">
                            <span className="text-[10px] text-slate-400 uppercase font-semibold">Min Prob:</span>
                            <input
                              type="number"
                              min={30}
                              max={95}
                              value={override.minProbability}
                              onChange={(e) => handleUpdateOverride(idx, 'minProbability', parseInt(e.target.value || '0', 10))}
                              className="w-12 bg-black/50 border border-white/10 text-xs font-mono font-bold text-red-400 rounded px-1 text-center"
                            />
                            <span className="text-[10px] text-slate-500">%</span>
                          </div>

                          {/* Min Conf */}
                          <div className="flex items-center gap-2 bg-[#16181D] px-2.5 py-1.5 rounded-lg border border-white/5">
                            <span className="text-[10px] text-slate-400 uppercase font-semibold">Min Conf:</span>
                            <input
                              type="number"
                              min={40}
                              max={95}
                              value={override.minConfidence}
                              onChange={(e) => handleUpdateOverride(idx, 'minConfidence', parseInt(e.target.value || '0', 10))}
                              className="w-12 bg-black/50 border border-white/10 text-xs font-mono font-bold text-blue-400 rounded px-1 text-center"
                            />
                            <span className="text-[10px] text-slate-500">%</span>
                          </div>

                          {/* Priority Routing */}
                          <div className="flex items-center gap-2">
                            <select
                              value={override.priorityRouting}
                              onChange={(e) => handleUpdateOverride(idx, 'priorityRouting', e.target.value)}
                              className="bg-[#16181D] border border-white/10 text-[11px] text-slate-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-blue-500"
                            >
                              <option value="Critical SMS & App">Critical SMS & App</option>
                              <option value="Urgent In-App">Urgent In-App</option>
                              <option value="Daily Digest">Daily Digest</option>
                            </select>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* TAB 3: CHANNELS & ESCALATION */}
          {activeTab === 'channels' && (
            <div className="bg-[#16181D] p-5 rounded-xl border border-white/10 shadow-md space-y-5">
              <div className="border-b border-white/5 pb-3">
                <h3 className="text-sm font-bold text-white">Alert Delivery Channels & Escalation Matrix</h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Route safety signals across multiple communication mediums based on severity and HSE leadership role.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* In-App Notifications */}
                <div className="p-4 rounded-xl bg-[#09090B] border border-white/5 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      <div className="w-8 h-8 rounded-lg bg-blue-600/10 text-blue-400 flex items-center justify-center border border-blue-500/20">
                        <Bell className="w-4 h-4" />
                      </div>
                      <div>
                        <span className="text-xs font-bold text-white">In-App Live Drawer & Bell</span>
                        <p className="text-[10px] text-slate-400">Real-time alerts with direct link to causal graphs</p>
                      </div>
                    </div>
                    <input
                      type="checkbox"
                      checked={config.channels.inAppAlerts}
                      onChange={(e) => handleUpdate(prev => ({
                        ...prev,
                        channels: { ...prev.channels, inAppAlerts: e.target.checked }
                      }))}
                      className="w-4 h-4 rounded text-blue-600 focus:ring-blue-500"
                    />
                  </div>
                </div>

                {/* Urgent Flash Badge */}
                <div className="p-4 rounded-xl bg-[#09090B] border border-white/5 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      <div className="w-8 h-8 rounded-lg bg-red-600/10 text-red-400 flex items-center justify-center border border-red-500/20">
                        <Zap className="w-4 h-4" />
                      </div>
                      <div>
                        <span className="text-xs font-bold text-white">Emergency Flash Banner</span>
                        <p className="text-[10px] text-slate-400">High-visibility banner for Critical risks (&gt;85% prob)</p>
                      </div>
                    </div>
                    <input
                      type="checkbox"
                      checked={config.channels.urgentBadge}
                      onChange={(e) => handleUpdate(prev => ({
                        ...prev,
                        channels: { ...prev.channels, urgentBadge: e.target.checked }
                      }))}
                      className="w-4 h-4 rounded text-blue-600 focus:ring-blue-500"
                    />
                  </div>
                </div>

                {/* Urgent SMS */}
                <div className="p-4 rounded-xl bg-[#09090B] border border-white/5 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      <div className="w-8 h-8 rounded-lg bg-purple-600/10 text-purple-400 flex items-center justify-center border border-purple-500/20">
                        <Smartphone className="w-4 h-4" />
                      </div>
                      <div>
                        <span className="text-xs font-bold text-white">SMS / PagerDuty Dispatch</span>
                        <p className="text-[10px] text-slate-400">Direct mobile dispatch to {config.userPreferences.phone}</p>
                      </div>
                    </div>
                    <input
                      type="checkbox"
                      checked={config.channels.smsUrgent}
                      onChange={(e) => handleUpdate(prev => ({
                        ...prev,
                        channels: { ...prev.channels, smsUrgent: e.target.checked }
                      }))}
                      className="w-4 h-4 rounded text-blue-600 focus:ring-blue-500"
                    />
                  </div>
                </div>

                {/* Email Executive Digest */}
                <div className="p-4 rounded-xl bg-[#09090B] border border-white/5 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      <div className="w-8 h-8 rounded-lg bg-emerald-600/10 text-emerald-400 flex items-center justify-center border border-emerald-500/20">
                        <Mail className="w-4 h-4" />
                      </div>
                      <div>
                        <span className="text-xs font-bold text-white">Daily Intelligence Briefing</span>
                        <p className="text-[10px] text-slate-400">Automated 07:00 AM summary to {config.userPreferences.email}</p>
                      </div>
                    </div>
                    <input
                      type="checkbox"
                      checked={config.channels.emailDigest}
                      onChange={(e) => handleUpdate(prev => ({
                        ...prev,
                        channels: { ...prev.channels, emailDigest: e.target.checked }
                      }))}
                      className="w-4 h-4 rounded text-blue-600 focus:ring-blue-500"
                    />
                  </div>
                </div>
              </div>

              {/* Quiet Hours Configuration */}
              <div className="mt-4 p-4 rounded-xl bg-[#09090B] border border-white/5 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Clock className="w-4 h-4 text-blue-400" />
                    <div>
                      <span className="text-xs font-bold text-white">Quiet Hours & Off-Shift Suppression</span>
                      <p className="text-[10px] text-slate-400">Suppress Moderate alerts outside operational hours (Critical P1 always delivers)</p>
                    </div>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={config.userPreferences.quietHoursEnabled}
                      onChange={(e) => handleUpdate(prev => ({
                        ...prev,
                        userPreferences: { ...prev.userPreferences, quietHoursEnabled: e.target.checked }
                      }))}
                      className="sr-only peer"
                    />
                    <div className="w-9 h-5 bg-slate-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-blue-600"></div>
                  </label>
                </div>

                {config.userPreferences.quietHoursEnabled && (
                  <div className="flex items-center gap-4 pt-2 border-t border-white/5">
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] text-slate-400">From:</span>
                      <input
                        type="time"
                        value={config.userPreferences.quietHoursStart}
                        onChange={(e) => handleUpdate(prev => ({
                          ...prev,
                          userPreferences: { ...prev.userPreferences, quietHoursStart: e.target.value }
                        }))}
                        className="bg-[#16181D] border border-white/10 text-xs text-white rounded px-2 py-1"
                      />
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] text-slate-400">To:</span>
                      <input
                        type="time"
                        value={config.userPreferences.quietHoursEnd}
                        onChange={(e) => handleUpdate(prev => ({
                          ...prev,
                          userPreferences: { ...prev.userPreferences, quietHoursEnd: e.target.value }
                        }))}
                        className="bg-[#16181D] border border-white/10 text-xs text-white rounded px-2 py-1"
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 4: RECIPIENT PROFILE & OPERATIONAL SCOPE */}
          {activeTab === 'profile' && (
            <div className="bg-[#16181D] p-5 rounded-xl border border-white/10 shadow-md space-y-5">
              <div className="border-b border-white/5 pb-3">
                <h3 className="text-sm font-bold text-white">HSE Manager Profile & Operational Scope</h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Personalize alert headers and target specific operating facilities under your safety oversight.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
                    HSE Recipient Name
                  </label>
                  <input
                    type="text"
                    value={config.userPreferences.recipientName}
                    onChange={(e) => handleUpdate(prev => ({
                      ...prev,
                      userPreferences: { ...prev.userPreferences, recipientName: e.target.value }
                    }))}
                    className="w-full bg-[#09090B] border border-white/10 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
                    Role & Accreditation
                  </label>
                  <input
                    type="text"
                    value={config.userPreferences.recipientRole}
                    onChange={(e) => handleUpdate(prev => ({
                      ...prev,
                      userPreferences: { ...prev.userPreferences, recipientRole: e.target.value }
                    }))}
                    className="w-full bg-[#09090B] border border-white/10 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
                    Notification Email Address
                  </label>
                  <input
                    type="email"
                    value={config.userPreferences.email}
                    onChange={(e) => handleUpdate(prev => ({
                      ...prev,
                      userPreferences: { ...prev.userPreferences, email: e.target.value }
                    }))}
                    className="w-full bg-[#09090B] border border-white/10 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
                    Emergency SMS Mobile
                  </label>
                  <input
                    type="tel"
                    value={config.userPreferences.phone}
                    onChange={(e) => handleUpdate(prev => ({
                      ...prev,
                      userPreferences: { ...prev.userPreferences, phone: e.target.value }
                    }))}
                    className="w-full bg-[#09090B] border border-white/10 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500"
                  />
                </div>
              </div>

              {/* Designated Sites Multi-Select */}
              <div className="pt-2">
                <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-2">
                  <MapPin className="w-3.5 h-3.5 text-blue-400" />
                  Designated Safety Oversight Sites
                </label>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  {SITES_LIST.map((site) => {
                    const isSelected = config.userPreferences.designatedSites.includes(site.name);
                    return (
                      <div
                        key={site.id}
                        onClick={() => handleToggleSite(site.name)}
                        className={`p-3 rounded-lg border cursor-pointer transition-all flex items-start justify-between ${
                          isSelected
                            ? 'bg-blue-600/15 border-blue-500/50 text-white'
                            : 'bg-[#09090B] border-white/5 text-slate-400 hover:bg-white/5'
                        }`}
                      >
                        <div>
                          <p className="text-xs font-bold text-white">{site.name}</p>
                          <p className="text-[10px] text-slate-500 mt-0.5">{site.type}</p>
                        </div>
                        {isSelected && <Check className="w-4 h-4 text-blue-400 shrink-0" />}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right Column: Live Trigger Simulation & Test Engine (4 cols) */}
        <div className="lg:col-span-4 space-y-6">
          
          {/* Live Impact Card */}
          <div className="bg-[#16181D] p-5 rounded-xl border border-white/10 shadow-lg space-y-4 sticky top-20">
            <div className="flex items-center justify-between border-b border-white/5 pb-3">
              <div className="flex items-center gap-2">
                <Activity className="w-4 h-4 text-blue-400" />
                <h3 className="text-xs font-bold text-white uppercase tracking-wider">
                  Live Threshold Simulation
                </h3>
              </div>
              <span className="flex h-2 w-2 relative">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </span>
            </div>

            {/* Impact Metric Banner */}
            <div className="bg-[#09090B] p-4 rounded-xl border border-white/5 text-center space-y-1">
              <div className="text-3xl font-bold font-mono text-white">
                <span className={triggeredCount > 0 ? 'text-red-400' : 'text-emerald-400'}>
                  {triggeredCount}
                </span>
                <span className="text-slate-500 text-lg"> / {risks.length}</span>
              </div>
              <p className="text-xs font-medium text-slate-300">
                Active Operational Risks Meet Alert Criteria
              </p>
              <p className="text-[11px] text-slate-500">
                Based on current probability & confidence sliders
              </p>
            </div>

            {/* Triggered Risks List */}
            <div className="space-y-2 max-h-72 overflow-y-auto custom-scrollbar pr-1">
              <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                Risk Evaluation Breakdown:
              </p>
              {liveEvaluations.map((item) => (
                <div
                  key={item.riskId}
                  onClick={() => onSelectRisk && onSelectRisk(item.riskId)}
                  className={`p-2.5 rounded-lg border text-xs transition-all cursor-pointer ${
                    item.isTriggered
                      ? 'bg-red-950/20 border-red-500/30 hover:border-red-500/60'
                      : 'bg-[#09090B] border-white/5 hover:border-white/15 opacity-60'
                  }`}
                >
                  <div className="flex items-start justify-between gap-1.5">
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className={`w-2 h-2 rounded-full shrink-0 ${item.isTriggered ? 'bg-red-400 animate-pulse' : 'bg-slate-600'}`} />
                        <span className="font-semibold text-white truncate text-[11px]">
                          {item.title}
                        </span>
                      </div>
                      <div className="text-[10px] text-slate-400 mt-0.5 font-mono">
                        {item.category} • {item.site}
                      </div>
                    </div>
                    <span className="text-[10px] font-mono shrink-0 px-1.5 py-0.5 rounded bg-black/40 text-slate-300 border border-white/5">
                      {item.probability}% Prob
                    </span>
                  </div>

                  {item.isTriggered ? (
                    <div className="mt-1.5 pt-1.5 border-t border-red-500/20 text-[10px] text-red-300">
                      ⚠️ {item.triggerReasons[0]}
                    </div>
                  ) : (
                    <div className="mt-1 text-[10px] text-slate-500">
                      Below trigger gate ({item.probability}% vs threshold)
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* Direct Trigger Simulation Button */}
            <button
              onClick={handleRunEvaluation}
              className="w-full py-2.5 px-3 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold transition-all shadow-md shadow-blue-600/30 flex items-center justify-center gap-2"
            >
              <Zap className="w-3.5 h-3.5" />
              <span>Evaluate & Trigger Notifications</span>
            </button>
          </div>

        </div>

      </div>
    </div>
  );
};
