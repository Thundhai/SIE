import React, { useState } from 'react';
import { 
  Cpu, 
  Send, 
  BrainCircuit, 
  FileText, 
  ExternalLink, 
  ShieldAlert, 
  CheckCircle2, 
  CornerDownLeft,
  User,
  BookOpen,
  ArrowRight,
  Database,
  Globe2,
  Building2,
  MapPin,
  Calendar,
  Layers,
  Sparkles,
  Activity,
  AlertTriangle,
  FileCheck2,
  Scale,
  ShieldCheck,
  Zap,
  ChevronRight
} from 'lucide-react';
import { AssistantChatMessage } from '../types';
import { INITIAL_CHAT_MESSAGES } from '../mockData';

interface AIAssistantViewProps {
  onOpenEvidence: (evidence: any) => void;
  onNavigateToInterventions: () => void;
  onNavigateToAnalysis?: (riskId?: string) => void;
  onNavigateToChallenge?: (riskId?: string) => void;
  currentSite?: string;
  currentTimeRange?: string;
  initialPrompt?: string;
}

export const AIAssistantView: React.FC<AIAssistantViewProps> = ({
  onOpenEvidence,
  onNavigateToInterventions,
  onNavigateToAnalysis,
  onNavigateToChallenge,
  currentSite = 'Lagos Operations',
  currentTimeRange = 'Last 90 Days',
  initialPrompt
}) => {
  const [messages, setMessages] = useState<AssistantChatMessage[]>(INITIAL_CHAT_MESSAGES);
  const [inputValue, setInputValue] = useState(initialPrompt || '');
  const [isGenerating, setIsGenerating] = useState(false);

  const starterPrompts = [
    "Summarize the top safety priorities across Lagos Operations today.",
    "What are our leading indicators for lifting operations this month?",
    "What OSHA standards apply to high-pressure flange bolt torque verification?",
    "Evaluate the causal chain for Yard 4 rigging non-conformances."
  ];

  const handleSendMessage = (promptText?: string) => {
    const textToSend = promptText || inputValue;
    if (!textToSend.trim()) return;

    const userMsg: AssistantChatMessage = {
      id: `USR-${Date.now()}`,
      sender: 'user',
      text: textToSend,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    setMessages(prev => [...prev, userMsg]);
    setInputValue('');
    setIsGenerating(true);

    // Grounded intelligence engine synthesis
    setTimeout(() => {
      let botResponse: AssistantChatMessage;

      if (textToSend.toLowerCase().includes('priority') || textToSend.toLowerCase().includes('lagos') || textToSend.toLowerCase().includes('today')) {
        botResponse = {
          id: `BOT-${Date.now()}`,
          sender: 'assistant',
          text: `### Synthesized Safety Intelligence Assessment: Lagos Operations

Cross-referencing 24 internal records across Yard 4 and Pier 2 against 6 statutory safety frameworks:

1. **Primary Critical Exposure: Heavy Lifting Operations (Risk Score: 78% / High)**
   - Precursor anomaly index elevated (+14% 30-day velocity).
   - 3 overdue corrective actions on sling recertification and tag-line protocol adherence.
   - High subcontractor turnover (18%) identified on Pier 2 heavy lift corridor.

2. **Secondary Exposure: Gas Compression Train B Integrity (Risk Score: 69% / High)**
   - Micro-vibration acoustic resonance detected at 142 Hz on header flange.
   - Soap bubble sniff tests confirmed 40 ppm trace hydrocarbon background reading.

3. **Prescribed Priority Interventions:**
   - Execute active campaign **INT-LIFT-2026-01**: Mandatory quarantine of uninspected spreader beams & pre-lift tag-line verification.
   - Schedule ultrasonic torque verification on Train B Skid flange B-104 bolts.`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          intelligenceContext: {
            orgRecords: 24,
            externalKnowledgeSources: 6,
            historicalAnalysisDays: 90,
            predictiveModelsCount: 3
          },
          evidenceUsed: {
            organizationEvidence: [
              '14 proactive observation logs (OBS-1021, OBS-1044)',
              '1 high-potential near-miss report (NM-203: load swing during wind shear)',
              '3 overdue rigging certification tickets (CAPA-4912, CAPA-4918)'
            ],
            externalKnowledge: [
              'HSE UK L113 (LOLER 1998 Regulation 8 & 9 Approved Code of Practice)',
              'OSHA 1926 Subpart CC (Cranes & Derricks in Construction)',
              'API 570 5th Ed (Piping Inspection Code § 7.3 Flange Torquing)'
            ],
            analyticalResults: [
              'Bayesian Causal Directed Acyclic Graph (DAG) convergence score: 0.88',
              '+14% 30-day precursor surge index exceeding statistical control baseline',
              '95% confidence interval [71% - 84%] on 30-day dropped object probability'
            ]
          },
          relatedRiskId: 'RISK-LIFT-01',
          citations: [
            { id: 'OBS-1021', title: 'Tag line absence on 12-ton turbine casing lift', type: 'Observation', severity: 'High', date: '12 Aug 2026', details: 'Tag line not utilized during load alignment near live manifold.' },
            { id: 'HSE-L113', title: 'HSE Safe Use of Lifting Equipment L113', type: 'Regulation', severity: 'Regulatory', date: '2026', details: 'Statutory guidance on LOLER 1998 Regulation 8: Organization of lifting operations.' }
          ]
        };
      } else if (textToSend.toLowerCase().includes('osha') || textToSend.toLowerCase().includes('flange') || textToSend.toLowerCase().includes('standard') || textToSend.toLowerCase().includes('torque')) {
        botResponse = {
          id: `BOT-${Date.now()}`,
          sender: 'assistant',
          text: `### Statutory Knowledge & Mechanical Integrity Synthesis

Applying **OSHA 1910.119 (Process Safety Management § 119(j))** and **ASME PCC-1 (Guidelines for Pressure Boundary Bolted Flange Joint Assembly)**:

1. **Mandatory Bolting & Torquing Protocol:**
   - Flange bolt pre-load must follow documented engineering torque tables with calibrated hydraulic tensioners.
   - Gasket alignment and seating face inspection are mandatory prior to torquing sequence.

2. **Quality Assurance & Verification Gates:**
   - 100% QA/QC sign-off required on all ASME Class 600+ hydrocarbon joints.
   - Torque stamp verification and digital work-pack filing required prior to system de-isolation.`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          intelligenceContext: {
            orgRecords: 18,
            externalKnowledgeSources: 4,
            historicalAnalysisDays: 90,
            predictiveModelsCount: 2
          },
          evidenceUsed: {
            organizationEvidence: [
              'INS-409 (Flange B-104 micro-bubble weeping on 6 o-clock bolt segment)',
              'CMMS Work Order WO-4409 (Deferred preventive torque check on Train B)'
            ],
            externalKnowledge: [
              'OSHA 1910.119(j) Mechanical Integrity Inspection Procedures',
              'ASME PCC-1 Appendix F: Torque Verification Protocols',
              'API 570 § 7.3: Flange Bolt Torquing & Acoustic Monitoring Protocols'
            ],
            analyticalResults: [
              'Acoustic resonance anomaly score: 0.76 (elevated 142 Hz harmonic trace)',
              'Loss-of-containment probability estimated at 69% prior to intervention'
            ]
          },
          relatedRiskId: 'RISK-PS-03',
          citations: [
            { id: 'OSHA-1910-119', title: 'OSHA Process Safety Management Standard', type: 'Regulation', severity: 'Mandatory', date: '2026', details: '29 CFR 1910.119(j) Mechanical Integrity inspection procedures.' },
            { id: 'ASME-PCC1', title: 'ASME PCC-1 Bolted Flange Joint Assembly', type: 'Engineering Standard', severity: 'Best Practice', date: '2026', details: 'Appendix F: Torque Verification protocols.' }
          ]
        };
      } else {
        botResponse = {
          id: `BOT-${Date.now()}`,
          sender: 'assistant',
          text: `### Operational Intelligence Query Synthesis

Analysis regarding: **"${textToSend}"**

- **Correlated Leading Factors**: High contractor mobilization velocity directly increases procedural non-conformance probability in high-hazard zones.
- **Evidence-Based Mitigations**: Enforce pre-task Dynamic Risk Assessments (DRA) and verify supervisor presence during critical lift windows.`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          intelligenceContext: {
            orgRecords: 16,
            externalKnowledgeSources: 5,
            historicalAnalysisDays: 90,
            predictiveModelsCount: 2
          },
          evidenceUsed: {
            organizationEvidence: [
              'OBS-1044 (Unsafe sling angle exceeding 60-degree safe envelope)',
              'ACT-884 (Master Rigging Register color-coding recertification backlog)'
            ],
            externalKnowledge: [
              'HSE UK L113 (LOLER 1998 Regulation 8 Planning of Lifting Operations)',
              'ISO 45001:2018 Clause 8.1.4 (Contractor Safety Management)'
            ],
            analyticalResults: [
              'Bayesian model correlation factor: 0.82 between contractor turnover and near-miss frequency',
              '90-day baseline trend indicates +12% risk slope without targeted campaign'
            ]
          },
          relatedRiskId: 'RISK-LIFT-01',
          citations: [
            { id: 'OBS-1044', title: 'Unsafe sling angle on pipe bundle lift', type: 'Observation', severity: 'Medium', date: '18 Aug 2026', details: 'Sling angle exceeded 60 degrees without engineering exemption.' }
          ]
        };
      }

      setMessages(prev => [...prev, botResponse]);
      setIsGenerating(false);
    }, 600);
  };

  return (
    <div className="h-[calc(100vh-140px)] flex flex-col space-y-4 animate-in fade-in duration-200">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-3 shrink-0">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
              <Cpu className="w-5 h-5 text-cyan-400" />
              <span>SIE Intelligence Assistant</span>
            </h1>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-300 border border-cyan-800 font-semibold">
              Conversational Engine Interface
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Interactive analytical interface directly querying SIE's causal Bayesian graphs, verified statutory standards, and tenant telemetry.
          </p>
        </div>

        <div className="flex items-center gap-2 text-xs text-slate-400 font-mono">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-slate-300">Engine: <strong>Causal Synthesis v4.6</strong></span>
        </div>
      </div>

      {/* CONTEXT BAR */}
      <div className="p-2.5 px-3.5 rounded-xl bg-slate-900/95 border border-slate-800 text-xs shrink-0 shadow-sm">
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5 font-mono text-[11px]">
          {/* Organization */}
          <div className="flex items-center gap-2 min-w-0">
            <Building2 className="w-3.5 h-3.5 text-slate-400 shrink-0" />
            <div className="truncate">
              <span className="text-slate-400 block text-[9px] uppercase">Organization</span>
              <span className="text-slate-200 font-semibold truncate block">Demo Energy Ltd</span>
            </div>
          </div>

          {/* Site */}
          <div className="flex items-center gap-2 min-w-0">
            <MapPin className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
            <div className="truncate">
              <span className="text-slate-400 block text-[9px] uppercase">Site</span>
              <span className="text-cyan-300 font-semibold truncate block">{currentSite}</span>
            </div>
          </div>

          {/* Time period */}
          <div className="flex items-center gap-2 min-w-0">
            <Calendar className="w-3.5 h-3.5 text-amber-400 shrink-0" />
            <div className="truncate">
              <span className="text-slate-400 block text-[9px] uppercase">Time Period</span>
              <span className="text-slate-200 font-semibold truncate block">{currentTimeRange}</span>
            </div>
          </div>

          {/* Data sources */}
          <div className="flex items-center gap-2 min-w-0">
            <Database className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
            <div className="truncate">
              <span className="text-slate-400 block text-[9px] uppercase">Data Sources</span>
              <span className="text-emerald-300 font-semibold truncate block">6 Active Connectors</span>
            </div>
          </div>

          {/* Knowledge sources */}
          <div className="flex items-center gap-2 min-w-0">
            <Globe2 className="w-3.5 h-3.5 text-blue-400 shrink-0" />
            <div className="truncate">
              <span className="text-slate-400 block text-[9px] uppercase">Knowledge Sources</span>
              <span className="text-blue-300 font-semibold truncate block">436 Verified Standards</span>
            </div>
          </div>

          {/* Prediction engine status */}
          <div className="flex items-center gap-2 min-w-0">
            <Activity className="w-3.5 h-3.5 text-purple-400 shrink-0" />
            <div className="truncate">
              <span className="text-slate-400 block text-[9px] uppercase">Engine Status</span>
              <span className="text-purple-300 font-semibold truncate block">Online & Calibrated</span>
            </div>
          </div>
        </div>
      </div>

      {/* Chat Messages Body */}
      <div className="flex-1 overflow-y-auto space-y-5 pr-2">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex items-start gap-3 ${
              msg.sender === 'user' ? 'justify-end' : 'justify-start'
            }`}
          >
            {msg.sender === 'assistant' && (
              <div className="w-8 h-8 rounded-lg bg-cyan-950 border border-cyan-800 text-cyan-400 flex items-center justify-center shrink-0 mt-1 shadow">
                <Cpu className="w-4 h-4" />
              </div>
            )}

            <div
              className={`max-w-3xl rounded-xl p-4 text-xs leading-relaxed space-y-4 ${
                msg.sender === 'user'
                  ? 'bg-cyan-600 text-white font-medium rounded-tr-none shadow'
                  : 'bg-slate-900/95 border border-slate-800 text-slate-200 rounded-tl-none shadow-md'
              }`}
            >
              {/* SECTION: Intelligence Context (Visible before assistant answer) */}
              {msg.sender === 'assistant' && msg.intelligenceContext && (
                <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-mono uppercase text-cyan-400 font-bold flex items-center gap-1.5">
                      <Sparkles className="w-3 h-3 text-cyan-400" />
                      <span>Intelligence Context</span>
                    </span>
                    <span className="text-[10px] font-mono text-slate-500">
                      Telemetry & Graph Grounding
                    </span>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px] font-mono pt-1">
                    <div className="p-2 rounded bg-slate-900/80 border border-slate-800/80">
                      <span className="text-[10px] text-slate-400 block">Organization Data</span>
                      <strong className="text-cyan-300 font-bold text-xs">{msg.intelligenceContext.orgRecords} records</strong>
                    </div>
                    <div className="p-2 rounded bg-slate-900/80 border border-slate-800/80">
                      <span className="text-[10px] text-slate-400 block">External Knowledge</span>
                      <strong className="text-blue-300 font-bold text-xs">{msg.intelligenceContext.externalKnowledgeSources} verified sources</strong>
                    </div>
                    <div className="p-2 rounded bg-slate-900/80 border border-slate-800/80">
                      <span className="text-[10px] text-slate-400 block">Historical Analysis</span>
                      <strong className="text-amber-300 font-bold text-xs">{msg.intelligenceContext.historicalAnalysisDays} days</strong>
                    </div>
                    <div className="p-2 rounded bg-slate-900/80 border border-slate-800/80">
                      <span className="text-[10px] text-slate-400 block">Predictive Models</span>
                      <strong className="text-purple-300 font-bold text-xs">{msg.intelligenceContext.predictiveModelsCount} active</strong>
                    </div>
                  </div>
                </div>
              )}

              {/* Message text formatted with markdown linebreaks */}
              <div className="whitespace-pre-line leading-relaxed text-slate-200">
                {msg.text}
              </div>

              {/* SECTION: Evidence Used */}
              {msg.sender === 'assistant' && msg.evidenceUsed && (
                <div className="p-3.5 rounded-lg bg-slate-950/90 border border-slate-800/90 space-y-3">
                  <div className="flex items-center justify-between border-b border-slate-800/80 pb-1.5">
                    <span className="text-[10px] font-mono uppercase text-emerald-400 font-bold flex items-center gap-1.5">
                      <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                      <span>Evidence Used</span>
                    </span>
                    <span className="text-[10px] font-mono text-emerald-300/80 font-medium">
                      Verifiable Provenance
                    </span>
                  </div>

                  <div className="space-y-2 text-xs">
                    {/* Organization Evidence */}
                    <div>
                      <span className="text-[10px] font-mono uppercase text-cyan-400 font-semibold block mb-1">
                        Organization Evidence:
                      </span>
                      <ul className="text-[11px] text-slate-300 space-y-0.5 list-disc list-inside">
                        {msg.evidenceUsed.organizationEvidence.map((item, i) => (
                          <li key={i}>{item}</li>
                        ))}
                      </ul>
                    </div>

                    {/* External Knowledge */}
                    <div>
                      <span className="text-[10px] font-mono uppercase text-blue-400 font-semibold block mb-1">
                        External Knowledge:
                      </span>
                      <ul className="text-[11px] text-slate-300 space-y-0.5 list-disc list-inside">
                        {msg.evidenceUsed.externalKnowledge.map((item, i) => (
                          <li key={i}>{item}</li>
                        ))}
                      </ul>
                    </div>

                    {/* Analytical Results */}
                    <div>
                      <span className="text-[10px] font-mono uppercase text-purple-400 font-semibold block mb-1">
                        Analytical Results:
                      </span>
                      <ul className="text-[11px] text-slate-300 space-y-0.5 list-disc list-inside">
                        {msg.evidenceUsed.analyticalResults.map((item, i) => (
                          <li key={i}>{item}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              )}

              {/* ACTION BUTTONS */}
              {msg.sender === 'assistant' && (
                <div className="pt-2 flex flex-wrap items-center gap-2 border-t border-slate-800/80">
                  <button
                    onClick={() => {
                      if (msg.citations && msg.citations.length > 0) {
                        onOpenEvidence(msg.citations[0]);
                      } else {
                        onOpenEvidence({
                          id: 'OBS-1021',
                          title: 'Yard 4 Lifting Non-Conformance Evidence Pack',
                          type: 'Observation Package',
                          severity: 'High',
                          date: 'Current Window',
                          details: 'Synthesized evidence pack backing this intelligence finding.'
                        });
                      }
                    }}
                    className="px-2.5 py-1.5 rounded-lg bg-slate-950 hover:bg-slate-800 border border-slate-700 hover:border-cyan-500 text-cyan-300 text-[11px] font-mono font-semibold transition-colors flex items-center gap-1.5 shadow-sm"
                  >
                    <BookOpen className="w-3 h-3 text-cyan-400" />
                    <span>View Evidence</span>
                  </button>

                  <button
                    onClick={() => onNavigateToAnalysis?.(msg.relatedRiskId || 'RISK-LIFT-01')}
                    className="px-2.5 py-1.5 rounded-lg bg-slate-950 hover:bg-slate-800 border border-slate-700 hover:border-purple-500 text-purple-300 text-[11px] font-mono font-semibold transition-colors flex items-center gap-1.5 shadow-sm"
                  >
                    <Activity className="w-3 h-3 text-purple-400" />
                    <span>View Analysis</span>
                  </button>

                  <button
                    onClick={() => onNavigateToChallenge?.(msg.relatedRiskId || 'RISK-LIFT-01')}
                    className="px-2.5 py-1.5 rounded-lg bg-slate-950 hover:bg-slate-800 border border-slate-700 hover:border-amber-500 text-amber-300 text-[11px] font-mono font-semibold transition-colors flex items-center gap-1.5 shadow-sm"
                  >
                    <Scale className="w-3 h-3 text-amber-400" />
                    <span>Challenge Finding</span>
                  </button>

                  <button
                    onClick={onNavigateToInterventions}
                    className="px-2.5 py-1.5 rounded-lg bg-emerald-950 hover:bg-emerald-900 border border-emerald-700 hover:border-emerald-500 text-emerald-200 text-[11px] font-mono font-semibold transition-colors flex items-center gap-1.5 shadow-sm"
                  >
                    <Zap className="w-3 h-3 text-emerald-400" />
                    <span>Create Intervention</span>
                  </button>
                </div>
              )}

              {/* Existing Citations Box if available */}
              {msg.citations && msg.citations.length > 0 && (
                <div className="pt-2 space-y-1.5">
                  <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block flex items-center gap-1">
                    <FileCheck2 className="w-3 h-3 text-cyan-400" />
                    <span>Linked Grounding Citations:</span>
                  </span>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {msg.citations.map((cit) => (
                      <button
                        key={cit.id}
                        onClick={() => onOpenEvidence(cit)}
                        className="p-2 rounded bg-slate-950/80 hover:bg-slate-800 border border-slate-800 text-left transition-colors flex items-start justify-between gap-1 group"
                      >
                        <div className="min-w-0">
                          <span className="text-[10px] font-mono text-cyan-400 font-bold block">{cit.id}</span>
                          <span className="text-[11px] text-slate-200 font-medium truncate block">{cit.title}</span>
                          <span className="text-[10px] text-slate-500">{cit.type} • {cit.date}</span>
                        </div>
                        <ExternalLink className="w-3 h-3 text-slate-500 group-hover:text-cyan-400 shrink-0 mt-0.5" />
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <div className="text-[10px] font-mono text-slate-500 text-right pt-1">
                {msg.timestamp}
              </div>
            </div>

            {msg.sender === 'user' && (
              <div className="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 text-slate-200 flex items-center justify-center shrink-0 mt-1 shadow">
                <User className="w-4 h-4" />
              </div>
            )}
          </div>
        ))}

        {isGenerating && (
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-cyan-950 border border-cyan-800 text-cyan-400 flex items-center justify-center">
              <BrainCircuit className="w-4 h-4 animate-spin" />
            </div>
            <div className="p-3 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-400 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
              <span>Querying verified knowledge base and synthesizing telemetry...</span>
            </div>
          </div>
        )}
      </div>

      {/* Starter Prompts Strip */}
      <div className="space-y-2 pt-2 shrink-0">
        <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
          Analytical Query Templates:
        </span>
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          {starterPrompts.map((prompt, idx) => (
            <button
              key={idx}
              onClick={() => handleSendMessage(prompt)}
              className="px-3 py-1.5 rounded-lg bg-slate-900/90 hover:bg-slate-800 border border-slate-800 hover:border-cyan-700/50 text-slate-300 text-xs whitespace-nowrap transition-colors flex items-center gap-1.5"
            >
              <Cpu className="w-3 h-3 text-cyan-400 shrink-0" />
              <span>{prompt}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Prompt Input Box */}
      <div className="p-3 rounded-xl bg-slate-900 border border-slate-800 shrink-0 flex items-center gap-2 shadow-sm">
        <input
          type="text"
          placeholder="Query SIE on emerging risk trajectories, causal factors, standards, or interventions..."
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSendMessage();
            }
          }}
          className="flex-1 bg-transparent text-xs text-slate-100 placeholder-slate-500 focus:outline-none px-2 font-medium"
        />
        <button
          onClick={() => handleSendMessage()}
          disabled={!inputValue.trim() || isGenerating}
          className="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white text-xs font-semibold shadow transition-colors flex items-center gap-1.5 shrink-0"
        >
          <span>Query Engine</span>
          <CornerDownLeft className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
};

