import React, { useState } from 'react';
import { 
  ArrowLeft, 
  ShieldCheck, 
  FileCheck2, 
  AlertTriangle, 
  Check, 
  X, 
  RotateCcw, 
  Calendar, 
  Building, 
  Globe, 
  Lock, 
  FileText, 
  Sparkles,
  ExternalLink,
  ChevronDown
} from 'lucide-react';
import { KnowledgeDocument, VerificationStatus } from '../types';

interface SourceVerificationViewProps {
  document: KnowledgeDocument;
  onBack: () => void;
  onUpdateStatus: (docId: string, status: VerificationStatus, note: string) => void;
  allDocs: KnowledgeDocument[];
  onSelectOtherDoc: (docId: string) => void;
}

export const SourceVerificationView: React.FC<SourceVerificationViewProps> = ({
  document,
  onBack,
  onUpdateStatus,
  allDocs,
  onSelectOtherDoc
}) => {
  const [reviewNote, setReviewNote] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleAction = (status: VerificationStatus) => {
    setIsSubmitting(true);
    setTimeout(() => {
      onUpdateStatus(document.id, status, reviewNote || `HSE Reviewer action set to ${status}`);
      setReviewNote('');
      setIsSubmitting(false);
    }, 400);
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-200">
      {/* Top Header & Breadcrumb */}
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
              <span>Knowledge Center</span>
              <span>/</span>
              <span className="text-slate-300 font-semibold">Knowledge Source Validation</span>
            </div>
            <h1 className="text-xl sm:text-2xl font-bold text-white tracking-tight mt-0.5">
              Knowledge Source Validation
            </h1>
          </div>
        </div>

        {/* Source Switcher */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">Source:</span>
          <select
            value={document.id}
            onChange={(e) => onSelectOtherDoc(e.target.value)}
            className="bg-slate-900 border border-slate-700 text-slate-200 text-xs font-semibold rounded-lg px-3 py-1.5 focus:outline-none focus:border-cyan-500"
          >
            {allDocs.map((d) => (
              <option key={d.id} value={d.id}>
                {d.source} — {d.documentCode} ({d.verification})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Governance Statement Banner */}
      <div className="p-4 rounded-xl bg-cyan-950/30 border border-cyan-800/60 flex items-start gap-3">
        <ShieldCheck className="w-5 h-5 text-cyan-400 shrink-0 mt-0.5" />
        <div className="text-xs text-slate-300 leading-relaxed">
          <strong className="text-cyan-200">Zero Unverified AI Ingestion Policy: </strong>
          Safelytic Intelligence Engine does not blindly trust generic web crawlers or unvalidated sources. Every regulatory rule, empirical table, or industry guideline must pass cryptographic source provenance, metadata inspection, and expert human review before entering predictive model weights.
        </div>
      </div>

      {/* Core Document Info Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Metadata & Controls (5 cols) */}
        <div className="lg:col-span-5 space-y-5">
          {/* Source Metadata Card */}
          <div className="p-5 rounded-xl bg-slate-900/90 border border-slate-800 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                <FileText className="w-4 h-4 text-cyan-400" />
                <span>Source Metadata</span>
              </h3>
              <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded ${
                document.verification === 'Verified'
                  ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                  : 'bg-amber-950 text-amber-300 border border-amber-800'
              }`}>
                {document.verification}
              </span>
            </div>

            <div className="space-y-2.5 text-xs text-slate-300">
              <div className="flex justify-between py-1.5 border-b border-slate-800">
                <span className="text-slate-400">Publisher:</span>
                <span className="font-semibold text-slate-200">{document.source}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-slate-800">
                <span className="text-slate-400">Document Code:</span>
                <span className="font-mono text-cyan-300 font-bold">{document.documentCode}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-slate-800">
                <span className="text-slate-400">Publication Year:</span>
                <span className="font-mono text-slate-200">{document.publicationDate}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-slate-800">
                <span className="text-slate-400">Jurisdiction:</span>
                <span className="text-slate-200">{document.jurisdiction}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-slate-800">
                <span className="text-slate-400">Reliability Grade:</span>
                <span className="font-mono text-emerald-400 font-bold flex items-center gap-1">
                  <ShieldCheck className="w-3 h-3" /> {document.reliability}
                </span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-slate-800">
                <span className="text-slate-400">Last Synced:</span>
                <span className="font-mono text-slate-400">{document.lastUpdated}</span>
              </div>
            </div>

            {/* Applicable Industries */}
            <div>
              <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-2">
                Applicable Industries:
              </span>
              <div className="flex flex-wrap gap-1.5">
                {document.applicableIndustries.map((ind) => (
                  <span key={ind} className="px-2 py-0.5 rounded bg-slate-800 text-slate-200 text-[11px] border border-slate-700">
                    {ind}
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* Review Actions Card */}
          <div className="p-5 rounded-xl bg-slate-900/90 border border-slate-800 space-y-4">
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <FileCheck2 className="w-4 h-4 text-emerald-400" />
              <span>HSE Expert Decision & Calibration</span>
            </h3>

            <div>
              <label className="text-xs text-slate-400 block mb-1.5">
                Reviewer Justification / Calibration Notes:
              </label>
              <textarea
                value={reviewNote}
                onChange={(e) => setReviewNote(e.target.value)}
                placeholder="Specify reasons for approval, scope limitations, or required model factor weighting changes..."
                rows={3}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
              />
            </div>

            <div className="grid grid-cols-3 gap-2">
              <button
                onClick={() => handleAction('Verified')}
                disabled={isSubmitting}
                className="px-3 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow transition-colors flex items-center justify-center gap-1.5"
              >
                <Check className="w-3.5 h-3.5" />
                <span>Approve</span>
              </button>

              <button
                onClick={() => handleAction('Pending Review')}
                disabled={isSubmitting}
                className="px-3 py-2 rounded-lg bg-amber-700 hover:bg-amber-600 text-white text-xs font-semibold shadow transition-colors flex items-center justify-center gap-1.5"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>Request Review</span>
              </button>

              <button
                onClick={() => handleAction('Rejected')}
                disabled={isSubmitting}
                className="px-3 py-2 rounded-lg bg-rose-700 hover:bg-rose-600 text-white text-xs font-semibold shadow transition-colors flex items-center justify-center gap-1.5"
              >
                <X className="w-3.5 h-3.5" />
                <span>Reject</span>
              </button>
            </div>
          </div>
        </div>

        {/* Right Column: Knowledge Extracted, Verification History, Related Docs (7 cols) */}
        <div className="lg:col-span-7 space-y-5">
          {/* Knowledge Extracted Card */}
          <div className="p-5 sm:p-6 rounded-xl bg-slate-900/90 border border-slate-800 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-cyan-400" />
                  <span>Knowledge Extracted (SIE Ingestion Engine)</span>
                </h3>
                <p className="text-[11px] text-slate-400">Structured statutory rules parsed and mapped to predictive risk vectors</p>
              </div>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800">
                {document.extractedKeyRules.length} Extracted Rules
              </span>
            </div>

            <div className="space-y-2.5">
              {document.extractedKeyRules.map((rule, idx) => (
                <div key={idx} className="p-3 rounded-lg bg-slate-950/70 border border-slate-800 flex items-start gap-3">
                  <span className="w-5 h-5 rounded-full bg-cyan-950 text-cyan-400 border border-cyan-800 flex items-center justify-center font-mono text-[10px] font-bold shrink-0 mt-0.5">
                    {idx + 1}
                  </span>
                  <div className="text-xs text-slate-200 leading-relaxed">
                    {rule}
                  </div>
                </div>
              ))}
            </div>

            <div className="p-3 rounded-lg bg-slate-950 border border-slate-800/80 text-[11px] text-slate-400">
              <strong className="text-slate-300">Executive Summary: </strong>
              {document.summary}
            </div>
          </div>

          {/* Verification History Audit Trail */}
          <div className="p-5 rounded-xl bg-slate-900/90 border border-slate-800 space-y-3">
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <Calendar className="w-4 h-4 text-cyan-400" />
              <span>Verification History & Provenance Log</span>
            </h3>

            <div className="space-y-2">
              {document.verificationHistory.map((item, index) => (
                <div key={index} className="p-3 rounded-lg bg-slate-950/60 border border-slate-800 text-xs flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div>
                    <div className="font-semibold text-slate-200">{item.action}</div>
                    <div className="text-[11px] text-slate-400 mt-0.5">{item.notes}</div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="text-[10px] font-mono text-cyan-400">{item.reviewer}</div>
                    <div className="text-[10px] font-mono text-slate-500">{item.date}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
