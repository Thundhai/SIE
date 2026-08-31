import React, { useState } from 'react';
import { 
  ArrowLeft, 
  Sparkles, 
  UserCheck, 
  BarChart2, 
  RotateCcw,
  Check
} from 'lucide-react';
import { 
  ResponsiveContainer, 
  AreaChart, 
  Area, 
  XAxis, 
  YAxis, 
  Tooltip, 
  CartesianGrid, 
  Legend 
} from 'recharts';
import { INTERVENTIONS } from '../mockData';

interface OutcomeLearningViewProps {
  interventionId: string;
  onBack: () => void;
  onSelectIntervention: (id: string) => void;
}

export const OutcomeLearningView: React.FC<OutcomeLearningViewProps> = ({
  interventionId,
  onBack,
  onSelectIntervention
}) => {
  const currentIntervention = INTERVENTIONS.find(i => i.id === interventionId) || INTERVENTIONS[0];
  const outcome = currentIntervention.outcomeData || {
    baselineRisk: 78,
    currentRisk: 51,
    observationShift: '-24%',
    complianceShift: '+18%',
    nearMissShift: '-33%',
    verdict: 'Likely Effective' as const,
    confidence: 76,
    evaluationPeriod: 'Post-intervention Day 18 Evaluation',
    expertAssessments: []
  };

  const [expertRating, setExpertRating] = useState<'Effective' | 'Partially Effective' | 'Not Effective'>('Effective');
  const [expertComment, setExpertComment] = useState('');
  const [assessmentSubmitted, setAssessmentSubmitted] = useState(false);

  // Generate 30-day trajectory progression based on baseline to current
  const trajectoryChartData = [
    { day: 'Day -10', riskScore: outcome.baselineRisk, compliance: 62 },
    { day: 'Day -5', riskScore: outcome.baselineRisk + 2, compliance: 60 },
    { day: 'Day 0 (Rollout)', riskScore: outcome.baselineRisk, compliance: 65 },
    { day: 'Day 5', riskScore: Math.round(outcome.baselineRisk - 6), compliance: 72 },
    { day: 'Day 10', riskScore: Math.round(outcome.baselineRisk - 14), compliance: 78 },
    { day: 'Day 15', riskScore: Math.round(outcome.baselineRisk - 21), compliance: 82 },
    { day: 'Day 20', riskScore: outcome.currentRisk, compliance: 85 },
    { day: 'Day 30 (Projected)', riskScore: Math.max(30, outcome.currentRisk - 5), compliance: 88 }
  ];

  const handleSubmitAssessment = (e: React.FormEvent) => {
    e.preventDefault();
    setAssessmentSubmitted(true);
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-200">
      {/* Top Navigation */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-4">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <span>Intervention Center</span>
              <span>/</span>
              <span className="text-slate-300 font-semibold">Effectiveness & Closed-Loop Learning</span>
            </div>
            <h1 className="text-xl sm:text-2xl font-bold text-white tracking-tight mt-0.5">
              Intervention Outcome Analysis
            </h1>
          </div>
        </div>

        {/* Case Switcher */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">Intervention Case:</span>
          <select
            value={currentIntervention.id}
            onChange={(e) => onSelectIntervention(e.target.value)}
            className="bg-slate-900 border border-slate-700 text-slate-200 text-xs font-semibold rounded-lg px-3 py-1.5 focus:outline-none focus:border-cyan-500"
          >
            {INTERVENTIONS.filter(i => i.outcomeData).map((i) => (
              <option key={i.id} value={i.id}>
                {i.title} ({i.id})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Case Header Card */}
      <div className="p-6 rounded-xl bg-slate-900/90 border border-slate-800 shadow-xl space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-xs font-mono font-bold px-2.5 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
            {outcome.verdict}
          </span>
          <span className="text-xs text-slate-400 font-mono">ID: {currentIntervention.id}</span>
          <span className="text-xs text-slate-400 font-mono">• Target: {currentIntervention.targetRiskCategory}</span>
          <span className="text-xs text-slate-400 font-mono">• Period: {outcome.evaluationPeriod}</span>
        </div>

        <h2 className="text-lg sm:text-xl font-bold text-white tracking-tight">
          {currentIntervention.title}
        </h2>
        <p className="text-xs sm:text-sm text-slate-300 leading-relaxed max-w-4xl">
          Deployed in response to elevated probability surge ({outcome.baselineRisk}%). Evaluated across 30 days of continuous field observations, near miss logs, and operational telemetry.
        </p>
      </div>

      {/* Outcome KPI Stats Bar (Screen 9 Requirements) */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {/* Baseline vs Current Risk */}
        <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 flex flex-col justify-between">
          <span className="text-[10px] uppercase font-semibold text-slate-400">Risk Probability Shift</span>
          <div className="flex items-baseline gap-2 mt-1">
            <span className="text-slate-400 line-through font-mono text-sm">{outcome.baselineRisk}%</span>
            <span className="text-2xl font-extrabold text-emerald-400 font-mono">{outcome.currentRisk}%</span>
          </div>
          <span className="text-[11px] text-emerald-400 font-mono mt-1 font-bold">
            {outcome.currentRisk - outcome.baselineRisk}% Total Risk Reduction
          </span>
        </div>

        {/* Observation Frequency */}
        <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 flex flex-col justify-between">
          <span className="text-[10px] uppercase font-semibold text-slate-400">Observation Frequency</span>
          <div className="text-2xl font-extrabold text-emerald-400 font-mono mt-1">
            {outcome.observationShift}
          </div>
          <span className="text-[11px] text-slate-400">Defect rate dropping</span>
        </div>

        {/* Control Compliance */}
        <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 flex flex-col justify-between">
          <span className="text-[10px] uppercase font-semibold text-slate-400">Control Compliance</span>
          <div className="text-2xl font-extrabold text-cyan-400 font-mono mt-1">
            {outcome.complianceShift}
          </div>
          <span className="text-[11px] text-slate-400">Tag lines & lift plans</span>
        </div>

        {/* Near Miss Frequency */}
        <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 flex flex-col justify-between">
          <span className="text-[10px] uppercase font-semibold text-slate-400">Near Miss Frequency</span>
          <div className="text-2xl font-extrabold text-emerald-400 font-mono mt-1">
            {outcome.nearMissShift}
          </div>
          <span className="text-[11px] text-slate-400">0 High-Potential events</span>
        </div>
      </div>

      {/* AI Finding Banner: Did the intervention work? */}
      <div className="p-5 sm:p-6 rounded-xl bg-gradient-to-r from-slate-900 via-slate-900 to-emerald-950/40 border border-emerald-700/60 shadow-xl space-y-2">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-emerald-400" />
          <h3 className="text-sm font-bold text-white">Did the intervention work? — Automated AI Assessment</h3>
          <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
            {outcome.verdict} (Confidence: {outcome.confidence}%)
          </span>
        </div>
        <p className="text-xs sm:text-sm text-slate-200 leading-relaxed">
          The intervention reduced overall risk probability from <strong>{outcome.baselineRisk}%</strong> down to <strong>{outcome.currentRisk}%</strong> ({outcome.currentRisk - outcome.baselineRisk}% reduction), with a <strong>{outcome.observationShift}</strong> decrease in unsafe observations and a <strong>{outcome.complianceShift}</strong> increase in field control compliance.
        </p>
      </div>

      {/* Before vs After 30-Day Trajectory Area Chart */}
      <div className="p-6 rounded-xl bg-slate-900/90 border border-slate-800 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <BarChart2 className="w-4 h-4 text-cyan-400" />
              <span>30-Day Before & After Intervention Trajectory</span>
            </h3>
            <p className="text-[11px] text-slate-400">Comparative progression showing risk score drop following Day 0 campaign rollout</p>
          </div>
          <div className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
            30-Day Daily Logging
          </div>
        </div>

        <div className="h-64 sm:h-72 w-full pt-2">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={trajectoryChartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="riskColor" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#f43f5e" stopOpacity={0.4}/>
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0.05}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="day" stroke="#64748b" fontSize={11} tickLine={false} />
              <YAxis domain={[20, 90]} stroke="#64748b" fontSize={11} tickLine={false} />
              <Tooltip
                contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '8px', fontSize: '12px', color: '#f8fafc' }}
              />
              <Legend wrapperStyle={{ fontSize: '11px', paddingTop: '8px' }} />
              <Area type="monotone" dataKey="riskScore" name="Predictive Risk Score (%)" stroke="#38bdf8" strokeWidth={3} fillOpacity={1} fill="url(#riskColor)" />
              <Area type="monotone" dataKey="compliance" name="Field Control Compliance (%)" stroke="#10b981" strokeWidth={2} fillOpacity={0} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Add Expert Assessment Form (Screen 9 Interactive Closed Loop) */}
      <div className="p-6 rounded-xl bg-slate-900/90 border border-slate-800 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <UserCheck className="w-4 h-4 text-purple-400" />
              <span>Add Expert Assessment (Human-in-the-Loop Feedback)</span>
            </h3>
            <p className="text-[11px] text-slate-400">Calibrates the model&apos;s future prescriptive weights for similar SIMOPS conditions</p>
          </div>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-950 text-purple-300 border border-purple-800">
            Bayesian Weight Recalibration
          </span>
        </div>

        {assessmentSubmitted ? (
          <div className="p-5 rounded-lg bg-emerald-950/40 border border-emerald-800 text-emerald-300 text-xs space-y-2">
            <div className="font-bold flex items-center gap-2 text-sm">
              <Check className="w-4 h-4" />
              <span>Expert Assessment Ingested Successfully!</span>
            </div>
            <p className="text-slate-300">
              The model has incorporated your assessment ({expertRating}) for <strong>{currentIntervention.title}</strong> into its Bayesian causal prior distribution. Future lifting surges will recommend this intervention pattern with +4.2% higher confidence.
            </p>
            <button
              onClick={() => setAssessmentSubmitted(false)}
              className="mt-2 text-xs text-emerald-400 underline font-semibold"
            >
              Edit Assessment
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmitAssessment} className="space-y-4">
            <div>
              <label className="text-xs text-slate-300 font-semibold block mb-2">
                Qualitative Effectiveness Verdict:
              </label>
              <div className="grid grid-cols-3 gap-3">
                {[
                  { value: 'Effective', label: 'Effective', desc: 'Met or exceeded risk reduction goal' },
                  { value: 'Partially Effective', label: 'Partially Effective', desc: 'Shifted some factors, gaps remain' },
                  { value: 'Not Effective', label: 'Not Effective', desc: 'No measurable risk mitigation' }
                ].map((opt) => (
                  <label
                    key={opt.value}
                    className={`p-3 rounded-lg border cursor-pointer transition-all ${
                      expertRating === opt.value
                        ? 'bg-purple-950/50 border-purple-500 ring-1 ring-purple-500/50'
                        : 'bg-slate-950/60 border-slate-800 hover:border-slate-700'
                    }`}
                  >
                    <input
                      type="radio"
                      name="expertRating"
                      value={opt.value}
                      checked={expertRating === opt.value}
                      onChange={(e) => setExpertRating(e.target.value as any)}
                      className="sr-only"
                    />
                    <span className="font-bold text-xs text-white block">{opt.label}</span>
                    <span className="text-[10px] text-slate-400 block mt-0.5">{opt.desc}</span>
                  </label>
                ))}
              </div>
            </div>

            <div>
              <label className="text-xs text-slate-300 font-semibold block mb-1.5">
                Expert Qualitative Observations & Site Constraints:
              </label>
              <textarea
                value={expertComment}
                onChange={(e) => setExpertComment(e.target.value)}
                placeholder="e.g. Dedicated rigging supervision significantly improved compliance during night shifts. Recommend retaining mandatory tag line verification for all modular lifts."
                rows={3}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg p-3 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
              />
            </div>

            <div className="flex justify-end">
              <button
                type="submit"
                className="px-5 py-2.5 rounded-lg bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white text-xs font-semibold shadow-md shadow-purple-900/30 transition-all flex items-center gap-2"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>Submit Expert Assessment & Recalibrate Weights</span>
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};
