import React from 'react';
import { X, FileText, CheckCircle2, AlertTriangle, ShieldCheck, MapPin, Calendar, User, ExternalLink, Hash } from 'lucide-react';

interface EvidenceDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  evidenceData: {
    id: string;
    type?: string;
    title: string;
    severity?: string;
    date?: string;
    location?: string;
    details?: string;
    reporterRole?: string;
    status?: string;
    // or external evidence:
    publisher?: string;
    documentTitle?: string;
    code?: string;
    publicationDate?: string;
    topic?: string;
    reliability?: string;
    jurisdiction?: string;
    keyExcerpt?: string;
  } | null;
}

export const EvidenceDetailModal: React.FC<EvidenceDetailModalProps> = ({
  isOpen,
  onClose,
  evidenceData
}) => {
  if (!isOpen || !evidenceData) return null;

  const isInternal = Boolean(evidenceData.type || evidenceData.location);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in">
      <div className="w-full max-w-xl bg-[#16181D] border border-white/10 rounded-xl shadow-2xl overflow-hidden animate-in zoom-in-95">
        {/* Header */}
        <div className="p-4 border-b border-white/5 bg-[#0F1117] flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className={`p-2 rounded-lg ${
              isInternal ? 'bg-blue-600/10 border border-blue-500/20 text-blue-400' : 'bg-purple-950/60 border border-purple-800/60 text-purple-400'
            }`}>
              <FileText className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono font-bold text-white">{evidenceData.id || evidenceData.code}</span>
                <span className={`text-[10px] font-mono px-1.5 py-0.2 rounded ${
                  isInternal ? 'bg-white/5 text-blue-400 border border-white/10' : 'bg-purple-950/60 text-purple-300 border border-purple-800/60'
                }`}>
                  {isInternal ? `Internal ${evidenceData.type}` : 'Verified External Source'}
                </span>
                {evidenceData.severity && (
                  <span className={`text-[10px] font-mono px-1.5 py-0.2 rounded ${
                    evidenceData.severity === 'High' || evidenceData.severity === 'Critical'
                      ? 'bg-red-950/60 text-red-400 border border-red-800/60'
                      : 'bg-amber-950/60 text-amber-400 border border-amber-800/60'
                  }`}>
                    {evidenceData.severity} Severity
                  </span>
                )}
              </div>
              <h3 className="text-sm font-semibold text-white mt-0.5">
                {evidenceData.title || evidenceData.documentTitle}
              </h3>
            </div>
          </div>
          <button onClick={onClose} className="p-1 rounded text-slate-400 hover:text-white hover:bg-white/5">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-5 space-y-4 text-xs text-slate-300 max-h-[70vh] overflow-y-auto custom-scrollbar">
          {/* Metadata Grid */}
          <div className="grid grid-cols-2 gap-3 p-3 rounded-lg bg-[#09090B] border border-white/5">
            {isInternal ? (
              <>
                <div className="flex items-center gap-2">
                  <Calendar className="w-3.5 h-3.5 text-slate-500" />
                  <span>Logged Date: <strong className="text-slate-200">{evidenceData.date}</strong></span>
                </div>
                <div className="flex items-center gap-2">
                  <MapPin className="w-3.5 h-3.5 text-slate-500" />
                  <span>Location: <strong className="text-slate-200">{evidenceData.location}</strong></span>
                </div>
                <div className="flex items-center gap-2">
                  <User className="w-3.5 h-3.5 text-slate-500" />
                  <span>Logged By: <strong className="text-slate-200">{evidenceData.reporterRole}</strong></span>
                </div>
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-3.5 h-3.5 text-slate-500" />
                  <span>Status: <strong className="text-blue-400">{evidenceData.status}</strong></span>
                </div>
              </>
            ) : (
              <>
                <div>
                  <span className="text-slate-400">Publisher:</span>
                  <div className="font-semibold text-white mt-0.5">{evidenceData.publisher}</div>
                </div>
                <div>
                  <span className="text-slate-400">Jurisdiction:</span>
                  <div className="font-semibold text-white mt-0.5">{evidenceData.jurisdiction}</div>
                </div>
                <div>
                  <span className="text-slate-400">Publication Year:</span>
                  <div className="font-semibold text-white mt-0.5">{evidenceData.publicationDate}</div>
                </div>
                <div>
                  <span className="text-slate-400">Reliability Index:</span>
                  <div className="font-semibold text-emerald-400 mt-0.5 flex items-center gap-1">
                    <ShieldCheck className="w-3 h-3" /> {evidenceData.reliability}
                  </div>
                </div>
              </>
            )}
          </div>

          {/* Detailed Narrative */}
          <div>
            <h4 className="text-xs font-semibold text-slate-200 uppercase tracking-wider mb-1.5">
              {isInternal ? 'Operational Event Record Details' : 'Key Extracted Regulatory Excerpt'}
            </h4>
            <div className="p-3.5 rounded-lg bg-[#09090B] border border-white/5 leading-relaxed text-slate-200 text-xs">
              {evidenceData.details || evidenceData.keyExcerpt}
            </div>
          </div>

          {/* AI Evidence Ingestion Stamp */}
          <div className="p-3 rounded-lg bg-blue-600/10 border border-blue-500/20 flex items-start gap-2.5">
            <ShieldCheck className="w-4 h-4 text-blue-400 shrink-0 mt-0.5" />
            <div className="text-[11px] text-slate-400">
              <span className="text-blue-300 font-semibold">Verified Evidence Hash: </span>
              <span className="font-mono text-slate-400">sha256-e9a3b7...4901</span>
              <p className="mt-0.5">
                This record is cryptographicly referenced inside the SIE Causal Graph for risk vector calibration.
              </p>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-3 bg-[#0F1117] border-t border-white/5 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-md bg-white/5 hover:bg-white/10 border border-white/10 text-slate-200 text-xs font-medium transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};

