import React, { useState } from 'react';
import { 
  BookOpen, 
  Search, 
  Filter, 
  ShieldCheck, 
  Clock, 
  FileCheck2, 
  AlertCircle, 
  ExternalLink, 
  ChevronRight,
  Globe,
  Building,
  Lock,
  Plus
} from 'lucide-react';
import { KnowledgeDocument, VerificationStatus } from '../types';

interface KnowledgeCenterViewProps {
  documents: KnowledgeDocument[];
  onSelectDocForValidation: (docId: string) => void;
  onOpenEvidence: (evidence: any) => void;
}

export const KnowledgeCenterView: React.FC<KnowledgeCenterViewProps> = ({
  documents,
  onSelectDocForValidation,
  onOpenEvidence
}) => {
  const [selectedDomain, setSelectedDomain] = useState<string>('All');
  const [searchQuery, setSearchQuery] = useState('');
  const [verificationFilter, setVerificationFilter] = useState<string>('All');
  const [industryFilter, setIndustryFilter] = useState<string>('All');

  const filteredDocs = documents.filter(doc => {
    const matchesDomain = selectedDomain === 'All' || doc.domain === selectedDomain;
    const matchesSearch = doc.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
                          doc.source.toLowerCase().includes(searchQuery.toLowerCase()) ||
                          doc.documentCode.toLowerCase().includes(searchQuery.toLowerCase()) ||
                          doc.topics.some(t => t.toLowerCase().includes(searchQuery.toLowerCase()));
    const matchesVerification = verificationFilter === 'All' || doc.verification === verificationFilter;
    const matchesIndustry = industryFilter === 'All' || doc.applicableIndustries.includes(industryFilter);
    return matchesDomain && matchesSearch && matchesVerification && matchesIndustry;
  });

  return (
    <div className="space-y-6 animate-in fade-in duration-200">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl sm:text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
              <BookOpen className="w-6 h-6 text-cyan-400" />
              <span>Safety Knowledge Center</span>
            </h1>
            <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-300 border border-cyan-800">
              Verified Knowledge Base
            </span>
          </div>
          <p className="text-xs sm:text-sm text-slate-400 mt-1 max-w-3xl leading-relaxed">
            Multi-tier verified safety intelligence repository unifying global statutory regulations, engineering standards, industry benchmarks, and private company SOPs.
          </p>
        </div>

        <button
          onClick={() => onSelectDocForValidation(documents[0].id)}
          className="px-3.5 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold shadow transition-colors flex items-center gap-2 shrink-0"
        >
          <FileCheck2 className="w-4 h-4" />
          <span>Source Validation Queue (27)</span>
        </button>
      </div>

      {/* 3 Major Knowledge Domains Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Global Safety Knowledge */}
        <div 
          onClick={() => setSelectedDomain(selectedDomain === 'Global Safety Knowledge' ? 'All' : 'Global Safety Knowledge')}
          className={`p-5 rounded-xl border transition-all cursor-pointer ${
            selectedDomain === 'Global Safety Knowledge'
              ? 'bg-cyan-950/50 border-cyan-500 shadow-md'
              : 'bg-slate-900/90 border-slate-800 hover:border-slate-700'
          }`}
        >
          <div className="flex items-start justify-between">
            <div className="p-2 rounded-lg bg-cyan-950 border border-cyan-800 text-cyan-400">
              <Globe className="w-5 h-5" />
            </div>
            <span className="text-xs font-mono font-bold text-cyan-400">8,420 Docs</span>
          </div>
          <h3 className="text-sm font-bold text-white mt-3">Global Safety Knowledge</h3>
          <p className="text-xs text-slate-400 mt-1 leading-relaxed">
            Statutory regulations & verified national frameworks (OSHA, HSE UK, NIOSH, ILO, ISO 45001).
          </p>
          <div className="mt-3 pt-2 border-t border-slate-800/80 text-[11px] font-mono text-cyan-300 flex items-center gap-1">
            <ShieldCheck className="w-3 h-3 text-emerald-400" />
            <span>100% Peer-Verified Lineage</span>
          </div>
        </div>

        {/* Industry Knowledge */}
        <div 
          onClick={() => setSelectedDomain(selectedDomain === 'Industry Knowledge' ? 'All' : 'Industry Knowledge')}
          className={`p-5 rounded-xl border transition-all cursor-pointer ${
            selectedDomain === 'Industry Knowledge'
              ? 'bg-purple-950/50 border-purple-500 shadow-md'
              : 'bg-slate-900/90 border-slate-800 hover:border-slate-700'
          }`}
        >
          <div className="flex items-start justify-between">
            <div className="p-2 rounded-lg bg-purple-950 border border-purple-800 text-purple-400">
              <Building className="w-5 h-5" />
            </div>
            <span className="text-xs font-mono font-bold text-purple-400">3,110 Docs</span>
          </div>
          <h3 className="text-sm font-bold text-white mt-3">Industry Knowledge</h3>
          <p className="text-xs text-slate-400 mt-1 leading-relaxed">
            Sector-specific technical guidelines (API, IMCA, IOGP, NFPA, Energy Institute).
          </p>
          <div className="mt-3 pt-2 border-t border-slate-800/80 text-[11px] font-mono text-purple-300 flex items-center gap-1">
            <ShieldCheck className="w-3 h-3 text-emerald-400" />
            <span>Oil & Gas / Maritime Calibrated</span>
          </div>
        </div>

        {/* Organization Knowledge */}
        <div 
          onClick={() => setSelectedDomain(selectedDomain === 'Organization Knowledge' ? 'All' : 'Organization Knowledge')}
          className={`p-5 rounded-xl border transition-all cursor-pointer ${
            selectedDomain === 'Organization Knowledge'
              ? 'bg-amber-950/50 border-amber-500 shadow-md'
              : 'bg-slate-900/90 border-slate-800 hover:border-slate-700'
          }`}
        >
          <div className="flex items-start justify-between">
            <div className="p-2 rounded-lg bg-amber-950 border border-amber-800 text-amber-400">
              <Lock className="w-5 h-5" />
            </div>
            <span className="text-xs font-mono font-bold text-amber-400">1,312 Docs</span>
          </div>
          <h3 className="text-sm font-bold text-white mt-3">Organization Knowledge</h3>
          <p className="text-xs text-slate-400 mt-1 leading-relaxed">
            Demo Energy & Engineering Ltd. private SOPs, Safe Systems of Work, and Golden Rules.
          </p>
          <div className="mt-3 pt-2 border-t border-slate-800/80 text-[11px] font-mono text-amber-300 flex items-center gap-1">
            <ShieldCheck className="w-3 h-3 text-emerald-400" />
            <span>Isolated Tenant Encryption</span>
          </div>
        </div>
      </div>

      {/* Statistics Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="p-3.5 rounded-lg bg-slate-900/90 border border-slate-800 text-center">
          <span className="text-[10px] uppercase font-semibold text-slate-400">Total Ingested Documents</span>
          <div className="text-xl font-extrabold text-cyan-400 font-mono mt-0.5">12,842</div>
        </div>
        <div className="p-3.5 rounded-lg bg-slate-900/90 border border-slate-800 text-center">
          <span className="text-[10px] uppercase font-semibold text-slate-400">Verified Sources</span>
          <div className="text-xl font-extrabold text-emerald-400 font-mono mt-0.5">436</div>
        </div>
        <div className="p-3.5 rounded-lg bg-slate-900/90 border border-slate-800 text-center">
          <span className="text-[10px] uppercase font-semibold text-slate-400">Pending Validation</span>
          <div className="text-xl font-extrabold text-amber-400 font-mono mt-0.5">27</div>
        </div>
        <div className="p-3.5 rounded-lg bg-slate-900/90 border border-slate-800 text-center">
          <span className="text-[10px] uppercase font-semibold text-slate-400">Recently Updated (30D)</span>
          <div className="text-xl font-extrabold text-slate-100 font-mono mt-0.5">84</div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
          {/* Search */}
          <div className="sm:col-span-2 relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="Search documents by code, title, topic or source (e.g. LOLER, OSHA, API RP 54)..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg pl-9 pr-3 py-1.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
            />
          </div>

          {/* Verification Status Filter */}
          <div>
            <select
              value={verificationFilter}
              onChange={(e) => setVerificationFilter(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 text-slate-200 text-xs rounded-lg px-3 py-1.5 focus:outline-none focus:border-cyan-500"
            >
              <option value="All">All Verification Statuses</option>
              <option value="Verified">Verified Only</option>
              <option value="Pending Review">Pending Review</option>
            </select>
          </div>

          {/* Industry Filter */}
          <div>
            <select
              value={industryFilter}
              onChange={(e) => setIndustryFilter(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 text-slate-200 text-xs rounded-lg px-3 py-1.5 focus:outline-none focus:border-cyan-500"
            >
              <option value="All">All Industries</option>
              <option value="Oil & Gas">Oil & Gas</option>
              <option value="Construction">Construction</option>
              <option value="Engineering">Engineering</option>
              <option value="Maritime">Maritime</option>
            </select>
          </div>
        </div>

        {/* Selected Domain filter tag */}
        {selectedDomain !== 'All' && (
          <div className="flex items-center gap-2 text-xs text-slate-400 pt-1">
            <span>Domain: <strong className="text-cyan-300">{selectedDomain}</strong></span>
            <button onClick={() => setSelectedDomain('All')} className="text-cyan-400 hover:underline">
              Clear Domain
            </button>
          </div>
        )}
      </div>

      {/* Document Table */}
      <div className="p-5 rounded-xl bg-slate-900/90 border border-slate-800">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400 font-semibold uppercase tracking-wider text-[10px]">
                <th className="py-2.5 px-3">Source & Publisher</th>
                <th className="py-2.5 px-3">Document Title & Code</th>
                <th className="py-2.5 px-3">Type</th>
                <th className="py-2.5 px-3">Jurisdiction</th>
                <th className="py-2.5 px-3">Publication Date</th>
                <th className="py-2.5 px-3">Verification</th>
                <th className="py-2.5 px-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {filteredDocs.map((doc) => (
                <tr key={doc.id} className="hover:bg-slate-800/50 transition-colors group">
                  <td className="py-3 px-3 font-semibold text-slate-100">
                    <div className="text-cyan-300 font-mono text-[11px]">{doc.source}</div>
                    <div className="text-[10px] text-slate-500 font-normal">{doc.domain}</div>
                  </td>
                  <td className="py-3 px-3 max-w-sm">
                    <div className="font-semibold text-slate-200 group-hover:text-cyan-300 transition-colors">
                      {doc.title}
                    </div>
                    <div className="text-[10px] font-mono text-slate-400 mt-0.5 flex items-center gap-2">
                      <span>{doc.documentCode}</span>
                      <span>•</span>
                      <span className="text-slate-400">{doc.topics.slice(0, 2).join(', ')}</span>
                    </div>
                  </td>
                  <td className="py-3 px-3 text-[11px]">
                    <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                      {doc.type}
                    </span>
                  </td>
                  <td className="py-3 px-3 text-[11px] text-slate-300">
                    {doc.jurisdiction}
                  </td>
                  <td className="py-3 px-3 font-mono text-slate-400 text-[11px]">
                    {doc.publicationDate}
                  </td>
                  <td className="py-3 px-3">
                    <span className={`text-[10px] font-mono px-2 py-0.5 rounded font-semibold ${
                      doc.verification === 'Verified'
                        ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                        : 'bg-amber-950 text-amber-300 border border-amber-800'
                    }`}>
                      {doc.verification}
                    </span>
                  </td>
                  <td className="py-3 px-3 text-right">
                    <button
                      onClick={() => onSelectDocForValidation(doc.id)}
                      className="px-2.5 py-1 rounded bg-slate-800 hover:bg-cyan-600 hover:text-white text-slate-300 text-xs font-medium transition-colors inline-flex items-center gap-1"
                    >
                      <span>Validate Source</span>
                      <ChevronRight className="w-3 h-3" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
