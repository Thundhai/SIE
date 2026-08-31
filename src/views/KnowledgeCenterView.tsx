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
  Plus,
  Shield,
  CheckCircle2,
  Calendar,
  Layers,
  ArrowRight,
  Eye,
  AlertTriangle,
  RefreshCw,
  Award,
  Sparkles,
  Info,
  SlidersHorizontal,
  Flame,
  HardHat,
  Factory,
  Zap,
  Ship,
  Pickaxe
} from 'lucide-react';
import { KnowledgeDocument, VerificationStatus, KnowledgeFreshness } from '../types';

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
  const [freshnessFilter, setFreshnessFilter] = useState<string>('All');
  const [selectedDocDetails, setSelectedDocDetails] = useState<KnowledgeDocument | null>(null);

  const filteredDocs = documents.filter(doc => {
    const matchesDomain = selectedDomain === 'All' || doc.domain === selectedDomain;
    const matchesSearch = doc.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
                          doc.source.toLowerCase().includes(searchQuery.toLowerCase()) ||
                          (doc.sourceAuthority && doc.sourceAuthority.toLowerCase().includes(searchQuery.toLowerCase())) ||
                          doc.documentCode.toLowerCase().includes(searchQuery.toLowerCase()) ||
                          doc.topics.some(t => t.toLowerCase().includes(searchQuery.toLowerCase()));
    const matchesVerification = verificationFilter === 'All' || doc.verification === verificationFilter;
    const matchesIndustry = industryFilter === 'All' || doc.applicableIndustries.includes(industryFilter);
    const matchesFreshness = freshnessFilter === 'All' || doc.freshness === freshnessFilter;
    return matchesDomain && matchesSearch && matchesVerification && matchesIndustry && matchesFreshness;
  });

  const getDomainBadge = (domain: string) => {
    switch (domain) {
      case 'Global Safety Knowledge':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-semibold bg-cyan-950/80 text-cyan-300 border border-cyan-700/60 shadow-sm">
            <Globe className="w-3.5 h-3.5 text-cyan-400" />
            <span>GLOBAL</span>
          </span>
        );
      case 'Industry Knowledge':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-semibold bg-purple-950/80 text-purple-300 border border-purple-700/60 shadow-sm">
            <Building className="w-3.5 h-3.5 text-purple-400" />
            <span>INDUSTRY</span>
          </span>
        );
      case 'Organization Knowledge':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-semibold bg-amber-950/90 text-amber-300 border border-amber-600/70 shadow-sm">
            <Lock className="w-3.5 h-3.5 text-amber-400" />
            <span>ORGANIZATION</span>
          </span>
        );
      default:
        return null;
    }
  };

  const getFreshnessBadge = (freshness?: KnowledgeFreshness) => {
    switch (freshness) {
      case 'Current':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-emerald-950/70 text-emerald-300 border border-emerald-800/80">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
            <span>Current</span>
          </span>
        );
      case 'Recently Updated':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-cyan-950/70 text-cyan-300 border border-cyan-800/80">
            <RefreshCw className="w-2.5 h-2.5 text-cyan-400" />
            <span>Recently Updated</span>
          </span>
        );
      case 'Review Required':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-amber-950/70 text-amber-300 border border-amber-800/80">
            <Clock className="w-2.5 h-2.5 text-amber-400" />
            <span>Review Required</span>
          </span>
        );
      case 'Expired/Obsolete':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-rose-950/70 text-rose-300 border border-rose-800/80">
            <AlertTriangle className="w-2.5 h-2.5 text-rose-400" />
            <span>Expired/Obsolete</span>
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-slate-800 text-slate-400 border border-slate-700">
            <span>Current</span>
          </span>
        );
    }
  };

  const getReliabilityBadge = (rel: string) => {
    switch (rel) {
      case 'Very High':
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-mono text-emerald-300">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            <span>Very High</span>
          </span>
        );
      case 'High':
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-mono text-cyan-300">
            <ShieldCheck className="w-3.5 h-3.5 text-cyan-400" />
            <span>High</span>
          </span>
        );
      case 'Moderate':
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-mono text-amber-300">
            <AlertCircle className="w-3.5 h-3.5 text-amber-400" />
            <span>Moderate</span>
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-mono text-slate-400">
            <span>Unverified</span>
          </span>
        );
    }
  };

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
            Multi-tier verified safety intelligence repository unifying global statutory regulations, sector engineering benchmarks, and isolated private organization standards.
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

      {/* Structured Knowledge Ingestion Flow Banner */}
      <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 relative overflow-hidden">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-md bg-cyan-950 border border-cyan-800 text-cyan-400">
              <Shield className="w-4 h-4" />
            </div>
            <div>
              <span className="text-xs font-bold text-slate-200 tracking-wide uppercase">Knowledge Intelligence Lifecycle</span>
              <p className="text-[11px] text-slate-400">Deterministic validation prevents random internet noise from entering SIE reasoning.</p>
            </div>
          </div>
          <div className="flex items-center gap-1.5 sm:gap-2 text-[10px] sm:text-xs font-mono font-semibold flex-wrap">
            <span className="px-2 py-1 rounded bg-slate-800 text-slate-300 border border-slate-700">1. Source</span>
            <ArrowRight className="w-3 h-3 text-cyan-500 shrink-0" />
            <span className="px-2 py-1 rounded bg-slate-800 text-cyan-300 border border-cyan-800/80">2. Validation</span>
            <ArrowRight className="w-3 h-3 text-cyan-500 shrink-0" />
            <span className="px-2 py-1 rounded bg-slate-800 text-purple-300 border border-purple-800/80">3. Classification</span>
            <ArrowRight className="w-3 h-3 text-cyan-500 shrink-0" />
            <span className="px-2 py-1 rounded bg-slate-800 text-amber-300 border border-amber-800/80">4. Knowledge</span>
            <ArrowRight className="w-3 h-3 text-cyan-500 shrink-0" />
            <span className="px-2 py-1 rounded bg-slate-800 text-emerald-300 border border-emerald-800/80">5. Retrieval</span>
            <ArrowRight className="w-3 h-3 text-cyan-500 shrink-0" />
            <span className="px-2.5 py-1 rounded bg-gradient-to-r from-cyan-950 to-blue-900 text-white border border-cyan-600 font-bold shadow-sm">6. Intelligence</span>
          </div>
        </div>
      </div>

      {/* 3 Major Knowledge Domains Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Global Safety Knowledge */}
        <div 
          onClick={() => setSelectedDomain(selectedDomain === 'Global Safety Knowledge' ? 'All' : 'Global Safety Knowledge')}
          className={`p-5 rounded-xl border transition-all cursor-pointer relative overflow-hidden ${
            selectedDomain === 'Global Safety Knowledge'
              ? 'bg-cyan-950/60 border-cyan-400 ring-1 ring-cyan-400/50 shadow-lg'
              : 'bg-slate-900/90 border-slate-800 hover:border-slate-700'
          }`}
        >
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2.5">
              <div className="p-2.5 rounded-lg bg-cyan-950 border border-cyan-800 text-cyan-400">
                <Globe className="w-5 h-5" />
              </div>
              <div>
                <span className="text-[10px] font-mono font-bold tracking-wider uppercase px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-700">
                  GLOBAL
                </span>
              </div>
            </div>
            <span className="text-xs font-mono font-bold text-cyan-400">8,420 Docs</span>
          </div>
          
          <h3 className="text-base font-bold text-white mt-3.5">Global Safety Knowledge</h3>
          <p className="text-xs text-slate-300 mt-1 leading-relaxed">
            Verified external knowledge applicable across organizations: Statutory frameworks, regulators, government agencies, scientific research, and safety alerts.
          </p>

          <div className="mt-3 flex flex-wrap gap-1 text-[10px] text-slate-400 font-medium">
            <span className="px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800">Regulators</span>
            <span className="px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800">Government Agencies</span>
            <span className="px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800">Research</span>
            <span className="px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800">Industry Bodies</span>
            <span className="px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800">Safety Alerts</span>
          </div>

          <div className="mt-3.5 pt-2.5 border-t border-slate-800/80 text-[11px] font-mono text-cyan-300 flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
              <span>100% Peer-Verified Lineage</span>
            </div>
            <span className="text-[10px] text-slate-400">OSHA, HSE, NIOSH, ILO</span>
          </div>
        </div>

        {/* Industry Knowledge */}
        <div 
          onClick={() => setSelectedDomain(selectedDomain === 'Industry Knowledge' ? 'All' : 'Industry Knowledge')}
          className={`p-5 rounded-xl border transition-all cursor-pointer relative overflow-hidden ${
            selectedDomain === 'Industry Knowledge'
              ? 'bg-purple-950/60 border-purple-400 ring-1 ring-purple-400/50 shadow-lg'
              : 'bg-slate-900/90 border-slate-800 hover:border-slate-700'
          }`}
        >
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2.5">
              <div className="p-2.5 rounded-lg bg-purple-950 border border-purple-800 text-purple-400">
                <Building className="w-5 h-5" />
              </div>
              <div>
                <span className="text-[10px] font-mono font-bold tracking-wider uppercase px-2 py-0.5 rounded bg-purple-950 text-purple-300 border border-purple-700">
                  INDUSTRY
                </span>
              </div>
            </div>
            <span className="text-xs font-mono font-bold text-purple-400">3,110 Docs</span>
          </div>

          <h3 className="text-base font-bold text-white mt-3.5">Industry Knowledge</h3>
          <p className="text-xs text-slate-300 mt-1 leading-relaxed">
            Sector-specific technical engineering guidelines, consensus practices, and operational benchmarks calibrated by vertical.
          </p>

          <div className="mt-3 flex flex-wrap gap-1 text-[10px] text-slate-400 font-medium">
            <span className="px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800 flex items-center gap-1"><Flame className="w-2.5 h-2.5 text-orange-400" /> Oil & Gas</span>
            <span className="px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800 flex items-center gap-1"><HardHat className="w-2.5 h-2.5 text-yellow-400" /> Construction</span>
            <span className="px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800 flex items-center gap-1"><Factory className="w-2.5 h-2.5 text-blue-400" /> Manufacturing</span>
            <span className="px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800 flex items-center gap-1"><Zap className="w-2.5 h-2.5 text-amber-400" /> Energy</span>
            <span className="px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800 flex items-center gap-1"><Ship className="w-2.5 h-2.5 text-cyan-400" /> Maritime</span>
            <span className="px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800 flex items-center gap-1"><Pickaxe className="w-2.5 h-2.5 text-emerald-400" /> Mining</span>
          </div>

          <div className="mt-3.5 pt-2.5 border-t border-slate-800/80 text-[11px] font-mono text-purple-300 flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
              <span>Sector Domain Calibrated</span>
            </div>
            <span className="text-[10px] text-slate-400">API, IMCA, EI, ICMM</span>
          </div>
        </div>

        {/* Organization Knowledge */}
        <div 
          onClick={() => setSelectedDomain(selectedDomain === 'Organization Knowledge' ? 'All' : 'Organization Knowledge')}
          className={`p-5 rounded-xl border transition-all cursor-pointer relative overflow-hidden ${
            selectedDomain === 'Organization Knowledge'
              ? 'bg-amber-950/60 border-amber-400 ring-1 ring-amber-400/50 shadow-lg'
              : 'bg-slate-900/90 border-slate-800 hover:border-slate-700'
          }`}
        >
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2.5">
              <div className="p-2.5 rounded-lg bg-amber-950 border border-amber-800 text-amber-400">
                <Lock className="w-5 h-5" />
              </div>
              <div>
                <span className="text-[10px] font-mono font-bold tracking-wider uppercase px-2 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-700">
                  ORGANIZATION
                </span>
              </div>
            </div>
            <span className="text-xs font-mono font-bold text-amber-400">1,312 Docs</span>
          </div>

          <h3 className="text-base font-bold text-white mt-3.5">Organization Knowledge</h3>
          <p className="text-xs text-slate-300 mt-1 leading-relaxed">
            Private organization-specific knowledge: Internal policies, standard operating procedures (SOPs), risk assessments (HIRA), incident reports, and lessons learned.
          </p>

          <div className="mt-3 flex flex-wrap gap-1 text-[10px] text-slate-400 font-medium">
            <span className="px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800">Policies</span>
            <span className="px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800">Procedures (SOPs)</span>
            <span className="px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800">Risk Assessments</span>
            <span className="px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800">Incident Reports</span>
            <span className="px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800">Lessons Learned</span>
            <span className="px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800">Internal Standards</span>
          </div>

          <div className="mt-3.5 pt-2.5 border-t border-slate-800/80 text-[11px] font-mono text-amber-300 flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <Lock className="w-3.5 h-3.5 text-amber-400" />
              <span className="font-semibold text-amber-200">Organization-scoped knowledge</span>
            </div>
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-amber-900/60 text-amber-300 border border-amber-700/60">
              Private & Isolated
            </span>
          </div>
        </div>
      </div>

      {/* Private Tenant Data Isolation Callout */}
      <div className="p-3.5 rounded-xl bg-amber-950/30 border border-amber-800/60 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
        <div className="flex items-start sm:items-center gap-2.5 text-slate-300">
          <div className="p-1.5 rounded-md bg-amber-950 border border-amber-700 text-amber-400 shrink-0">
            <Lock className="w-4 h-4" />
          </div>
          <div>
            <strong className="text-amber-200 font-semibold">Organization Knowledge Privacy Guarantee: </strong>
            <span>All organization-scoped documents (SOPs, HIRAs, Incident Reports) are strictly isolated in a private tenant encryption container and are never shared across organizations or used for public training.</span>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0 font-mono text-[11px]">
          <span className="px-2.5 py-1 rounded bg-amber-950 text-amber-300 border border-amber-700 font-semibold">
            Tenant: Demo Energy & Eng. (ISOLATED)
          </span>
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
        <div className="grid grid-cols-1 sm:grid-cols-12 gap-3">
          {/* Search */}
          <div className="sm:col-span-4 relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="Search by title, authority, code, topic..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg pl-9 pr-3 py-1.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
            />
          </div>

          {/* Domain Filter */}
          <div className="sm:col-span-2">
            <select
              value={selectedDomain}
              onChange={(e) => setSelectedDomain(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 text-slate-200 text-xs rounded-lg px-3 py-1.5 focus:outline-none focus:border-cyan-500"
            >
              <option value="All">All Domains</option>
              <option value="Global Safety Knowledge">Global Safety</option>
              <option value="Industry Knowledge">Industry Knowledge</option>
              <option value="Organization Knowledge">Organization (Private)</option>
            </select>
          </div>

          {/* Verification Status Filter */}
          <div className="sm:col-span-2">
            <select
              value={verificationFilter}
              onChange={(e) => setVerificationFilter(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 text-slate-200 text-xs rounded-lg px-3 py-1.5 focus:outline-none focus:border-cyan-500"
            >
              <option value="All">All Verification</option>
              <option value="Verified">Verified Only</option>
              <option value="Pending Review">Pending Review</option>
              <option value="Flagged">Flagged</option>
            </select>
          </div>

          {/* Industry Filter */}
          <div className="sm:col-span-2">
            <select
              value={industryFilter}
              onChange={(e) => setIndustryFilter(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 text-slate-200 text-xs rounded-lg px-3 py-1.5 focus:outline-none focus:border-cyan-500"
            >
              <option value="All">All Industries</option>
              <option value="Oil & Gas">Oil & Gas</option>
              <option value="Construction">Construction</option>
              <option value="Manufacturing">Manufacturing</option>
              <option value="Energy">Energy</option>
              <option value="Maritime">Maritime</option>
              <option value="Mining">Mining</option>
              <option value="Engineering">Engineering</option>
            </select>
          </div>

          {/* Freshness Filter */}
          <div className="sm:col-span-2">
            <select
              value={freshnessFilter}
              onChange={(e) => setFreshnessFilter(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 text-slate-200 text-xs rounded-lg px-3 py-1.5 focus:outline-none focus:border-cyan-500"
            >
              <option value="All">All Freshness</option>
              <option value="Current">Current</option>
              <option value="Recently Updated">Recently Updated</option>
              <option value="Review Required">Review Required</option>
              <option value="Expired/Obsolete">Expired/Obsolete</option>
            </select>
          </div>
        </div>

        {/* Selected Filter Tags */}
        {(selectedDomain !== 'All' || verificationFilter !== 'All' || industryFilter !== 'All' || freshnessFilter !== 'All' || searchQuery) && (
          <div className="flex items-center gap-2 text-xs text-slate-400 pt-1 flex-wrap">
            <span className="font-semibold text-slate-300">Active Filters:</span>
            {selectedDomain !== 'All' && (
              <span className="px-2 py-0.5 rounded bg-slate-800 text-cyan-300 border border-slate-700 flex items-center gap-1">
                Domain: {selectedDomain}
                <button onClick={() => setSelectedDomain('All')} className="hover:text-white ml-1">×</button>
              </span>
            )}
            {verificationFilter !== 'All' && (
              <span className="px-2 py-0.5 rounded bg-slate-800 text-emerald-300 border border-slate-700 flex items-center gap-1">
                Status: {verificationFilter}
                <button onClick={() => setVerificationFilter('All')} className="hover:text-white ml-1">×</button>
              </span>
            )}
            {industryFilter !== 'All' && (
              <span className="px-2 py-0.5 rounded bg-slate-800 text-purple-300 border border-slate-700 flex items-center gap-1">
                Sector: {industryFilter}
                <button onClick={() => setIndustryFilter('All')} className="hover:text-white ml-1">×</button>
              </span>
            )}
            {freshnessFilter !== 'All' && (
              <span className="px-2 py-0.5 rounded bg-slate-800 text-amber-300 border border-slate-700 flex items-center gap-1">
                Freshness: {freshnessFilter}
                <button onClick={() => setFreshnessFilter('All')} className="hover:text-white ml-1">×</button>
              </span>
            )}
            <button 
              onClick={() => {
                setSelectedDomain('All');
                setVerificationFilter('All');
                setIndustryFilter('All');
                setFreshnessFilter('All');
                setSearchQuery('');
              }} 
              className="text-cyan-400 hover:underline ml-2"
            >
              Reset All Filters
            </button>
          </div>
        )}
      </div>

      {/* Document Table with Trust & Freshness metadata */}
      <div className="p-5 rounded-xl bg-slate-900/90 border border-slate-800">
        <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-2">
          <div className="text-xs text-slate-300">
            Showing <strong className="text-cyan-400">{filteredDocs.length}</strong> of <strong className="text-slate-100">{documents.length}</strong> knowledge records
          </div>
          <div className="flex items-center gap-3 text-[11px] text-slate-400">
            <span className="flex items-center gap-1"><Globe className="w-3 h-3 text-cyan-400" /> Global</span>
            <span className="flex items-center gap-1"><Building className="w-3 h-3 text-purple-400" /> Industry</span>
            <span className="flex items-center gap-1"><Lock className="w-3 h-3 text-amber-400" /> Org (Private)</span>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400 font-semibold uppercase tracking-wider text-[10px]">
                <th className="py-2.5 px-3">Domain</th>
                <th className="py-2.5 px-3">Source & Authority</th>
                <th className="py-2.5 px-3">Document Title, Code & Revision</th>
                <th className="py-2.5 px-3">Jurisdiction</th>
                <th className="py-2.5 px-3">Trust & Reliability</th>
                <th className="py-2.5 px-3">Freshness & Review Date</th>
                <th className="py-2.5 px-3">Verification</th>
                <th className="py-2.5 px-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {filteredDocs.map((doc) => (
                <tr key={doc.id} className="hover:bg-slate-800/50 transition-colors group">
                  {/* Domain Tag */}
                  <td className="py-3 px-3 align-top whitespace-nowrap">
                    {getDomainBadge(doc.domain)}
                    {doc.domain === 'Organization Knowledge' && (
                      <div className="text-[9px] font-mono text-amber-400 mt-1 flex items-center gap-1">
                        <Lock className="w-2.5 h-2.5" />
                        <span>Organization-scoped</span>
                      </div>
                    )}
                  </td>

                  {/* Source Authority */}
                  <td className="py-3 px-3 align-top max-w-[200px]">
                    <div className="font-semibold text-slate-100 text-[12px]">{doc.source}</div>
                    <div className="text-[10px] text-slate-400 mt-0.5 leading-snug">
                      {doc.sourceAuthority || doc.source}
                    </div>
                    <div className="mt-1">
                      <span className="inline-block px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 text-[9px] font-mono border border-slate-700">
                        {doc.type}
                      </span>
                    </div>
                  </td>

                  {/* Title, Code, Revision */}
                  <td className="py-3 px-3 align-top max-w-sm">
                    <div className="font-semibold text-slate-200 group-hover:text-cyan-300 transition-colors text-[12px] leading-snug">
                      {doc.title}
                    </div>
                    <div className="text-[10px] font-mono text-slate-400 mt-1 flex items-center gap-2 flex-wrap">
                      <span className="text-cyan-300 font-semibold">{doc.documentCode}</span>
                      {doc.revision && (
                        <>
                          <span>•</span>
                          <span className="text-slate-300 bg-slate-800/80 px-1 rounded">{doc.revision}</span>
                        </>
                      )}
                      <span>•</span>
                      <span className="text-slate-400">{doc.topics.slice(0, 2).join(', ')}</span>
                    </div>
                  </td>

                  {/* Jurisdiction */}
                  <td className="py-3 px-3 align-top text-[11px] text-slate-300 whitespace-nowrap">
                    <div>{doc.jurisdiction}</div>
                    <div className="text-[10px] text-slate-500 font-mono mt-0.5">
                      Pub: {doc.publicationDate}
                    </div>
                  </td>

                  {/* Trust & Reliability */}
                  <td className="py-3 px-3 align-top whitespace-nowrap">
                    <div>{getReliabilityBadge(doc.reliability)}</div>
                    <div className="text-[10px] text-slate-400 font-mono mt-0.5">
                      Audit Score: {doc.reliability === 'Very High' ? '99.4%' : doc.reliability === 'High' ? '94.2%' : '82.0%'}
                    </div>
                  </td>

                  {/* Freshness & Review Date */}
                  <td className="py-3 px-3 align-top whitespace-nowrap">
                    <div>{getFreshnessBadge(doc.freshness)}</div>
                    <div className="text-[10px] font-mono text-slate-400 mt-1 flex items-center gap-1">
                      <Calendar className="w-3 h-3 text-slate-500" />
                      <span>Review: {doc.reviewDate || '2027-01-01'}</span>
                    </div>
                  </td>

                  {/* Verification Status */}
                  <td className="py-3 px-3 align-top whitespace-nowrap">
                    <span className={`text-[10px] font-mono px-2 py-0.5 rounded font-semibold inline-flex items-center gap-1 ${
                      doc.verification === 'Verified'
                        ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                        : doc.verification === 'Pending Review'
                        ? 'bg-amber-950 text-amber-300 border border-amber-800'
                        : 'bg-rose-950 text-rose-300 border border-rose-800'
                    }`}>
                      {doc.verification === 'Verified' && <CheckCircle2 className="w-3 h-3 text-emerald-400" />}
                      {doc.verification === 'Pending Review' && <Clock className="w-3 h-3 text-amber-400" />}
                      {doc.verification === 'Flagged' && <AlertTriangle className="w-3 h-3 text-rose-400" />}
                      <span>{doc.verification}</span>
                    </span>
                  </td>

                  {/* Action */}
                  <td className="py-3 px-3 align-top text-right whitespace-nowrap">
                    <div className="flex items-center justify-end gap-1.5">
                      <button
                        onClick={() => setSelectedDocDetails(doc)}
                        className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium transition-colors inline-flex items-center gap-1"
                        title="View Full Document Trust Card"
                      >
                        <Eye className="w-3 h-3" />
                        <span className="hidden sm:inline">Inspect</span>
                      </button>
                      <button
                        onClick={() => onSelectDocForValidation(doc.id)}
                        className="px-2.5 py-1 rounded bg-slate-800 hover:bg-cyan-600 hover:text-white text-slate-300 text-xs font-medium transition-colors inline-flex items-center gap-1"
                      >
                        <span>Validate</span>
                        <ChevronRight className="w-3 h-3" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modal: Full Trust Card Inspection */}
      {selectedDocDetails && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl p-6 space-y-5">
            {/* Modal Header */}
            <div className="flex items-start justify-between gap-4 border-b border-slate-800 pb-4">
              <div>
                <div className="flex items-center gap-2">
                  {getDomainBadge(selectedDocDetails.domain)}
                  {getFreshnessBadge(selectedDocDetails.freshness)}
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-cyan-300 border border-slate-700">
                    {selectedDocDetails.documentCode}
                  </span>
                </div>
                <h2 className="text-lg font-bold text-white mt-2">
                  {selectedDocDetails.title}
                </h2>
                <div className="text-xs text-slate-400 mt-0.5">
                  Published by <strong className="text-slate-200">{selectedDocDetails.source}</strong> ({selectedDocDetails.sourceAuthority})
                </div>
              </div>
              <button 
                onClick={() => setSelectedDocDetails(null)}
                className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
              >
                ✕
              </button>
            </div>

            {/* Scope Badge if Org */}
            {selectedDocDetails.domain === 'Organization Knowledge' && (
              <div className="p-3 rounded-lg bg-amber-950/40 border border-amber-700/60 flex items-center gap-2 text-xs text-amber-200">
                <Lock className="w-4 h-4 text-amber-400 shrink-0" />
                <div>
                  <strong>Organization-scoped knowledge: </strong>
                  This document belongs exclusively to Demo Energy & Engineering Ltd. and is isolated within private tenant storage.
                </div>
              </div>
            )}

            {/* Source Trust Grid */}
            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-3">
              <span className="text-[11px] font-mono uppercase tracking-wider text-cyan-400 font-bold flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
                <span>Verified Source Trust Profile</span>
              </span>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
                <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800">
                  <span className="text-[10px] text-slate-400 uppercase font-semibold">Source Authority</span>
                  <div className="font-semibold text-slate-200 mt-0.5">{selectedDocDetails.sourceAuthority || selectedDocDetails.source}</div>
                </div>
                <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800">
                  <span className="text-[10px] text-slate-400 uppercase font-semibold">Verification Status</span>
                  <div className="font-semibold text-emerald-300 mt-0.5">{selectedDocDetails.verificationStatus || selectedDocDetails.verification}</div>
                </div>
                <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800">
                  <span className="text-[10px] text-slate-400 uppercase font-semibold">Reliability Rating</span>
                  <div className="font-semibold text-cyan-300 mt-0.5">{selectedDocDetails.reliability}</div>
                </div>
                <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800">
                  <span className="text-[10px] text-slate-400 uppercase font-semibold">Publication Date</span>
                  <div className="font-semibold text-slate-200 mt-0.5">{selectedDocDetails.publicationDate}</div>
                </div>
                <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800">
                  <span className="text-[10px] text-slate-400 uppercase font-semibold">Revision / Version</span>
                  <div className="font-semibold text-slate-200 mt-0.5">{selectedDocDetails.revision || 'Standard Rev'}</div>
                </div>
                <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800">
                  <span className="text-[10px] text-slate-400 uppercase font-semibold">Jurisdiction</span>
                  <div className="font-semibold text-slate-200 mt-0.5">{selectedDocDetails.jurisdiction}</div>
                </div>
                <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800">
                  <span className="text-[10px] text-slate-400 uppercase font-semibold">Next Review Date</span>
                  <div className="font-semibold text-amber-300 mt-0.5">{selectedDocDetails.reviewDate || '2027-01-01'}</div>
                </div>
                <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800">
                  <span className="text-[10px] text-slate-400 uppercase font-semibold">Knowledge Freshness</span>
                  <div className="font-semibold text-emerald-400 mt-0.5">{selectedDocDetails.freshness || 'Current'}</div>
                </div>
                <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800">
                  <span className="text-[10px] text-slate-400 uppercase font-semibold">Applicable Industries</span>
                  <div className="font-semibold text-purple-300 mt-0.5">{selectedDocDetails.applicableIndustries.join(', ')}</div>
                </div>
              </div>
            </div>

            {/* Summary & Key Rules */}
            <div className="space-y-3">
              <span className="text-xs font-bold text-slate-300 uppercase tracking-wider">Executive Summary</span>
              <p className="text-xs text-slate-300 leading-relaxed bg-slate-950 p-3.5 rounded-lg border border-slate-800">
                {selectedDocDetails.summary}
              </p>

              <span className="text-xs font-bold text-slate-300 uppercase tracking-wider block pt-2">Extracted Deterministic Rules</span>
              <div className="space-y-2">
                {selectedDocDetails.extractedKeyRules.map((rule, idx) => (
                  <div key={idx} className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-300 flex items-start gap-2">
                    <span className="px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-400 font-mono text-[10px] shrink-0">{idx + 1}</span>
                    <span className="leading-relaxed">{rule}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Modal Actions */}
            <div className="flex items-center justify-between border-t border-slate-800 pt-4">
              <span className="text-[11px] font-mono text-slate-500">
                Lineage ID: {selectedDocDetails.id}
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setSelectedDocDetails(null)}
                  className="px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold"
                >
                  Close
                </button>
                <button
                  onClick={() => {
                    const docId = selectedDocDetails.id;
                    setSelectedDocDetails(null);
                    onSelectDocForValidation(docId);
                  }}
                  className="px-4 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold flex items-center gap-1.5 shadow"
                >
                  <FileCheck2 className="w-3.5 h-3.5" />
                  <span>Open in Validation Queue</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

