import React from 'react';
import { 
  Workflow, 
  Sparkles, 
  BrainCircuit, 
  UserCheck, 
  ShieldAlert, 
  TrendingUp, 
  BookOpen, 
  Database, 
  CheckCircle2, 
  ArrowRight,
  Clock,
  RotateCcw,
  Zap
} from 'lucide-react';
import { LEARNING_ACTIVITY_TIMELINE } from '../mockData';

export const IntelligenceLearningView: React.FC = () => {
  const pipelineSteps = [
    { step: 1, title: 'Knowledge', desc: 'Statutory rules & peer-reviewed standards', icon: BookOpen, color: 'text-cyan-400', bg: 'bg-cyan-950/80 border-cyan-800' },
    { step: 2, title: 'Analysis', desc: 'Continuous causal synthesis & sensor fusion', icon: Zap, color: 'text-blue-400', bg: 'bg-blue-950/80 border-blue-800' },
    { step: 3, title: 'Prediction', desc: 'Probability & exposure forecasting', icon: BrainCircuit, color: 'text-purple-400', bg: 'bg-purple-950/80 border-purple-800' },
    { step: 4, title: 'Recommendation', desc: 'Targeted field safety interventions', icon: ShieldAlert, color: 'text-amber-400', bg: 'bg-amber-950/80 border-amber-800' },
    { step: 5, title: 'Intervention', desc: 'Execution of toolboxes & engineering controls', icon: UserCheck, color: 'text-emerald-400', bg: 'bg-emerald-950/80 border-emerald-800' },
    { step: 6, title: 'Outcome', desc: 'Post-intervention telemetry & metrics shift', icon: TrendingUp, color: 'text-rose-400', bg: 'bg-rose-950/80 border-rose-800' },
    { step: 7, title: 'Learning', desc: 'Recalibration of Bayesian network weights', icon: RotateCcw, color: 'text-cyan-300', bg: 'bg-cyan-900/80 border-cyan-600' }
  ];

  return (
    <div className="space-y-6 animate-in fade-in duration-200">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl sm:text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
              <Workflow className="w-6 h-6 text-purple-400" />
              <span>Intelligence Learning</span>
            </h1>
            <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-purple-950 text-purple-300 border border-purple-800">
              Closed-Loop Recalibration
            </span>
          </div>
          <p className="text-xs sm:text-sm text-slate-400 mt-1 max-w-3xl leading-relaxed">
            Continuous Bayesian parameter recalibration and causal graph refinement without black-box drift.
          </p>
        </div>
      </div>

      {/* Principle Banner: How SIE Learns */}
      <div className="p-6 rounded-xl bg-slate-900/90 border border-slate-800 space-y-4">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-cyan-400" />
          <h2 className="text-sm font-bold text-white uppercase tracking-wider">
            How SIE Continuously Learns (Not Generic LLM Fine-Tuning)
          </h2>
        </div>
        <p className="text-xs text-slate-300 leading-relaxed max-w-4xl">
          Unlike general-purpose conversational LLMs, Safelytic Intelligence Engine uses an auditable, deterministic Bayesian safety learning architecture. The system continuously refines its predictive sensitivity through four verified feedback loops:
        </p>

        {/* 4 Pillars Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 pt-2">
          <div className="p-4 rounded-lg bg-slate-950/70 border border-slate-800 space-y-2">
            <div className="flex items-center gap-2 text-xs font-bold text-cyan-300">
              <BookOpen className="w-4 h-4 text-cyan-400" />
              <span>1. External Knowledge</span>
            </div>
            <p className="text-[11px] text-slate-400 leading-relaxed">
              Ingestion of newly published statutory standards, OSHA alerts, HSE UK guidance, and academic incident forensics.
            </p>
          </div>

          <div className="p-4 rounded-lg bg-slate-950/70 border border-slate-800 space-y-2">
            <div className="flex items-center gap-2 text-xs font-bold text-emerald-300">
              <Database className="w-4 h-4 text-emerald-400" />
              <span>2. Organization Data</span>
            </div>
            <p className="text-[11px] text-slate-400 leading-relaxed">
              Empirical field evidence: observations, near misses, equipment inspection failures, and contractor training compliance.
            </p>
          </div>

          <div className="p-4 rounded-lg bg-slate-950/70 border border-slate-800 space-y-2">
            <div className="flex items-center gap-2 text-xs font-bold text-purple-300">
              <UserCheck className="w-4 h-4 text-purple-400" />
              <span>3. Expert Feedback</span>
            </div>
            <p className="text-[11px] text-slate-400 leading-relaxed">
              CMIOSH and HSE Directors validating, challenging, or refining causal drivers and model risk factor weights.
            </p>
          </div>

          <div className="p-4 rounded-lg bg-slate-950/70 border border-slate-800 space-y-2">
            <div className="flex items-center gap-2 text-xs font-bold text-amber-300">
              <TrendingUp className="w-4 h-4 text-amber-400" />
              <span>4. Intervention Outcomes</span>
            </div>
            <p className="text-[11px] text-slate-400 leading-relaxed">
              Measuring what actually happened after a safety campaign was deployed to confirm or correct causal predictions.
            </p>
          </div>
        </div>
      </div>

      {/* Visual Pipeline (Knowledge -> Analysis -> Prediction -> Recommendation -> Intervention -> Outcome -> Learning) */}
      <div className="p-6 rounded-xl bg-slate-900/90 border border-slate-800 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <Workflow className="w-4 h-4 text-cyan-400" />
              <span>Closed-Loop Safety Intelligence Pipeline</span>
            </h3>
            <p className="text-[11px] text-slate-400">Deterministic lifecycle from raw multi-source ingestion to parameter reinforcement</p>
          </div>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
            Loop Frequency: Real-Time
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2.5 pt-2">
          {pipelineSteps.map((step, idx) => {
            const Icon = step.icon;
            return (
              <div key={step.step} className="relative flex flex-col">
                <div className={`p-3.5 rounded-lg border flex-1 flex flex-col justify-between ${step.bg}`}>
                  <div>
                    <div className="flex items-center justify-between text-[10px] font-mono mb-2">
                      <span className="font-bold text-slate-300">STEP 0{step.step}</span>
                      <Icon className={`w-4 h-4 ${step.color}`} />
                    </div>
                    <h4 className="text-xs font-bold text-white">{step.title}</h4>
                    <p className="text-[10px] text-slate-300 mt-1 leading-snug">{step.desc}</p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 4 Summary Stat Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 text-center">
          <span className="text-[10px] uppercase font-semibold text-slate-400">Knowledge Items Ingested</span>
          <div className="text-2xl font-extrabold text-cyan-400 font-mono mt-1">12,842</div>
          <span className="text-[10px] text-slate-500">436 Verified Sources</span>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 text-center">
          <span className="text-[10px] uppercase font-semibold text-slate-400">Expert Feedback Inputs</span>
          <div className="text-2xl font-extrabold text-purple-400 font-mono mt-1">419</div>
          <span className="text-[10px] text-slate-500">HSE Director Validations</span>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 text-center">
          <span className="text-[10px] uppercase font-semibold text-slate-400">Validated Predictions</span>
          <div className="text-2xl font-extrabold text-emerald-400 font-mono mt-1">88.4%</div>
          <span className="text-[10px] text-emerald-400 font-medium">Precision Accuracy</span>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 text-center">
          <span className="text-[10px] uppercase font-semibold text-slate-400">Intervention Outcomes Logged</span>
          <div className="text-2xl font-extrabold text-amber-400 font-mono mt-1">92</div>
          <span className="text-[10px] text-slate-500">Closed-Loop Evaluated</span>
        </div>
      </div>

      {/* AI Learning Activity Timeline */}
      <div className="p-6 rounded-xl bg-slate-900/90 border border-slate-800 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <Clock className="w-4 h-4 text-cyan-400" />
              <span>AI Learning Activity & Recalibration Timeline</span>
            </h3>
            <p className="text-[11px] text-slate-400">Audit log of model parameter shifts triggered by human expert reviews and intervention results</p>
          </div>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
            Immutable Audit Trail
          </span>
        </div>

        <div className="space-y-3">
          {LEARNING_ACTIVITY_TIMELINE.map((item) => (
            <div
              key={item.id}
              className="p-4 rounded-lg bg-slate-950/70 border border-slate-800 text-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3"
            >
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className={`text-[10px] font-mono px-2 py-0.5 rounded font-bold ${
                    item.category === 'Expert Feedback'
                      ? 'bg-purple-950 text-purple-300 border border-purple-800'
                      : item.category === 'Intervention Outcome'
                      ? 'bg-amber-950 text-amber-300 border border-amber-800'
                      : item.category === 'Validated Prediction'
                      ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                      : 'bg-cyan-950 text-cyan-300 border border-cyan-800'
                  }`}>
                    {item.category}
                  </span>
                  <span className="font-semibold text-slate-200">{item.title}</span>
                </div>
                <p className="text-[11px] text-slate-400 leading-relaxed">{item.description}</p>
                <div className="text-[10px] text-slate-500 flex items-center gap-2 pt-0.5">
                  <span>System Effect: <strong className="text-slate-300">{item.systemEffect}</strong></span>
                </div>
              </div>

              <div className="text-right shrink-0">
                <span className="text-xs font-mono font-bold text-cyan-400 block">{item.impactWeightDelta}</span>
                <span className="text-[10px] font-mono text-slate-500">{item.timestamp}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
