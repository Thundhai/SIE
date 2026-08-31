import React, { useState } from 'react';
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
  Zap,
  Layers,
  ShieldCheck,
  AlertTriangle,
  Sliders,
  FileText,
  Filter,
  Info,
  Plus,
  Search,
  Star,
  ThumbsUp,
  Check,
  ExternalLink,
  Activity,
  Cpu,
  Award,
  ArrowDown,
  ChevronRight,
  Send,
  X
} from 'lucide-react';
import { 
  LEARNING_ACTIVITY_TIMELINE,
  KNOWLEDGE_INGESTION_ITEMS,
  PREDICTIVE_MODEL_MODULES,
  EXPERT_FEEDBACK_LEDGER,
  OUTCOME_LEARNING_CASES,
  SAFETY_DATA_METRICS,
  INITIAL_EMERGING_RISKS
} from '../mockData';
import { 
  KnowledgeIngestionItem, 
  PredictiveModelModule, 
  ExpertFeedbackItem, 
  OutcomeLearningRecord 
} from '../types';

export const IntelligenceLearningView: React.FC = () => {
  // State for active mechanism tab
  const [activeTab, setActiveTab] = useState<'all' | 'knowledge' | 'predictive' | 'expert' | 'outcome'>('all');
  
  // Knowledge stream filter
  const [knowledgeCategory, setKnowledgeCategory] = useState<string>('All');
  
  // Closed-loop pipeline active step
  const [activePipelineStep, setActivePipelineStep] = useState<number>(1);

  // Expert feedback interactive modal
  const [isFeedbackModalOpen, setIsFeedbackModalOpen] = useState<boolean>(false);
  const [selectedRiskForFeedback, setSelectedRiskForFeedback] = useState<string>('RISK-LIFT-01');
  const [feedbackActionType, setFeedbackActionType] = useState<'Confirming Prediction' | 'Correcting Prediction' | 'Challenging Assumption' | 'Rating Recommendation'>('Confirming Prediction');
  const [feedbackRating, setFeedbackRating] = useState<number>(5);
  const [feedbackNotes, setFeedbackNotes] = useState<string>('');
  const [feedbackAdjustment, setFeedbackAdjustment] = useState<string>('');
  const [feedbackList, setFeedbackList] = useState<ExpertFeedbackItem[]>(EXPERT_FEEDBACK_LEDGER);
  const [feedbackSubmittedSuccess, setFeedbackSubmittedSuccess] = useState<boolean>(false);

  // Filtered knowledge items
  const filteredKnowledge = knowledgeCategory === 'All'
    ? KNOWLEDGE_INGESTION_ITEMS
    : KNOWLEDGE_INGESTION_ITEMS.filter(k => k.category.toLowerCase().includes(knowledgeCategory.toLowerCase()));

  // 7-Stage Closed-Loop Intelligence Steps
  const closedLoopSteps = [
    {
      step: 1,
      title: 'Data',
      sub: 'Multi-Source Telemetry',
      icon: Database,
      color: 'text-blue-400',
      border: 'border-blue-500/40',
      bg: 'bg-blue-950/40',
      activeBg: 'bg-blue-900/60 border-blue-400 ring-2 ring-blue-500/30',
      inputs: '1,284 safety observations, 142 near misses, 412 inspection reports, 420 msgs/s IoT crane sensor feeds, SAP ERP work orders',
      deliverable: 'Normalized, quality-scored (94% Q-Score) organizational safety telemetry data stream',
      assurance: 'Zero-knowledge tenant isolation & schema validation check'
    },
    {
      step: 2,
      title: 'Analysis',
      sub: 'Causal Synthesis & Norms',
      icon: Zap,
      color: 'text-cyan-400',
      border: 'border-cyan-500/40',
      bg: 'bg-cyan-950/40',
      activeBg: 'bg-cyan-900/60 border-cyan-400 ring-2 ring-cyan-500/30',
      inputs: 'Indexed statutory codes (OSHA, LOLER, API), historical 3-year baseline hazard rates, site spatial graphs',
      deliverable: 'Causal dependency graphs mapping precursor signals to high-consequence failure modes',
      assurance: 'Deterministic causal link verification against verified regulatory benchmarks'
    },
    {
      step: 3,
      title: 'Prediction',
      sub: 'Bayesian Risk Forecasting',
      icon: BrainCircuit,
      color: 'text-purple-400',
      border: 'border-purple-500/40',
      bg: 'bg-purple-950/40',
      activeBg: 'bg-purple-900/60 border-purple-400 ring-2 ring-purple-500/30',
      inputs: 'Precursor velocity slopes, contractor competency passports, SIMOPS congestion density',
      deliverable: 'Quantified probability scores, confidence intervals (95% CI), and emerging hazard trajectories',
      assurance: '91.8% AUC-ROC calibrated predictive sensitivity with transparent factor weights'
    },
    {
      step: 4,
      title: 'Intervention',
      sub: 'Targeted Field Controls',
      icon: ShieldAlert,
      color: 'text-amber-400',
      border: 'border-amber-500/40',
      bg: 'bg-amber-950/40',
      activeBg: 'bg-amber-900/60 border-amber-400 ring-2 ring-amber-500/30',
      inputs: 'Prescriptive safety action templates, engineered barrier hierarchy, responsible duty holders',
      deliverable: 'Targeted field campaigns (e.g. Rigging gear quarantine, auxiliary solar mast lighting, flange torque)',
      assurance: 'Role-assigned accountability workflows with target verification metrics'
    },
    {
      step: 5,
      title: 'Outcome',
      sub: 'Post-Deployment Telemetry',
      icon: TrendingUp,
      color: 'text-rose-400',
      border: 'border-rose-500/40',
      bg: 'bg-rose-950/40',
      activeBg: 'bg-rose-900/60 border-rose-400 ring-2 ring-rose-500/30',
      inputs: 'Field observation shift data, IoT compliance sensors, leading indicator delta tracking',
      deliverable: 'Quantified behavioral & physical shifts (-24% lifting defects, -78% pedestrian lane breaches)',
      assurance: '30-day post-intervention surveillance window with automated drift alarms'
    },
    {
      step: 6,
      title: 'Evaluation',
      sub: 'Effectiveness & Feedback',
      icon: UserCheck,
      color: 'text-emerald-400',
      border: 'border-emerald-500/40',
      bg: 'bg-emerald-950/40',
      activeBg: 'bg-emerald-900/60 border-emerald-400 ring-2 ring-emerald-500/30',
      inputs: 'CMIOSH HSE Director reviews, intervention effectiveness ratings, empirical vs predicted delta',
      deliverable: 'Verified intervention scoring (e.g. 92% Highly Effective) & human confirmation log',
      assurance: 'Mandatory human-in-the-loop expert oversight before model parameter shifts'
    },
    {
      step: 7,
      title: 'Improvement',
      sub: 'Model Parameter Calibration',
      icon: RotateCcw,
      color: 'text-teal-300',
      border: 'border-teal-500/40',
      bg: 'bg-teal-950/40',
      activeBg: 'bg-teal-900/60 border-teal-400 ring-2 ring-teal-500/30',
      inputs: 'Closed-loop Bayesian likelihood matrices, factor weight delta updates, verified knowledge updates',
      deliverable: 'Recalibrated Bayesian network weights (+0.14 confidence) without retraining LLM weights',
      assurance: 'Deterministic parameter tuning preventing black-box model drift'
    }
  ];

  const handleOpenFeedbackModal = () => {
    setFeedbackNotes('');
    setFeedbackAdjustment('');
    setFeedbackSubmittedSuccess(false);
    setIsFeedbackModalOpen(true);
  };

  const handleSubmitFeedback = (e: React.FormEvent) => {
    e.preventDefault();
    const risk = INITIAL_EMERGING_RISKS.find(r => r.id === selectedRiskForFeedback) || INITIAL_EMERGING_RISKS[0];
    const newFeedback: ExpertFeedbackItem = {
      id: `FB-${Math.floor(1000 + Math.random() * 9000)}`,
      expertName: 'Dr. Alistair Vance (Current Session)',
      role: 'Group HSE Assurance Director, CMIOSH',
      actionType: feedbackActionType,
      targetRiskId: risk.id,
      targetRiskTitle: risk.title,
      date: 'Just now',
      notes: feedbackNotes || `Expert review submitted for ${risk.title}. Calibration parameters recorded.`,
      rating: feedbackActionType === 'Rating Recommendation' ? feedbackRating : undefined,
      adjustment: feedbackAdjustment || (feedbackActionType === 'Confirming Prediction' ? '+8% Predictive Factor Weight' : feedbackActionType === 'Correcting Prediction' ? '-14% Risk Prior Adjusted' : 'Assumption Parameter Re-indexed'),
      status: 'Applied to Model',
      isSimulated: true
    };

    setFeedbackList([newFeedback, ...feedbackList]);
    setFeedbackSubmittedSuccess(true);
    setTimeout(() => {
      setIsFeedbackModalOpen(false);
      setFeedbackSubmittedSuccess(false);
    }, 1200);
  };

  return (
    <div className="space-y-7 animate-in fade-in duration-200">
      
      {/* 1. Header Section */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-xl sm:text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
              <Workflow className="w-6 h-6 text-cyan-400" />
              <span>Intelligence Learning &amp; Improvement</span>
            </h1>
            <span className="text-[11px] font-mono px-2.5 py-0.5 rounded-full bg-cyan-950 text-cyan-300 border border-cyan-800 font-bold">
              Multi-Mechanism Learning
            </span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-950/80 text-amber-300 border border-amber-800 font-bold uppercase">
              DEMO / SIMULATED
            </span>
          </div>
          <p className="text-xs sm:text-sm text-slate-400 mt-1 max-w-4xl leading-relaxed">
            Safelytic Intelligence Engine (SIE) continuously refines safety intelligence through four separate, auditable learning loops without ungrounded model drift.
          </p>
        </div>

        <div className="flex items-center gap-2.5 shrink-0">
          <button
            onClick={handleOpenFeedbackModal}
            className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold shadow-lg shadow-purple-900/30 transition-all cursor-pointer"
          >
            <UserCheck className="w-4 h-4" />
            <span>Submit Expert Feedback</span>
          </button>
        </div>
      </div>

      {/* 2. Critical Architecture Principle Banner (MANDATORY DISTINCTION) */}
      <div className="p-5 sm:p-6 rounded-2xl bg-gradient-to-br from-slate-900 via-slate-900 to-cyan-950/40 border border-cyan-500/30 shadow-xl space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-cyan-500/20 pb-3">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
              <Cpu className="w-5 h-5" />
            </div>
            <div>
              <span className="text-[11px] font-mono text-cyan-400 uppercase font-bold tracking-wider block">
                Fundamental AI Architecture Principle
              </span>
              <h2 className="text-sm sm:text-base font-bold text-white">
                &ldquo;Knowledge retrieval, predictive model improvement and language-model behavior are separate mechanisms.&rdquo;
              </h2>
            </div>
          </div>

          <span className="text-[11px] font-mono px-3 py-1 rounded-lg bg-emerald-950/80 text-emerald-300 border border-emerald-800 font-bold self-start md:self-auto">
            Deterministic Safety Governance
          </span>
        </div>

        {/* 3 Pillars Explaining the Distinction */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5 pt-1">
          <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800/80 space-y-1.5">
            <div className="flex items-center gap-2 text-xs font-bold text-cyan-300">
              <BookOpen className="w-4 h-4 text-cyan-400" />
              <span>1. Knowledge Retrieval (RAG)</span>
            </div>
            <p className="text-[11px] text-slate-300 leading-relaxed">
              Continuously indexes statutory codes (OSHA, HSE UK, IMO), research findings, and company SOPs into a verified semantic knowledge base without altering model weights.
            </p>
          </div>

          <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800/80 space-y-1.5">
            <div className="flex items-center gap-2 text-xs font-bold text-purple-300">
              <Sliders className="w-4 h-4 text-purple-400" />
              <span>2. Predictive Model Improvement</span>
            </div>
            <p className="text-[11px] text-slate-300 leading-relaxed">
              Structured field safety data (near-misses, observations, telematics) recalibrates Bayesian network priors, anomaly thresholds, and hazard trajectory coefficients.
            </p>
          </div>

          <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800/80 space-y-1.5">
            <div className="flex items-center gap-2 text-xs font-bold text-emerald-300">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              <span>3. Language Model Behavior</span>
            </div>
            <p className="text-[11px] text-slate-300 leading-relaxed">
              The LLM performs contextual reasoning and natural language synthesis over calibrated model outputs. <strong className="text-slate-100">The LLM itself is NOT automatically retrained after every record.</strong>
            </p>
          </div>
        </div>
      </div>

      {/* 3. VISUAL: Closed-Loop Intelligence Workflow */}
      <div className="p-6 rounded-2xl bg-slate-900/90 border border-slate-800 shadow-xl space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h3 className="text-sm sm:text-base font-bold text-white flex items-center gap-2">
              <RotateCcw className="w-4 h-4 text-cyan-400" />
              <span>Closed-Loop Intelligence Pipeline</span>
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Interactive 7-stage closed-loop lifecycle from raw operational data ingestion to Bayesian parameter improvement
            </p>
          </div>

          <div className="flex items-center gap-2 text-[10px] font-mono text-slate-400">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              Live Closed-Loop Feedback Active
            </span>
          </div>
        </div>

        {/* The 7-Stage Horizontal Pipeline Visual */}
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2.5 pt-2">
          {closedLoopSteps.map((step) => {
            const Icon = step.icon;
            const isActive = activePipelineStep === step.step;
            return (
              <button
                key={step.step}
                onClick={() => setActivePipelineStep(step.step)}
                className={`p-3.5 rounded-xl border text-left transition-all flex flex-col justify-between cursor-pointer group ${
                  isActive ? step.activeBg : `${step.bg} ${step.border} hover:bg-slate-800/80`
                }`}
              >
                <div>
                  <div className="flex items-center justify-between text-[10px] font-mono mb-2">
                    <span className="font-bold text-slate-400">STEP 0{step.step}</span>
                    <Icon className={`w-4 h-4 ${step.color} group-hover:scale-110 transition-transform`} />
                  </div>
                  <h4 className="text-xs font-bold text-white">{step.title}</h4>
                  <p className="text-[10px] text-slate-400 mt-0.5 font-medium leading-snug">{step.sub}</p>
                </div>

                <div className="mt-3 pt-2 border-t border-white/5 flex items-center justify-between text-[9px] font-mono text-slate-400">
                  <span className={isActive ? step.color : 'text-slate-500'}>
                    {isActive ? 'Active Stage' : 'Click to Inspect'}
                  </span>
                  <ChevronRight className={`w-3 h-3 ${isActive ? step.color : 'text-slate-600'}`} />
                </div>
              </button>
            );
          })}
        </div>

        {/* Selected Stage Detail Drawer */}
        {(() => {
          const currentStepObj = closedLoopSteps.find(s => s.step === activePipelineStep) || closedLoopSteps[0];
          const CurrentIcon = currentStepObj.icon;
          return (
            <div className="p-4 sm:p-5 rounded-xl bg-slate-950/80 border border-slate-800 space-y-3 mt-3 animate-in fade-in duration-150">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800/80 pb-2.5">
                <div className="flex items-center gap-2.5">
                  <div className={`p-2 rounded-lg bg-slate-900 border border-slate-800 ${currentStepObj.color}`}>
                    <CurrentIcon className="w-4 h-4" />
                  </div>
                  <div>
                    <span className="text-[10px] font-mono text-slate-400 uppercase font-bold">
                      Stage 0{currentStepObj.step} Architecture Breakdown
                    </span>
                    <h4 className="text-sm font-bold text-white">
                      {currentStepObj.title} — {currentStepObj.sub}
                    </h4>
                  </div>
                </div>

                <span className="text-[10px] font-mono px-2.5 py-1 rounded bg-slate-900 text-slate-300 border border-slate-800">
                  Assurance: {currentStepObj.assurance}
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800/60">
                  <span className="text-[10px] font-mono text-slate-400 uppercase block font-bold mb-1">
                    Telemetry &amp; Knowledge Inputs
                  </span>
                  <p className="text-slate-200 leading-relaxed">{currentStepObj.inputs}</p>
                </div>
                <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800/60">
                  <span className="text-[10px] font-mono text-cyan-400 uppercase block font-bold mb-1">
                    System Process Deliverable
                  </span>
                  <p className="text-slate-200 leading-relaxed">{currentStepObj.deliverable}</p>
                </div>
              </div>
            </div>
          );
        })()}
      </div>

      {/* 4. Tab Navigation for the 4 Distinct Learning Mechanisms */}
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-800 pb-3">
        <button
          onClick={() => setActiveTab('all')}
          className={`px-3.5 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
            activeTab === 'all'
              ? 'bg-slate-800 text-white border border-slate-700 shadow'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
          }`}
        >
          All 4 Learning Mechanisms
        </button>

        <button
          onClick={() => setActiveTab('knowledge')}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
            activeTab === 'knowledge'
              ? 'bg-blue-600/20 text-blue-300 border border-blue-500/40 shadow'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
          }`}
        >
          <BookOpen className="w-3.5 h-3.5 text-blue-400" />
          <span>1. Knowledge Ingestion</span>
          <span className="text-[10px] font-mono bg-blue-950 px-1.5 py-0.2 rounded border border-blue-800">436 Docs</span>
        </button>

        <button
          onClick={() => setActiveTab('predictive')}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
            activeTab === 'predictive'
              ? 'bg-purple-600/20 text-purple-300 border border-purple-500/40 shadow'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
          }`}
        >
          <Sliders className="w-3.5 h-3.5 text-purple-400" />
          <span>2. Predictive Model Learning</span>
          <span className="text-[10px] font-mono bg-purple-950 px-1.5 py-0.2 rounded border border-purple-800">4 Modules</span>
        </button>

        <button
          onClick={() => setActiveTab('expert')}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
            activeTab === 'expert'
              ? 'bg-emerald-600/20 text-emerald-300 border border-emerald-500/40 shadow'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
          }`}
        >
          <UserCheck className="w-3.5 h-3.5 text-emerald-400" />
          <span>3. Expert Feedback</span>
          <span className="text-[10px] font-mono bg-emerald-950 px-1.5 py-0.2 rounded border border-emerald-800">419 Reviews</span>
        </button>

        <button
          onClick={() => setActiveTab('outcome')}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
            activeTab === 'outcome'
              ? 'bg-amber-600/20 text-amber-300 border border-amber-500/40 shadow'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
          }`}
        >
          <TrendingUp className="w-3.5 h-3.5 text-amber-400" />
          <span>4. Outcome Learning</span>
          <span className="text-[10px] font-mono bg-amber-950 px-1.5 py-0.2 rounded border border-amber-800">Closed-Loop</span>
        </button>
      </div>

      {/* =========================================================================
          MECHANISM 1: KNOWLEDGE INGESTION
         ========================================================================= */}
      {(activeTab === 'all' || activeTab === 'knowledge') && (
        <div className="p-6 rounded-2xl bg-slate-900/90 border border-slate-800 shadow-xl space-y-5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800/80 pb-4">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-xl bg-blue-600/15 border border-blue-500/30 text-blue-400">
                <BookOpen className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-mono font-bold text-blue-400 uppercase tracking-wider">
                    Learning Mechanism 01
                  </span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-blue-950 text-blue-300 border border-blue-800 font-bold">
                    Continuous RAG Grounding
                  </span>
                </div>
                <h3 className="text-base sm:text-lg font-bold text-white mt-0.5">
                  Knowledge Ingestion &amp; Regulatory Verification
                </h3>
              </div>
            </div>

            <p className="text-xs text-slate-400 max-w-md">
              SIE continuously adds validated information from regulators, research, industry sources, safety alerts, and organization documents.
            </p>
          </div>

          {/* 3 Status Metric Cards Requested by User */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="p-4 rounded-xl bg-slate-950/80 border border-blue-500/20 text-center">
              <span className="text-[11px] font-mono uppercase text-slate-400 font-semibold block">
                Documents Processed
              </span>
              <div className="text-2xl sm:text-3xl font-extrabold text-blue-400 font-mono mt-1">436</div>
              <span className="text-[10px] text-slate-500 mt-0.5 block">Statutory &amp; Technical Manuals Ingested</span>
            </div>

            <div className="p-4 rounded-xl bg-slate-950/80 border border-purple-500/20 text-center">
              <span className="text-[11px] font-mono uppercase text-slate-400 font-semibold block">
                Sources Verified
              </span>
              <div className="text-2xl sm:text-3xl font-extrabold text-purple-400 font-mono mt-1">52</div>
              <span className="text-[10px] text-slate-500 mt-0.5 block">International Authorities &amp; Institutes</span>
            </div>

            <div className="p-4 rounded-xl bg-slate-950/80 border border-emerald-500/20 text-center">
              <span className="text-[11px] font-mono uppercase text-slate-400 font-semibold block">
                Knowledge Items Added
              </span>
              <div className="text-2xl sm:text-3xl font-extrabold text-emerald-400 font-mono mt-1">12,842</div>
              <span className="text-[10px] text-slate-500 mt-0.5 block">Semantic Rules, Benchmarks &amp; Checkpoints</span>
            </div>
          </div>

          {/* 5 Ingestion Streams Pills Filter */}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <span className="text-xs text-slate-400 font-medium mr-1">Filter Source Streams:</span>
            {['All', 'Regulators', 'Research', 'Industry Sources', 'Safety Alerts', 'Organization Documents'].map((cat) => (
              <button
                key={cat}
                onClick={() => setKnowledgeCategory(cat)}
                className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                  knowledgeCategory === cat
                    ? 'bg-blue-600 text-white shadow'
                    : 'bg-slate-800/80 hover:bg-slate-700 text-slate-300 border border-slate-700'
                }`}
              >
                {cat}
              </button>
            ))}
          </div>

          {/* Knowledge Ingestion Feed Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
            {filteredKnowledge.map((item) => (
              <div
                key={item.id}
                className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 hover:border-blue-500/40 transition-all flex flex-col justify-between space-y-3"
              >
                <div>
                  <div className="flex items-center justify-between text-[10px] font-mono text-slate-400 border-b border-slate-800/80 pb-2">
                    <span className="text-blue-400 font-bold">{item.category}</span>
                    <span className="px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800 font-bold">
                      {item.verificationStatus}
                    </span>
                  </div>

                  <h4 className="text-xs font-bold text-white mt-2.5 line-clamp-2">
                    {item.title}
                  </h4>
                  <p className="text-[10px] text-purple-300 font-mono mt-1">{item.sourceAuthority}</p>

                  <p className="text-[11px] text-slate-300 mt-2 leading-relaxed line-clamp-2">
                    {item.summary}
                  </p>
                </div>

                <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between text-[10px] font-mono text-slate-400">
                  <span className="text-emerald-400 font-bold">+{item.itemsExtracted} Rules Indexed</span>
                  <span>{item.processedDate}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* =========================================================================
          MECHANISM 2: PREDICTIVE MODEL LEARNING
         ========================================================================= */}
      {(activeTab === 'all' || activeTab === 'predictive') && (
        <div className="p-6 rounded-2xl bg-slate-900/90 border border-slate-800 shadow-xl space-y-5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800/80 pb-4">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-xl bg-purple-600/15 border border-purple-500/30 text-purple-400">
                <Sliders className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-mono font-bold text-purple-400 uppercase tracking-wider">
                    Learning Mechanism 02
                  </span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-950 text-purple-300 border border-purple-800 font-bold">
                    Statistical Parameter Calibration
                  </span>
                </div>
                <h3 className="text-base sm:text-lg font-bold text-white mt-0.5">
                  Predictive Model Learning from Structured Safety Data
                </h3>
              </div>
            </div>

            <p className="text-xs text-slate-400 max-w-md">
              Structured safety data (observations, near-misses, IoT sensor telemetry) continuously tunes mathematical risk model parameters and Bayesian network factor priors.
            </p>
          </div>

          {/* Crucial Non-Retraining LLM Notice Banner */}
          <div className="p-3.5 rounded-xl bg-purple-950/30 border border-purple-500/30 text-purple-200 text-xs flex items-start gap-2.5">
            <Info className="w-4 h-4 text-purple-400 shrink-0 mt-0.5" />
            <div className="leading-relaxed">
              <strong className="text-purple-300">Statistical Learning Governance:</strong> Structured safety data recalibrates Bayesian graph probabilities, covariance matrices, and hazard trajectory slopes. 
              <span className="text-white font-medium"> This process does NOT automatically retrain the language model itself after every record</span>, ensuring complete mathematical auditability and preventing conversational hallucinations.
            </div>
          </div>

          {/* 4 Core Predictive Model Examples Requested by User */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {PREDICTIVE_MODEL_MODULES.map((mod) => (
              <div
                key={mod.id}
                className="p-5 rounded-xl bg-slate-950/80 border border-slate-800 hover:border-purple-500/40 transition-all flex flex-col justify-between space-y-4"
              >
                <div>
                  <div className="flex items-center justify-between text-[10px] font-mono border-b border-slate-800/80 pb-2">
                    <span className="font-bold text-purple-400">{mod.id}</span>
                    <span className="text-emerald-400 font-bold">{mod.currentAccuracy}</span>
                  </div>

                  <h4 className="text-sm font-bold text-white mt-2.5 flex items-center gap-2">
                    <Activity className="w-4 h-4 text-purple-400" />
                    <span>{mod.name}</span>
                  </h4>
                  <p className="text-xs text-purple-300/90 font-mono mt-0.5">{mod.tagline}</p>

                  <p className="text-xs text-slate-300 mt-2 leading-relaxed">
                    {mod.description}
                  </p>

                  {/* Input Data Types */}
                  <div className="mt-3 p-2.5 rounded-lg bg-slate-900/80 border border-slate-800/60">
                    <span className="text-[10px] font-mono text-slate-400 uppercase font-bold block mb-1">
                      Structured Safety Data Inputs:
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {mod.inputDataTypes.map((dt, idx) => (
                        <span key={idx} className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                          {dt}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="pt-3 border-t border-slate-800/80 grid grid-cols-2 gap-2 text-[10px] font-mono text-slate-400">
                  <div>
                    <span className="text-slate-500 block">Algorithm:</span>
                    <span className="text-slate-300 truncate block">{mod.algorithmType}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Recalibration:</span>
                    <span className="text-cyan-400 truncate block">{mod.recalibrationMechanism}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* =========================================================================
          MECHANISM 3: EXPERT FEEDBACK
         ========================================================================= */}
      {(activeTab === 'all' || activeTab === 'expert') && (
        <div className="p-6 rounded-2xl bg-slate-900/90 border border-slate-800 shadow-xl space-y-5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800/80 pb-4">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-xl bg-emerald-600/15 border border-emerald-500/30 text-emerald-400">
                <UserCheck className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-mono font-bold text-emerald-400 uppercase tracking-wider">
                    Learning Mechanism 03
                  </span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800 font-bold">
                    Human-in-the-Loop Validation
                  </span>
                </div>
                <h3 className="text-base sm:text-lg font-bold text-white mt-0.5">
                  Expert Feedback &amp; Oversight Ledger
                </h3>
              </div>
            </div>

            <button
              onClick={handleOpenFeedbackModal}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/30 text-xs font-semibold transition-all cursor-pointer shrink-0"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Record HSE Expert Review</span>
            </button>
          </div>

          <p className="text-xs text-slate-300 leading-relaxed">
            HSE professionals (CMIOSH, Process Safety Engineers, Rigging Leads) actively steer the intelligence engine by confirming predictions, correcting likelihood estimates, challenging model assumptions, and rating recommended interventions.
          </p>

          {/* 4 Feedback Modes Summary */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-3 rounded-xl bg-slate-950/70 border border-slate-800 text-center">
              <span className="text-[10px] font-mono uppercase text-slate-400 block font-bold">Confirming</span>
              <span className="text-emerald-400 font-bold text-sm mt-0.5 block font-mono">184 Verified</span>
              <span className="text-[9px] text-slate-500">Validating precursor signals</span>
            </div>
            <div className="p-3 rounded-xl bg-slate-950/70 border border-slate-800 text-center">
              <span className="text-[10px] font-mono uppercase text-slate-400 block font-bold">Correcting</span>
              <span className="text-amber-400 font-bold text-sm mt-0.5 block font-mono">92 Calibrations</span>
              <span className="text-[9px] text-slate-500">Adjusting risk likelihoods</span>
            </div>
            <div className="p-3 rounded-xl bg-slate-950/70 border border-slate-800 text-center">
              <span className="text-[10px] font-mono uppercase text-slate-400 block font-bold">Challenging</span>
              <span className="text-cyan-400 font-bold text-sm mt-0.5 block font-mono">48 Refinements</span>
              <span className="text-[9px] text-slate-500">Testing baseline assumptions</span>
            </div>
            <div className="p-3 rounded-xl bg-slate-950/70 border border-slate-800 text-center">
              <span className="text-[10px] font-mono uppercase text-slate-400 block font-bold">Rating Actions</span>
              <span className="text-purple-400 font-bold text-sm mt-0.5 block font-mono">4.8 / 5.0 Avg</span>
              <span className="text-[9px] text-slate-500">Intervention quality score</span>
            </div>
          </div>

          {/* Live Expert Feedback Cards */}
          <div className="space-y-3 pt-1">
            {feedbackList.map((fb) => (
              <div
                key={fb.id}
                className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 hover:border-emerald-500/30 text-xs flex flex-col md:flex-row md:items-center justify-between gap-4 transition-all"
              >
                <div className="space-y-1.5 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`text-[10px] font-mono px-2 py-0.5 rounded font-bold ${
                      fb.actionType === 'Confirming Prediction'
                        ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                        : fb.actionType === 'Correcting Prediction'
                        ? 'bg-amber-950 text-amber-300 border border-amber-800'
                        : fb.actionType === 'Challenging Assumption'
                        ? 'bg-cyan-950 text-cyan-300 border border-cyan-800'
                        : 'bg-purple-950 text-purple-300 border border-purple-800'
                    }`}>
                      {fb.actionType}
                    </span>

                    <span className="font-bold text-white">{fb.expertName}</span>
                    <span className="text-slate-500 text-[10px] font-mono">• {fb.role}</span>
                  </div>

                  <p className="text-slate-300 leading-relaxed">
                    &ldquo;{fb.notes}&rdquo;
                  </p>

                  <div className="flex flex-wrap items-center gap-3 text-[10px] font-mono text-slate-400 pt-0.5">
                    <span>Target Risk: <strong className="text-slate-300">{fb.targetRiskTitle}</strong></span>
                    {fb.adjustment && (
                      <span className="text-cyan-400 font-bold">Calibration: {fb.adjustment}</span>
                    )}
                    {fb.rating && (
                      <span className="text-amber-300 font-bold flex items-center gap-1">
                        <Star className="w-3 h-3 fill-amber-300" /> {fb.rating} / 5.0
                      </span>
                    )}
                  </div>
                </div>

                <div className="text-right shrink-0 font-mono text-[10px]">
                  <span className="px-2 py-0.5 rounded bg-slate-900 text-emerald-400 border border-slate-800 font-bold block mb-1">
                    {fb.status}
                  </span>
                  <span className="text-slate-500">{fb.date}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* =========================================================================
          MECHANISM 4: OUTCOME LEARNING
         ========================================================================= */}
      {(activeTab === 'all' || activeTab === 'outcome') && (
        <div className="p-6 rounded-2xl bg-slate-900/90 border border-slate-800 shadow-xl space-y-5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800/80 pb-4">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-xl bg-amber-600/15 border border-amber-500/30 text-amber-400">
                <TrendingUp className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-mono font-bold text-amber-400 uppercase tracking-wider">
                    Learning Mechanism 04
                  </span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-800 font-bold">
                    Empirical Closed-Loop Validation
                  </span>
                </div>
                <h3 className="text-base sm:text-lg font-bold text-white mt-0.5">
                  Outcome Learning &amp; Intervention Evaluation
                </h3>
              </div>
            </div>

            <div className="text-xs font-mono text-amber-300 bg-amber-950/60 px-3 py-1 rounded-lg border border-amber-800">
              Prediction → Intervention → Outcome → Effectiveness → Model Evaluation
            </div>
          </div>

          <p className="text-xs text-slate-300 leading-relaxed">
            By tracking actual field outcomes after safety interventions are deployed, SIE evaluates whether causal predictions were correct and recalibrates predictive confidence weights accordingly.
          </p>

          {/* 5-Step Visual Flow Requested by User */}
          <div className="p-4 rounded-xl bg-slate-950/70 border border-slate-800">
            <span className="text-[10px] font-mono text-slate-400 uppercase font-bold block mb-2 text-center">
              The 5-Stage Outcome Evaluation Chain
            </span>
            <div className="flex flex-col md:flex-row items-center justify-between gap-2 text-xs">
              <div className="p-2.5 rounded-lg bg-blue-950/60 border border-blue-800 text-blue-300 text-center w-full">
                <span className="font-bold block">1. Prediction</span>
                <span className="text-[10px] text-slate-400">Forecast hazard exposure</span>
              </div>
              <ArrowRight className="w-4 h-4 text-slate-600 shrink-0 hidden md:block" />
              <ArrowDown className="w-4 h-4 text-slate-600 shrink-0 md:hidden" />

              <div className="p-2.5 rounded-lg bg-purple-950/60 border border-purple-800 text-purple-300 text-center w-full">
                <span className="font-bold block">2. Intervention</span>
                <span className="text-[10px] text-slate-400">Deploy targeted control</span>
              </div>
              <ArrowRight className="w-4 h-4 text-slate-600 shrink-0 hidden md:block" />
              <ArrowDown className="w-4 h-4 text-slate-600 shrink-0 md:hidden" />

              <div className="p-2.5 rounded-lg bg-cyan-950/60 border border-cyan-800 text-cyan-300 text-center w-full">
                <span className="font-bold block">3. Outcome</span>
                <span className="text-[10px] text-slate-400">Measure field delta</span>
              </div>
              <ArrowRight className="w-4 h-4 text-slate-600 shrink-0 hidden md:block" />
              <ArrowDown className="w-4 h-4 text-slate-600 shrink-0 md:hidden" />

              <div className="p-2.5 rounded-lg bg-emerald-950/60 border border-emerald-800 text-emerald-300 text-center w-full">
                <span className="font-bold block">4. Effectiveness</span>
                <span className="text-[10px] text-slate-400">Score practical impact</span>
              </div>
              <ArrowRight className="w-4 h-4 text-slate-600 shrink-0 hidden md:block" />
              <ArrowDown className="w-4 h-4 text-slate-600 shrink-0 md:hidden" />

              <div className="p-2.5 rounded-lg bg-amber-950/60 border border-amber-800 text-amber-300 text-center w-full">
                <span className="font-bold block">5. Model Evaluation</span>
                <span className="text-[10px] text-slate-400">Calibrate Bayesian prior</span>
              </div>
            </div>
          </div>

          {/* Outcome Case Study Cards */}
          <div className="space-y-4">
            {OUTCOME_LEARNING_CASES.map((oc) => (
              <div
                key={oc.id}
                className="p-5 rounded-xl bg-slate-950/80 border border-slate-800 hover:border-amber-500/30 space-y-3 transition-all"
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800/80 pb-2.5">
                  <div>
                    <span className="text-[10px] font-mono text-cyan-400 font-bold">{oc.riskId}</span>
                    <h4 className="text-sm font-bold text-white">{oc.riskTitle}</h4>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-mono px-2.5 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800 font-bold">
                      Effectiveness: {oc.effectiveness}
                    </span>
                    <span className="text-[10px] font-mono text-slate-500">{oc.date}</span>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
                  <div className="p-3 rounded-lg bg-slate-900/70 border border-slate-800/60">
                    <span className="text-[10px] font-mono text-blue-400 uppercase font-bold block mb-1">
                      1. Prediction &amp; Early Warning:
                    </span>
                    <p className="text-slate-300 leading-relaxed">{oc.prediction}</p>
                  </div>

                  <div className="p-3 rounded-lg bg-slate-900/70 border border-slate-800/60">
                    <span className="text-[10px] font-mono text-purple-400 uppercase font-bold block mb-1">
                      2. Prescribed Field Intervention:
                    </span>
                    <p className="text-slate-300 leading-relaxed">{oc.intervention}</p>
                  </div>

                  <div className="p-3 rounded-lg bg-slate-900/70 border border-slate-800/60">
                    <span className="text-[10px] font-mono text-cyan-400 uppercase font-bold block mb-1">
                      3. Measured Field Outcome:
                    </span>
                    <p className="text-slate-300 leading-relaxed">{oc.outcome}</p>
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-emerald-950/20 border border-emerald-500/20 flex items-start gap-2.5 text-xs text-emerald-200">
                  <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                  <div>
                    <strong className="text-emerald-300 font-mono text-[11px] uppercase block">
                      Closed-Loop Model Evaluation &amp; Bayesian Recalibration:
                    </strong>
                    <p className="text-slate-300 mt-0.5">{oc.modelEvaluation}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 5. Immutable Learning & Audit Trail Timeline */}
      <div className="p-6 rounded-2xl bg-slate-900/90 border border-slate-800 shadow-xl space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h3 className="text-sm sm:text-base font-bold text-white flex items-center gap-2">
              <Clock className="w-4 h-4 text-cyan-400" />
              <span>Intelligence Improvement Audit Trail</span>
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Cryptographic, immutable event ledger recording knowledge indexing, human expert reviews, and Bayesian parameter shifts
            </p>
          </div>
          <span className="text-[10px] font-mono px-2.5 py-1 rounded bg-slate-800 text-slate-300 border border-slate-700">
            Immutable Audit Trail • SHA-256 Anchored
          </span>
        </div>

        <div className="space-y-3 pt-1">
          {LEARNING_ACTIVITY_TIMELINE.map((item) => (
            <div
              key={item.id}
              className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 text-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:border-slate-700 transition-all"
            >
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className={`text-[10px] font-mono px-2 py-0.5 rounded font-bold ${
                    item.category === 'Expert Feedback'
                      ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                      : item.category === 'Intervention Outcome'
                      ? 'bg-amber-950 text-amber-300 border border-amber-800'
                      : item.category === 'Validated Prediction'
                      ? 'bg-purple-950 text-purple-300 border border-purple-800'
                      : 'bg-blue-950 text-blue-300 border border-blue-800'
                  }`}>
                    {item.category}
                  </span>
                  <span className="font-bold text-white">{item.title}</span>
                </div>
                <p className="text-[11px] text-slate-300 leading-relaxed">{item.description}</p>
                <div className="text-[10px] text-slate-400 flex items-center gap-2 pt-0.5">
                  <span>System Effect: <strong className="text-cyan-300">{item.systemEffect}</strong></span>
                </div>
              </div>

              <div className="text-right shrink-0 font-mono">
                <span className="text-xs font-bold text-cyan-400 block">{item.impactWeightDelta}</span>
                <span className="text-[10px] text-slate-500">{item.timestamp}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* =========================================================================
          MODAL: SUBMIT EXPERT FEEDBACK / CHALLENGE ASSUMPTIONS
         ========================================================================= */}
      {isFeedbackModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in">
          <div 
            className="w-full max-w-xl bg-[#16181D] border border-white/10 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh] animate-in zoom-in-95"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="p-4 sm:p-5 border-b border-white/10 bg-[#0F1117] flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-xl bg-purple-600/20 text-purple-400 border border-purple-500/30">
                  <UserCheck className="w-5 h-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono font-bold text-white uppercase">Human-in-the-Loop Oversight</span>
                    <span className="text-[10px] font-mono px-2 py-0.2 rounded bg-amber-950 text-amber-300 border border-amber-800 font-bold uppercase">
                      DEMO / SIMULATED
                    </span>
                  </div>
                  <h3 className="text-sm sm:text-base font-bold text-white">
                    Submit Expert Feedback or Challenge Assumptions
                  </h3>
                </div>
              </div>

              <button
                onClick={() => setIsFeedbackModalOpen(false)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Modal Form */}
            <form onSubmit={handleSubmitFeedback} className="p-5 space-y-4 text-xs text-slate-300 overflow-y-auto custom-scrollbar flex-1">
              
              {feedbackSubmittedSuccess ? (
                <div className="p-6 rounded-xl bg-emerald-950/40 border border-emerald-500/40 text-center space-y-2">
                  <CheckCircle2 className="w-8 h-8 text-emerald-400 mx-auto" />
                  <h4 className="text-sm font-bold text-white">Expert Feedback Recorded &amp; Calibrated</h4>
                  <p className="text-xs text-slate-300">
                    Your assessment has been cryptographically logged into the audit trail. Bayesian factor priors have been adjusted.
                  </p>
                </div>
              ) : (
                <>
                  {/* Select Target Emerging Risk */}
                  <div>
                    <label className="block text-[11px] font-mono uppercase font-bold text-slate-400 mb-1">
                      Target Emerging Risk
                    </label>
                    <select
                      value={selectedRiskForFeedback}
                      onChange={(e) => setSelectedRiskForFeedback(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-white text-xs focus:ring-1 focus:ring-purple-500 focus:outline-none"
                    >
                      {INITIAL_EMERGING_RISKS.map((risk) => (
                        <option key={risk.id} value={risk.id}>
                          {risk.id} — {risk.title} ({risk.probability}% Probability)
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Select Action Mode */}
                  <div>
                    <label className="block text-[11px] font-mono uppercase font-bold text-slate-400 mb-1">
                      Expert Review Action Type
                    </label>
                    <div className="grid grid-cols-2 gap-2">
                      {[
                        { type: 'Confirming Prediction', label: '1. Confirm Prediction', desc: 'Validates early-warning accuracy' },
                        { type: 'Correcting Prediction', label: '2. Correct Prediction', desc: 'Adjusts likelihood estimate' },
                        { type: 'Challenging Assumption', label: '3. Challenge Assumption', desc: 'Flags invalid baseline driver' },
                        { type: 'Rating Recommendation', label: '4. Rate Recommendation', desc: 'Scores intervention quality' }
                      ].map((item) => (
                        <button
                          key={item.type}
                          type="button"
                          onClick={() => setFeedbackActionType(item.type as any)}
                          className={`p-2.5 rounded-lg border text-left transition-all cursor-pointer ${
                            feedbackActionType === item.type
                              ? 'bg-purple-950/80 border-purple-500 text-white ring-1 ring-purple-500'
                              : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:bg-slate-800'
                          }`}
                        >
                          <strong className="block text-xs text-white">{item.label}</strong>
                          <span className="text-[10px] text-slate-400">{item.desc}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Rating Slider if Rating Recommendation */}
                  {feedbackActionType === 'Rating Recommendation' && (
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <label className="text-[11px] font-mono uppercase font-bold text-slate-400">
                          Intervention Operational Quality Rating
                        </label>
                        <span className="text-sm font-bold text-amber-300 font-mono flex items-center gap-1">
                          <Star className="w-3.5 h-3.5 fill-amber-300" /> {feedbackRating} / 5.0
                        </span>
                      </div>
                      <input
                        type="range"
                        min="1"
                        max="5"
                        step="0.1"
                        value={feedbackRating}
                        onChange={(e) => setFeedbackRating(parseFloat(e.target.value))}
                        className="w-full accent-amber-400 cursor-pointer"
                      />
                    </div>
                  )}

                  {/* Parameter Adjustment Note */}
                  <div>
                    <label className="block text-[11px] font-mono uppercase font-bold text-slate-400 mb-1">
                      Proposed Factor Weight / Parameter Adjustment
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. +10% Weight to Rigging Gear Inspection, or -15% Likelihood Prior"
                      value={feedbackAdjustment}
                      onChange={(e) => setFeedbackAdjustment(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-white text-xs focus:ring-1 focus:ring-purple-500 focus:outline-none"
                    />
                  </div>

                  {/* Expert Notes */}
                  <div>
                    <label className="block text-[11px] font-mono uppercase font-bold text-slate-400 mb-1">
                      Expert Review Rationale &amp; Field Observations
                    </label>
                    <textarea
                      rows={3}
                      placeholder="Enter field observations, CMIOSH inspection results, or engineering controls verified on site..."
                      value={feedbackNotes}
                      onChange={(e) => setFeedbackNotes(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-white text-xs focus:ring-1 focus:ring-purple-500 focus:outline-none resize-none"
                    />
                  </div>
                </>
              )}

              {/* Modal Footer Buttons */}
              <div className="pt-3 border-t border-white/10 flex items-center justify-end gap-2.5">
                <button
                  type="button"
                  onClick={() => setIsFeedbackModalOpen(false)}
                  className="px-4 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-slate-300 text-xs font-semibold transition-colors"
                >
                  Cancel
                </button>
                {!feedbackSubmittedSuccess && (
                  <button
                    type="submit"
                    className="flex items-center gap-2 px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold shadow-lg shadow-purple-900/30 transition-all cursor-pointer"
                  >
                    <Send className="w-3.5 h-3.5" />
                    <span>Apply Calibration &amp; Save</span>
                  </button>
                )}
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
