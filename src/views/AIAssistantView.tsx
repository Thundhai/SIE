import React, { useState } from 'react';
import { 
  Sparkles, 
  Send, 
  BrainCircuit, 
  FileText, 
  ExternalLink, 
  ShieldAlert, 
  CheckCircle2, 
  CornerDownLeft,
  Bot,
  User,
  BookOpen,
  ArrowRight,
  Database,
  HelpCircle
} from 'lucide-react';
import { AssistantChatMessage } from '../types';
import { INITIAL_CHAT_MESSAGES } from '../mockData';

interface AIAssistantViewProps {
  onOpenEvidence: (evidence: any) => void;
  onNavigateToInterventions: () => void;
  initialPrompt?: string;
}

export const AIAssistantView: React.FC<AIAssistantViewProps> = ({
  onOpenEvidence,
  onNavigateToInterventions,
  initialPrompt
}) => {
  const [messages, setMessages] = useState<AssistantChatMessage[]>(INITIAL_CHAT_MESSAGES);
  const [inputValue, setInputValue] = useState(initialPrompt || '');
  const [isGenerating, setIsGenerating] = useState(false);

  const starterPrompts = [
    "Summarize the top safety priorities across Lagos Operations today.",
    "What are our leading indicators for lifting operations this month?",
    "What OSHA standards apply to high-pressure flange bolt torque verification?",
    "Generate a draft toolbox talk outline for wind-surge crane operations."
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

    // Simulate intelligent grounded response
    setTimeout(() => {
      let botResponse: AssistantChatMessage;

      if (textToSend.toLowerCase().includes('priority') || textToSend.toLowerCase().includes('lagos')) {
        botResponse = {
          id: `BOT-${Date.now()}`,
          sender: 'assistant',
          text: `Here is the current synthesized safety executive briefing for **Lagos Operations** (Confidence: 84%):

1. **Primary Critical Watchpoint: Lifting Operations (Risk Score: 78% / High)**
   - Observation rate has increased by +28% over 30 days.
   - 3 overdue corrective actions regarding sling certification and tag line adherence.
   - Ground wind shear exceeding 18 knots forecast for Thursday.

2. **Secondary Watchpoint: Process Safety & Flange Integrity (Risk Score: 69%)**
   - 4 overdue valve packings in Gas Compression Train B.

3. **Recommended Immediate Action:**
   - Execute the active **Targeted Lifting Safety Campaign (INT-LIFT-2026-01)**.
   - Issue mandatory supervisor verification on all modular lifts >10T.`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          citations: [
            { id: 'OBS-1021', title: 'Tag line absence on 12-ton turbine casing lift', type: 'Observation', severity: 'High', date: '12 Aug 2026', details: 'Tag line not utilized during load alignment near live manifold.' },
            { id: 'HSE-L113', title: 'HSE Safe Use of Lifting Equipment L113', type: 'Regulation', severity: 'Regulatory', date: '2026', details: 'Statutory guidance on LOLER 1998 Regulation 8: Organization of lifting operations.' }
          ]
        };
      } else if (textToSend.toLowerCase().includes('osha') || textToSend.toLowerCase().includes('flange') || textToSend.toLowerCase().includes('standard')) {
        botResponse = {
          id: `BOT-${Date.now()}`,
          sender: 'assistant',
          text: `Based on **OSHA 1910.119 (Process Safety Management of Highly Hazardous Chemicals)** and **ASME PCC-1 (Guidelines for Pressure Boundary Bolted Flange Joint Assembly)**:

1. **Mechanical Integrity Requirements:**
   - Flange bolt torque must adhere to documented engineering torque tables with calibrated hydraulic tensioners.
   - Gasket seating and alignment must be inspected prior to torquing sequence.

2. **Inspection & Verification Protocol:**
   - 100% QA/QC signoff required on all ASME Class 600+ hydrocarbon joints.
   - Tagging and torque stamp verification must be filed in the digital work pack prior to system pressurization.`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          citations: [
            { id: 'OSHA-1910-119', title: 'OSHA Process Safety Management Standard', type: 'Regulation', severity: 'Mandatory', date: '2026', details: '29 CFR 1910.119(j) Mechanical Integrity inspection procedures.' },
            { id: 'ASME-PCC1', title: 'ASME PCC-1 Bolted Flange Joint Assembly', type: 'Engineering Standard', severity: 'Best Practice', date: '2026', details: 'Appendix F: Torque Verification protocols.' }
          ]
        };
      } else {
        botResponse = {
          id: `BOT-${Date.now()}`,
          sender: 'assistant',
          text: `### Specialized HSE Intelligence Synthesis

Regarding **"${textToSend}"**:

**Key Findings:**
- Cross-referencing 1,284 internal observation records and 436 verified statutory standards.
- Current field data indicates high correlation between rapid mobilization schedules and minor procedural deviations.

**Evidence-Based Mitigations:**
- Implement dedicated pre-task dynamic risk assessments (DRA).
- Ensure toolbox talk reinforces line-of-fire awareness and 100% barrier management.`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
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
              <Sparkles className="w-5 h-5 text-cyan-400" />
              <span>AI Safety Assistant</span>
            </h1>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-300 border border-cyan-800">
              Grounded in Safety Evidence
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Real-time HSE co-pilot querying organization telemetry, incident history, and 436 verified regulatory knowledge sources.
          </p>
        </div>

        <div className="flex items-center gap-2 text-xs text-slate-400 font-mono">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span>Model: SIE Causal Co-Pilot v4</span>
        </div>
      </div>

      {/* Chat Messages Body */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-2">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex items-start gap-3 ${
              msg.sender === 'user' ? 'justify-end' : 'justify-start'
            }`}
          >
            {msg.sender === 'assistant' && (
              <div className="w-8 h-8 rounded-lg bg-cyan-950 border border-cyan-800 text-cyan-400 flex items-center justify-center shrink-0 mt-1">
                <BrainCircuit className="w-4 h-4" />
              </div>
            )}

            <div
              className={`max-w-2xl rounded-xl p-4 text-xs leading-relaxed space-y-3 ${
                msg.sender === 'user'
                  ? 'bg-cyan-600 text-white font-medium rounded-tr-none'
                  : 'bg-slate-900/95 border border-slate-800 text-slate-200 rounded-tl-none shadow-md'
              }`}
            >
              {/* Message text formatted with markdown linebreaks */}
              <div className="whitespace-pre-line">
                {msg.text}
              </div>

              {/* Citations Box */}
              {msg.citations && msg.citations.length > 0 && (
                <div className="pt-3 border-t border-slate-800/80 space-y-2">
                  <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block flex items-center gap-1.5">
                    <BookOpen className="w-3 h-3 text-cyan-400" />
                    <span>Evidence & Verified Knowledge Base:</span>
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

              <div className="text-[10px] font-mono text-slate-400 text-right">
                {msg.timestamp}
              </div>
            </div>

            {msg.sender === 'user' && (
              <div className="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 text-slate-200 flex items-center justify-center shrink-0 mt-1">
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
          Recommended Safety Prompts:
        </span>
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          {starterPrompts.map((prompt, idx) => (
            <button
              key={idx}
              onClick={() => handleSendMessage(prompt)}
              className="px-3 py-1.5 rounded-lg bg-slate-900/90 hover:bg-slate-800 border border-slate-800 hover:border-cyan-700/50 text-slate-300 text-xs whitespace-nowrap transition-colors flex items-center gap-1.5"
            >
              <Sparkles className="w-3 h-3 text-cyan-400 shrink-0" />
              <span>{prompt}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Prompt Input Box */}
      <div className="p-3 rounded-xl bg-slate-900 border border-slate-800 shrink-0 flex items-center gap-2">
        <input
          type="text"
          placeholder="Ask SIE about emerging risks, regulations, root causes, or intervention strategies..."
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSendMessage();
            }
          }}
          className="flex-1 bg-transparent text-xs text-slate-100 placeholder-slate-500 focus:outline-none px-2"
        />
        <button
          onClick={() => handleSendMessage()}
          disabled={!inputValue.trim() || isGenerating}
          className="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white text-xs font-semibold shadow transition-colors flex items-center gap-1.5 shrink-0"
        >
          <span>Send</span>
          <CornerDownLeft className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
};
