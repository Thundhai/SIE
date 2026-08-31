import React, { useState, useMemo, useEffect } from 'react';
import { 
  Search, 
  X, 
  BrainCircuit, 
  BookOpen, 
  ShieldAlert, 
  ArrowRight,
  Database,
  Tag
} from 'lucide-react';
import { EmergingRisk, KnowledgeDocument, InterventionItem } from '../types';

interface GlobalSearchModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectRisk: (riskId: string) => void;
  onSelectDoc: (docId: string) => void;
  onSelectIntervention: (intId: string) => void;
  risks: EmergingRisk[];
  documents: KnowledgeDocument[];
  interventions: InterventionItem[];
}

export const GlobalSearchModal: React.FC<GlobalSearchModalProps> = ({
  isOpen,
  onClose,
  onSelectRisk,
  onSelectDoc,
  onSelectIntervention,
  risks,
  documents,
  interventions
}) => {
  const [query, setQuery] = useState('');

  // Keyboard shortcut Esc
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  const searchResults = useMemo(() => {
    if (!query.trim()) return { risks: [], docs: [], interventions: [] };
    const q = query.toLowerCase();

    const matchedRisks = risks.filter(
      r => r.title.toLowerCase().includes(q) ||
           r.category.toLowerCase().includes(q) ||
           r.mainDriver.toLowerCase().includes(q) ||
           r.location.toLowerCase().includes(q)
    );

    const matchedDocs = documents.filter(
      d => d.title.toLowerCase().includes(q) ||
           d.source.toLowerCase().includes(q) ||
           d.documentCode.toLowerCase().includes(q) ||
           d.topics.some(t => t.toLowerCase().includes(q))
    );

    const matchedInterventions = interventions.filter(
      i => i.title.toLowerCase().includes(q) ||
           i.reason.toLowerCase().includes(q) ||
           i.targetRiskCategory.toLowerCase().includes(q)
    );

    return { risks: matchedRisks, docs: matchedDocs, interventions: matchedInterventions };
  }, [query, risks, documents, interventions]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 px-4 bg-black/70 backdrop-blur-sm animate-in fade-in">
      <div className="w-full max-w-2xl bg-[#16181D] border border-white/10 rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[80vh]">
        {/* Input Bar */}
        <div className="flex items-center gap-3 px-4 py-3.5 border-b border-white/5 bg-[#0F1117]">
          <Search className="w-5 h-5 text-blue-400 shrink-0" />
          <input
            type="text"
            placeholder="Search emerging risks, knowledge standards, evidence codes (e.g. OBS-1021, LOLER, Lifting)..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
            className="w-full bg-transparent text-sm text-slate-100 placeholder-slate-500 focus:outline-none"
          />
          {query && (
            <button onClick={() => setQuery('')} className="text-slate-400 hover:text-slate-200">
              <X className="w-4 h-4" />
            </button>
          )}
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-black/40 text-slate-400 border border-white/10">
            ESC
          </span>
        </div>

        {/* Results Body */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar">
          {!query.trim() ? (
            <div className="py-8 text-center text-slate-500 text-xs">
              <p className="font-medium text-slate-400 mb-2">Quick Suggested Searches:</p>
              <div className="flex flex-wrap justify-center gap-2 max-w-md mx-auto">
                {['Lifting Operations', 'LOLER 1998', 'OBS-1021', 'Vehicle Movement', 'Process Safety', 'OSHA Cranes'].map((tag) => (
                  <button
                    key={tag}
                    onClick={() => setQuery(tag)}
                    className="px-2.5 py-1 rounded-md bg-white/5 hover:bg-white/10 border border-white/5 text-slate-300 text-xs transition-colors"
                  >
                    {tag}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <>
              {/* Emerging Risks */}
              {searchResults.risks.length > 0 && (
                <div>
                  <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <BrainCircuit className="w-3.5 h-3.5 text-red-400" />
                    Emerging Risk Signals ({searchResults.risks.length})
                  </div>
                  <div className="space-y-1.5">
                    {searchResults.risks.map((risk) => (
                      <div
                        key={risk.id}
                        onClick={() => {
                          onSelectRisk(risk.id);
                          onClose();
                        }}
                        className="p-2.5 rounded-lg bg-[#09090B] hover:bg-white/5 border border-white/5 hover:border-blue-500/40 cursor-pointer transition-all flex items-center justify-between group"
                      >
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-semibold text-slate-100 group-hover:text-blue-300">
                              {risk.category} — {risk.title}
                            </span>
                            <span className={`text-[10px] font-mono px-1.5 py-0.2 rounded ${
                              risk.level === 'High' ? 'bg-red-950/60 text-red-400 border border-red-800/60' : 'bg-amber-950/60 text-amber-400 border border-amber-800/60'
                            }`}>
                              {risk.probability}% Prob
                            </span>
                          </div>
                          <p className="text-[11px] text-slate-400 line-clamp-1 mt-0.5">{risk.mainDriver}</p>
                        </div>
                        <ArrowRight className="w-4 h-4 text-slate-500 group-hover:text-blue-400 transition-transform group-hover:translate-x-1" />
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Knowledge Documents */}
              {searchResults.docs.length > 0 && (
                <div>
                  <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <BookOpen className="w-3.5 h-3.5 text-blue-400" />
                    Verified Knowledge & Standards ({searchResults.docs.length})
                  </div>
                  <div className="space-y-1.5">
                    {searchResults.docs.map((doc) => (
                      <div
                        key={doc.id}
                        onClick={() => {
                          onSelectDoc(doc.id);
                          onClose();
                        }}
                        className="p-2.5 rounded-lg bg-[#09090B] hover:bg-white/5 border border-white/5 hover:border-blue-500/40 cursor-pointer transition-all flex items-center justify-between group"
                      >
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-semibold text-slate-100 group-hover:text-blue-300">
                              {doc.source} — {doc.documentCode}
                            </span>
                            <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-emerald-950/60 text-emerald-400 border border-emerald-800/60">
                              {doc.verification}
                            </span>
                          </div>
                          <p className="text-[11px] text-slate-300 line-clamp-1 mt-0.5">{doc.title}</p>
                        </div>
                        <ArrowRight className="w-4 h-4 text-slate-500 group-hover:text-blue-400 transition-transform group-hover:translate-x-1" />
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Interventions */}
              {searchResults.interventions.length > 0 && (
                <div>
                  <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <ShieldAlert className="w-3.5 h-3.5 text-amber-400" />
                    Safety Interventions ({searchResults.interventions.length})
                  </div>
                  <div className="space-y-1.5">
                    {searchResults.interventions.map((intv) => (
                      <div
                        key={intv.id}
                        onClick={() => {
                          onSelectIntervention(intv.id);
                          onClose();
                        }}
                        className="p-2.5 rounded-lg bg-[#09090B] hover:bg-white/5 border border-white/5 hover:border-amber-500/40 cursor-pointer transition-all flex items-center justify-between group"
                      >
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-semibold text-slate-100 group-hover:text-amber-300">
                              {intv.title}
                            </span>
                            <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-amber-950/60 text-amber-400 border border-amber-800/60">
                              {intv.priority}
                            </span>
                          </div>
                          <p className="text-[11px] text-slate-400 line-clamp-1 mt-0.5">{intv.reason}</p>
                        </div>
                        <ArrowRight className="w-4 h-4 text-slate-500 group-hover:text-amber-400 transition-transform group-hover:translate-x-1" />
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {searchResults.risks.length === 0 && searchResults.docs.length === 0 && searchResults.interventions.length === 0 && (
                <div className="py-8 text-center text-slate-400 text-xs">
                  No matching intelligence or knowledge items found for &ldquo;{query}&rdquo;.
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-2 bg-[#0F1117] border-t border-white/5 flex items-center justify-between text-[11px] text-slate-500">
          <span>Navigate with ↵ to open</span>
          <span>Safelytic Intelligence Engine</span>
        </div>
      </div>
    </div>
  );
};

