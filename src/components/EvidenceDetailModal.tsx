import React from 'react';
import { 
  X, 
  FileText, 
  CheckCircle2, 
  AlertTriangle, 
  ShieldCheck, 
  MapPin, 
  Calendar, 
  User, 
  ExternalLink, 
  Hash,
  Database,
  Layers,
  Activity,
  Sliders,
  TrendingUp,
  Cpu,
  Info
} from 'lucide-react';
import { OrganizationEvidenceItem, ExternalEvidenceItem, AnalyticalEvidenceItem } from '../types';

interface EvidenceDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  evidenceData?: any;
  data?: any;
}

export const EvidenceDetailModal: React.FC<EvidenceDetailModalProps> = ({
  isOpen,
  onClose,
  evidenceData: rawEvidenceData,
  data
}) => {
  const evidenceData = rawEvidenceData || data;
  if (!isOpen || !evidenceData) return null;

  const isOrganization = Boolean(evidenceData.activity || evidenceData.sourceSystem || (evidenceData.type && !evidenceData.modelTechnique));
  const isExternal = Boolean(evidenceData.publisher || evidenceData.documentTitle || evidenceData.code);
  const isAnalytical = Boolean(evidenceData.trend || evidenceData.baseline || evidenceData.modelTechnique);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in">
      <div 
        className="w-full max-w-2xl bg-[#16181D] border border-white/10 rounded-2xl shadow-2xl overflow-hidden animate-in zoom-in-95 flex flex-col max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-4 sm:p-5 border-b border-white/10 bg-[#0F1117] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`p-2.5 rounded-xl ${
              isOrganization
                ? 'bg-blue-600/15 border border-blue-500/30 text-blue-400'
                : isExternal
                ? 'bg-purple-600/15 border border-purple-500/30 text-purple-400'
                : 'bg-cyan-600/15 border border-cyan-500/30 text-cyan-400'
            }`}>
              {isOrganization ? <FileText className="w-5 h-5" /> : isExternal ? <Database className="w-5 h-5" /> : <Activity className="w-5 h-5" />}
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-mono font-bold text-white tracking-wide">
                  {evidenceData.id || evidenceData.code || 'EVIDENCE RECORD'}
                </span>
                
                <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded uppercase tracking-wider ${
                  isOrganization
                    ? 'bg-blue-950/80 text-blue-300 border border-blue-800'
                    : isExternal
                    ? 'bg-purple-950/80 text-purple-300 border border-purple-800'
                    : 'bg-cyan-950/80 text-cyan-300 border border-cyan-800'
                }`}>
                  {isOrganization ? `Organization Evidence (${evidenceData.type || 'Operational Record'})` : isExternal ? 'External Knowledge Grounding' : 'Analytical Evidence'}
                </span>

                {/* Prominent DEMO / SIMULATED Badge */}
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-800 font-bold uppercase tracking-wider">
                  DEMO / SIMULATED
                </span>

                {evidenceData.severity && (
                  <span className={`text-[10px] font-mono px-2 py-0.5 rounded font-bold ${
                    evidenceData.severity === 'High' || evidenceData.severity === 'Critical'
                      ? 'bg-red-950/80 text-red-300 border border-red-800'
                      : 'bg-amber-950/80 text-amber-300 border border-amber-800'
                  }`}>
                    {evidenceData.severity} Severity
                  </span>
                )}
              </div>

              <h3 className="text-sm sm:text-base font-bold text-white mt-1">
                {evidenceData.title || evidenceData.documentTitle || evidenceData.topic || 'Analytical Factor Matrix'}
              </h3>
            </div>
          </div>

          <button 
            onClick={onClose} 
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors shrink-0"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-5 space-y-5 text-xs text-slate-300 overflow-y-auto custom-scrollbar flex-1">
          
          {/* Provenance Notice */}
          <div className="p-3 rounded-lg bg-blue-950/30 border border-blue-500/30 text-blue-200 text-xs flex items-start gap-2.5">
            <Info className="w-4 h-4 text-blue-400 shrink-0 mt-0.5" />
            <div className="leading-relaxed">
              <strong className="text-blue-300">Evidence Provenance Assurance:</strong> Every intelligence finding in SIE is anchored to verifiable data points.
              This prototype record is marked <span className="font-mono font-bold text-amber-300 bg-amber-950/60 px-1 py-0.2 rounded border border-amber-800">DEMO / SIMULATED</span> for demonstration purposes.
            </div>
          </div>

          {/* 1. ORGANIZATION EVIDENCE MODALITY */}
          {isOrganization && (
            <div className="space-y-4">
              <div className="text-[11px] font-mono font-bold uppercase tracking-wider text-slate-400 flex items-center justify-between border-b border-white/5 pb-1">
                <span>Organization Record Attributes</span>
                <span className="text-blue-400">Source: {evidenceData.sourceSystem || 'Intelex HSE Cloud'}</span>
              </div>

              {/* Comprehensive 8-Point Organization Evidence Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 p-3.5 rounded-xl bg-[#09090B] border border-white/5">
                <div>
                  <span className="text-[10px] text-slate-400 font-mono uppercase block">Record ID</span>
                  <strong className="text-blue-400 font-mono text-xs">{evidenceData.id}</strong>
                </div>

                <div>
                  <span className="text-[10px] text-slate-400 font-mono uppercase block">Record Type</span>
                  <strong className="text-white text-xs">{evidenceData.type || 'Safety Observation'}</strong>
                </div>

                <div>
                  <span className="text-[10px] text-slate-400 font-mono uppercase block">Logged Date</span>
                  <strong className="text-slate-200 text-xs flex items-center gap-1">
                    <Calendar className="w-3 h-3 text-slate-400" />
                    {evidenceData.date}
                  </strong>
                </div>

                <div>
                  <span className="text-[10px] text-slate-400 font-mono uppercase block">Site &amp; Location</span>
                  <strong className="text-slate-200 text-xs flex items-center gap-1">
                    <MapPin className="w-3 h-3 text-slate-400" />
                    {evidenceData.site || 'Lagos Operations'} ({evidenceData.location})
                  </strong>
                </div>

                <div>
                  <span className="text-[10px] text-slate-400 font-mono uppercase block">Operational Activity</span>
                  <strong className="text-slate-200 text-xs">{evidenceData.activity || 'Field Operations'}</strong>
                </div>

                <div>
                  <span className="text-[10px] text-slate-400 font-mono uppercase block">Status &amp; Workflow</span>
                  <strong className="text-emerald-400 text-xs flex items-center gap-1">
                    <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                    {evidenceData.status || 'Active Ingestion'}
                  </strong>
                </div>

                <div className="col-span-2 sm:col-span-3 pt-2 border-t border-white/5 grid grid-cols-2 gap-3">
                  <div>
                    <span className="text-[10px] text-slate-400 font-mono uppercase block">Identified Hazard</span>
                    <p className="text-slate-200 text-xs mt-0.5">{evidenceData.hazard || 'Workplace hazard condition'}</p>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-400 font-mono uppercase block">Associated Risk Vector</span>
                    <p className="text-amber-300 text-xs mt-0.5">{evidenceData.risk || 'Elevated incident potential'}</p>
                  </div>
                </div>
              </div>

              {/* Event Description */}
              <div>
                <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider mb-1.5 flex items-center gap-1.5">
                  <FileText className="w-3.5 h-3.5 text-blue-400" />
                  <span>Field Record Description &amp; Observer Transcript</span>
                </h4>
                <div className="p-3.5 rounded-xl bg-[#09090B] border border-white/5 leading-relaxed text-slate-200 text-xs font-sans">
                  {evidenceData.details}
                </div>
                {evidenceData.reporterRole && (
                  <div className="mt-1 text-[11px] text-slate-400 font-mono flex items-center gap-1.5">
                    <User className="w-3 h-3 text-slate-400" />
                    <span>Logged by: <strong className="text-slate-300">{evidenceData.reporterRole}</strong></span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 2. EXTERNAL EVIDENCE MODALITY */}
          {isExternal && (
            <div className="space-y-4">
              <div className="text-[11px] font-mono font-bold uppercase tracking-wider text-purple-300 flex items-center justify-between border-b border-white/5 pb-1">
                <span>External Knowledge Standards Grounding</span>
                <span className="text-emerald-400 font-mono">Reliability: {evidenceData.reliability || 'Very High'}</span>
              </div>

              {/* External Evidence 10-Point Parameter Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 p-3.5 rounded-xl bg-[#09090B] border border-white/5">
                <div>
                  <span className="text-[10px] text-slate-400 font-mono uppercase block">Publisher / Body</span>
                  <strong className="text-purple-300 text-xs">{evidenceData.publisher}</strong>
                </div>

                <div>
                  <span className="text-[10px] text-slate-400 font-mono uppercase block">Document Type</span>
                  <strong className="text-white text-xs">{evidenceData.documentType || 'Approved Code of Practice'}</strong>
                </div>

                <div>
                  <span className="text-[10px] text-slate-400 font-mono uppercase block">Standard Code / Ref</span>
                  <strong className="text-cyan-400 font-mono text-xs">{evidenceData.code}</strong>
                </div>

                <div>
                  <span className="text-[10px] text-slate-400 font-mono uppercase block">Jurisdiction</span>
                  <strong className="text-slate-200 text-xs">{evidenceData.jurisdiction}</strong>
                </div>

                <div>
                  <span className="text-[10px] text-slate-400 font-mono uppercase block">Publication Year</span>
                  <strong className="text-slate-200 text-xs">{evidenceData.publicationDate}</strong>
                </div>

                <div>
                  <span className="text-[10px] text-slate-400 font-mono uppercase block">Revision / Version</span>
                  <strong className="text-slate-200 text-xs">{evidenceData.revisionVersion || '2025/2026 Edition'}</strong>
                </div>

                <div>
                  <span className="text-[10px] text-slate-400 font-mono uppercase block">Verification Status</span>
                  <strong className="text-emerald-400 text-xs flex items-center gap-1">
                    <ShieldCheck className="w-3 h-3 text-emerald-400" />
                    {evidenceData.verificationStatus || 'Verified & Active'}
                  </strong>
                </div>

                <div>
                  <span className="text-[10px] text-slate-400 font-mono uppercase block">Core Topic</span>
                  <strong className="text-slate-200 text-xs">{evidenceData.topic}</strong>
                </div>

                <div>
                  <span className="text-[10px] text-slate-400 font-mono uppercase block">Source Reference</span>
                  <strong className="text-purple-300 font-mono text-xs">{evidenceData.sourceReference || evidenceData.code}</strong>
                </div>
              </div>

              {/* Extracted Excerpt */}
              <div>
                <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider mb-1.5 flex items-center gap-1.5">
                  <Database className="w-3.5 h-3.5 text-purple-400" />
                  <span>Key Extracted Normative Excerpt</span>
                </h4>
                <div className="p-3.5 rounded-xl bg-[#09090B] border border-purple-900/30 text-purple-100 italic text-xs leading-relaxed">
                  &ldquo;{evidenceData.keyExcerpt}&rdquo;
                </div>
              </div>
            </div>
          )}

          {/* 3. ANALYTICAL EVIDENCE MODALITY */}
          {isAnalytical && (
            <div className="space-y-4">
              <div className="text-[11px] font-mono font-bold uppercase tracking-wider text-cyan-300 flex items-center justify-between border-b border-white/5 pb-1">
                <span>Analytical Evidence &amp; Statistical Baselines</span>
                <span className="text-cyan-400 font-mono">{evidenceData.confidenceInterval || '95% CI'}</span>
              </div>

              {/* Analytical Evidence 6-Point Breakdown */}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 p-3.5 rounded-xl bg-[#09090B] border border-white/5">
                <div>
                  <span className="text-[10px] text-slate-400 font-mono uppercase block">Calculated Trend</span>
                  <strong className="text-rose-400 font-mono text-xs flex items-center gap-1">
                    <TrendingUp className="w-3.5 h-3.5 text-rose-400" />
                    {evidenceData.trend}
                  </strong>
                </div>

                <div>
                  <span className="text-[10px] text-slate-400 font-mono uppercase block">Historical Baseline</span>
                  <strong className="text-slate-200 text-xs">{evidenceData.baseline}</strong>
                </div>

                <div>
                  <span className="text-[10px] text-slate-400 font-mono uppercase block">Current Observed Value</span>
                  <strong className="text-cyan-300 text-xs">{evidenceData.currentValue}</strong>
                </div>

                <div>
                  <span className="text-[10px] text-slate-400 font-mono uppercase block">Statistical Deviation</span>
                  <strong className="text-amber-400 font-mono text-xs">{evidenceData.deviation}</strong>
                </div>

                <div>
                  <span className="text-[10px] text-slate-400 font-mono uppercase block">Modeling Technique</span>
                  <strong className="text-slate-200 text-xs">{evidenceData.modelTechnique || 'Markov Chain & Bayes Survival'}</strong>
                </div>

                <div>
                  <span className="text-[10px] text-slate-400 font-mono uppercase block">Confidence Interval</span>
                  <strong className="text-emerald-400 font-mono text-xs">{evidenceData.confidenceInterval || '95% CI [72% - 88%]'}</strong>
                </div>
              </div>

              {/* Historical Comparison */}
              <div>
                <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider mb-1.5 flex items-center gap-1.5">
                  <Activity className="w-3.5 h-3.5 text-cyan-400" />
                  <span>Historical Comparison Pattern</span>
                </h4>
                <div className="p-3.5 rounded-xl bg-[#09090B] border border-white/5 leading-relaxed text-slate-200 text-xs">
                  {evidenceData.historicalComparison}
                </div>
              </div>

              {/* Contributing Factors */}
              {evidenceData.contributingFactors && evidenceData.contributingFactors.length > 0 && (
                <div>
                  <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <Sliders className="w-3.5 h-3.5 text-cyan-400" />
                    <span>Contributing Analytical Factors</span>
                  </h4>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                    {evidenceData.contributingFactors.map((f: any) => (
                      <div key={f.name} className="p-2.5 rounded-lg bg-[#09090B] border border-white/5">
                        <div className="flex items-center justify-between text-xs mb-1">
                          <span className="font-semibold text-slate-200 line-clamp-1">{f.name}</span>
                          <span className="font-mono font-bold text-cyan-400">{f.percentage}%</span>
                        </div>
                        <p className="text-[10px] text-slate-400 leading-snug">{f.description}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Cryptographic Lineage Anchor */}
          <div className="p-3 rounded-xl bg-blue-600/10 border border-blue-500/20 flex items-start gap-2.5">
            <ShieldCheck className="w-4 h-4 text-blue-400 shrink-0 mt-0.5" />
            <div className="text-[11px] text-slate-400">
              <div className="flex items-center gap-2">
                <span className="text-blue-300 font-semibold">Cryptographic Provenance Lineage Hash: </span>
                <span className="font-mono text-slate-300">sha256-e9a3b72c4901f4...88d2</span>
              </div>
              <p className="mt-0.5 text-slate-400">
                This record is mathematically linked to the Safety Intelligence Engine causal prediction graph.
              </p>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 bg-[#0F1117] border-t border-white/10 flex items-center justify-between">
          <span className="text-[10px] font-mono text-slate-500">
            SIE Provenance Engine v4.6.2 • Certified Traceability
          </span>
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/15 text-white text-xs font-semibold transition-colors"
          >
            Close Record
          </button>
        </div>
      </div>
    </div>
  );
};


