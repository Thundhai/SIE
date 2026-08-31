import React, { useState } from 'react';
import { 
  ShieldCheck, 
  Lock, 
  Eye, 
  FileCheck2, 
  UserCheck, 
  Cpu, 
  CheckCircle2, 
  AlertOctagon,
  Scale,
  Server,
  Layers,
  Sparkles,
  Database,
  ArrowDown,
  Globe2,
  Building2,
  Ban,
  ShieldAlert,
  Fingerprint,
  KeyRound,
  Download,
  Trash2,
  Clock,
  User,
  FileText,
  HelpCircle,
  ToggleLeft,
  ToggleRight,
  ChevronRight,
  Info
} from 'lucide-react';

export const GovernanceView: React.FC = () => {
  const [activeFindingTab, setActiveFindingTab] = useState<'lift' | 'gas' | 'vehicle'>('lift');
  const [crossOrgFederatedOptIn, setCrossOrgFederatedOptIn] = useState(false);

  const complianceCertifications = [
    { name: 'ISO 27001', desc: 'Information Security Management System Certified', status: 'Certified' },
    { name: 'SOC 2 Type II', desc: 'Enterprise Security, Availability & Confidentiality Audited', status: 'Audited' },
    { name: 'ISO 45001', desc: 'Occupational Health and Safety Systems Standard Aligned', status: 'Aligned' },
    { name: 'GDPR / Enterprise Privacy', desc: 'Isolated European & Regional Data Boundary Enforcement', status: 'Enforced' }
  ];

  const modelGovernanceSpecs = [
    { name: 'Causal Synthesis Bayesian Engine', version: 'v4.6.2', status: 'Active Production', drift: '0.012% (Nominal)', explainability: '100% Deterministic DAG' },
    { name: 'Regulatory Standards Parser', version: 'v2.1.0', status: 'Active Production', drift: '0.000% (Strict)', explainability: 'Direct Citation Tree' },
    { name: 'Prescriptive Action Generator', version: 'v3.8.4', status: 'Active Production', drift: '0.024% (Nominal)', explainability: 'Rule Matrix Lineage' }
  ];

  // AI Data Controls
  const aiDataControls = [
    {
      title: 'External AI Access',
      status: 'Controlled',
      color: 'emerald',
      desc: 'Zero customer data is shared with public LLMs or 3rd-party frontier model training pools.'
    },
    {
      title: 'Organization Data',
      status: 'Tenant-isolated',
      color: 'cyan',
      desc: 'Strict cryptographic separation with dedicated KMS tenant keys and virtual boundary enforcement.'
    },
    {
      title: 'Personal Data',
      status: 'Minimized',
      color: 'blue',
      desc: 'Automated PII pseudonymization and scrubbing before any semantic indexing occurs.'
    },
    {
      title: 'Data Encryption',
      status: 'Enabled',
      color: 'emerald',
      desc: 'AES-256 encryption at rest, TLS 1.3 in transit, with customer-managed key (BYOK) capability.'
    },
    {
      title: 'Audit Logging',
      status: 'Enabled',
      color: 'emerald',
      desc: 'Immutable, tamper-evident cryptographic logs recorded for every inference and query.'
    },
    {
      title: 'Data Retention',
      status: 'Configurable',
      color: 'amber',
      desc: 'Custom retention schedules (30-day, 1-year, 7-year statutory or automated purging).'
    },
    {
      title: 'Data Export',
      status: 'Available',
      color: 'purple',
      desc: 'One-click full extraction of raw observations, Bayesian graphs, and audit history in JSON/CSV.'
    },
    {
      title: 'Data Deletion',
      status: 'Available',
      color: 'rose',
      desc: 'Instant cryptographic data shredding and verifiable tenant purge upon request.'
    }
  ];

  // Sample finding transparency data
  const findingTransparencyData = {
    lift: {
      title: 'Finding #SIE-TR-9021: Yard 4 Lifting Operations Precursor Surge',
      dataAccessed: 'OBS-1021 (Synthetic sling UV degradation), INC-2026-041 (Trailer near miss), INSP-8831 (Spreader beam proof load non-conformance), LMS-4912 (Rigger certification log)',
      knowledgeAccessed: 'HSE UK L113 (LOLER Reg 9 Thorough Examination), OSHA 1926 Subpart CC (Crane Safety), DEE-SOP-LIFT-042-Rev6 (Tandem Rigging Procedure)',
      modelUsed: 'Causal Synthesis Bayesian Engine v4.6.2 (Deterministic Directed Acyclic Graph)',
      timestamp: '2026-08-31 08:35:12 UTC',
      tenant: 'ORG-ENG-4921-NG (Demo Energy & Engineering Ltd. - Isolated Partition #1)',
      user: 'Tariq Ibrahim (Area HSE Superintendent - Employee ID: EMP-4912)',
      evidence: '34% overdue rigging certification velocity, 28% contractor turnover surge, 14% precursor anomaly score surge in Yard 4 over 30-day lookback',
      result: 'Elevated Risk Forecast (78% Probability, SIF Precursor) → Prescribed Intervention: Quarantine uncertified spreader beams & mandate supervisor toolbox reset'
    },
    gas: {
      title: 'Finding #SIE-TR-9022: Compression Train B Flange Acoustic Resonance',
      dataAccessed: 'IOT-GAS-SNIF-B104 (40ppm CH4 trace), CMMS-WO-8821 (Flange bolt torque work order), VIB-SENS-09 (High-frequency harmonic vibration)',
      knowledgeAccessed: 'API 570 5th Ed (Piping Inspection Code), ASME PCC-1 (Flanged Joint Assembly Guidelines), DEE-SOP-MNT-109 (Gas Plant Integrity)',
      modelUsed: 'Acoustic Resonance & Precursor Anomaly Detector v2.4',
      timestamp: '2026-08-31 08:14:02 UTC',
      tenant: 'ORG-ENG-4921-NG (Demo Energy & Engineering Ltd. - Isolated Partition #1)',
      user: 'Engr. Folake Adeleke (Operations Integrity Lead - Employee ID: EMP-1082)',
      evidence: 'Co-occurrence of 180Hz cyclic vibration spike with 40ppm trace hydrocarbon sniffing within 48h of cold restart',
      result: 'Medium Risk Forecast (48% Probability) → Prescribed Intervention: Schedule ultrasonic phased array inspection within 24 hours'
    },
    vehicle: {
      title: 'Finding #SIE-TR-9023: Logistics Gate 2 Vehicle-Pedestrian Conflict',
      dataAccessed: 'INC-2026-041 (Trailer reversed within 1.5m of walkway), OBS-9812 (Inadequate illumination reported at Gate 2 buffer)',
      knowledgeAccessed: 'HSE UK HSG136 (Workplace Transport Safety), OSHA 1910.178 (Powered Industrial Trucks)',
      modelUsed: 'Spatial Conflict & Lighting Correlation Matrix v3.1',
      timestamp: '2026-08-30 21:50:00 UTC',
      tenant: 'ORG-ENG-4921-NG (Demo Energy & Engineering Ltd. - Isolated Partition #1)',
      user: 'Automated Ingestion Gateway (Triggered via SAP EHSM Webhook)',
      evidence: 'Illumination below 20 lux combined with absence of dedicated reversing spotter during dusk shift change',
      result: 'Elevated Risk Forecast (61% Probability) → Prescribed Intervention: Realign temporary floodlight tower & deploy physical water-filled barriers'
    }
  };

  const selectedFinding = findingTransparencyData[activeFindingTab];

  return (
    <div className="space-y-8 animate-in fade-in duration-200">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl sm:text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
              <ShieldCheck className="w-6 h-6 text-emerald-400" />
              <span>Privacy & AI Governance</span>
            </h1>
            <span className="text-[11px] font-mono px-2.5 py-0.5 rounded-full bg-emerald-950 text-emerald-300 border border-emerald-800 font-semibold">
              Zero Multi-Tenant Bleed
            </span>
          </div>
          <p className="text-xs sm:text-sm text-slate-400 mt-1 max-w-3xl leading-relaxed">
            Cryptographic tenant isolation, complete explainability, zero public LLM training data leakage, and auditable lineage.
          </p>
        </div>

        <div className="flex items-center gap-2 text-xs text-slate-300 font-mono p-2 px-3 rounded-lg bg-slate-900 border border-slate-800">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span>Tenant: <strong>ORG-ENG-4921-NG (Strict Sandbox)</strong></span>
        </div>
      </div>

      {/* SECTION 1: DATA ISOLATION ARCHITECTURE */}
      <div className="p-6 rounded-xl bg-slate-900/90 border border-slate-800 space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 pb-3 border-b border-slate-800">
          <div>
            <div className="flex items-center gap-2">
              <Database className="w-5 h-5 text-cyan-400" />
              <h2 className="text-base sm:text-lg font-bold text-white tracking-tight">
                Data Isolation Architecture
              </h2>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Strict multi-tenant cryptographic boundaries. Organization data is strictly private and never shared.
            </p>
          </div>

          <div className="flex items-center gap-2 text-[11px] font-mono text-emerald-400 bg-emerald-950/80 px-2.5 py-1 rounded border border-emerald-700/60 font-semibold shrink-0">
            <Lock className="w-3.5 h-3.5" />
            <span>Air-Gapped Tenant Partitions</span>
          </div>
        </div>

        {/* Visual Architecture Diagram */}
        <div className="space-y-6">
          {/* Top Layer: Global Knowledge */}
          <div className="p-4 rounded-xl bg-gradient-to-r from-blue-950/50 via-cyan-950/40 to-blue-950/50 border border-cyan-700/60 text-center space-y-2 relative shadow-md">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-cyan-950 border border-cyan-600 text-cyan-200 text-xs font-mono font-bold uppercase tracking-wider">
              <Globe2 className="w-4 h-4 text-cyan-400" />
              <span>GLOBAL KNOWLEDGE</span>
            </div>
            <p className="text-xs sm:text-sm font-semibold text-slate-200 max-w-2xl mx-auto">
              436+ Verified International Standards, Statutory Regulations & Open HSE Codes
            </p>
            <p className="text-[11px] text-slate-400 font-mono">
              OSHA • ISO 45001 • API 570 • UK HSE LOLER / COMAH • IOGP • NFPA
            </p>
          </div>

          {/* Down Arrow / Dissemination Flow */}
          <div className="flex flex-col items-center justify-center space-y-1">
            <span className="text-[11px] font-mono font-bold text-cyan-400 bg-slate-950 px-3 py-1 rounded-full border border-cyan-800 shadow-sm flex items-center gap-1.5">
              <ArrowDown className="w-3.5 h-3.5" />
              <span>Available to authorized tenants</span>
            </span>
          </div>

          {/* Three Isolated Tenant Columns with Physical Barrier Indication */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 relative">
            {/* Organization A */}
            <div className="p-5 rounded-xl bg-slate-950 border-2 border-emerald-600/80 space-y-3 relative shadow-lg">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="p-2 rounded-lg bg-emerald-950 border border-emerald-700 text-emerald-400">
                    <Building2 className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-white">ORGANIZATION A</h3>
                    <span className="text-[10px] font-mono text-emerald-400 font-semibold block">ORG-ENG-4921-NG</span>
                  </div>
                </div>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-700 font-bold">
                  Your Tenant (Active)
                </span>
              </div>

              <div className="p-3 rounded-lg bg-emerald-950/20 border border-emerald-800/40 space-y-1.5">
                <div className="text-xs font-bold text-emerald-300 flex items-center gap-1.5">
                  <Lock className="w-3.5 h-3.5" />
                  <span>Private intelligence</span>
                </div>
                <ul className="text-[11px] text-slate-300 space-y-1 list-disc list-inside">
                  <li>Proprietary field hazard observations</li>
                  <li>Internal near-miss & SIF investigation reports</li>
                  <li>Worker competency & contractor LMS records</li>
                  <li>Dedicated Bayesian risk weighting matrix</li>
                </ul>
              </div>

              <div className="text-[10px] font-mono text-emerald-400/80 flex items-center gap-1 pt-1">
                <ShieldCheck className="w-3 h-3" />
                <span>Encrypted with Customer KMS Key #A-891</span>
              </div>
            </div>

            {/* Cryptographic Isolation Wall Indicator (Visible on desktop between cards) */}

            {/* Organization B */}
            <div className="p-5 rounded-xl bg-slate-950 border border-slate-800 space-y-3 relative opacity-85 hover:opacity-100 transition-opacity">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="p-2 rounded-lg bg-slate-900 border border-slate-700 text-slate-300">
                    <Building2 className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-white">ORGANIZATION B</h3>
                    <span className="text-[10px] font-mono text-slate-400 block">ORG-PETRO-8104-UK</span>
                  </div>
                </div>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-900 text-slate-400 border border-slate-800">
                  Isolated Tenant
                </span>
              </div>

              <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800 space-y-1.5">
                <div className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
                  <Lock className="w-3.5 h-3.5 text-slate-400" />
                  <span>Private intelligence</span>
                </div>
                <ul className="text-[11px] text-slate-400 space-y-1 list-disc list-inside">
                  <li>Proprietary offshore crane logs</li>
                  <li>Internal audit findings & PTW tickets</li>
                  <li>Confidential process hazard evaluations</li>
                  <li>Dedicated isolated Bayesian graph</li>
                </ul>
              </div>

              <div className="text-[10px] font-mono text-slate-400 flex items-center gap-1 pt-1">
                <ShieldCheck className="w-3 h-3" />
                <span>Encrypted with Customer KMS Key #B-334</span>
              </div>
            </div>

            {/* Organization C */}
            <div className="p-5 rounded-xl bg-slate-950 border border-slate-800 space-y-3 relative opacity-85 hover:opacity-100 transition-opacity">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="p-2 rounded-lg bg-slate-900 border border-slate-700 text-slate-300">
                    <Building2 className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-white">ORGANIZATION C</h3>
                    <span className="text-[10px] font-mono text-slate-400 block">ORG-CONSTR-2291-US</span>
                  </div>
                </div>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-900 text-slate-400 border border-slate-800">
                  Isolated Tenant
                </span>
              </div>

              <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800 space-y-1.5">
                <div className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
                  <Lock className="w-3.5 h-3.5 text-slate-400" />
                  <span>Private intelligence</span>
                </div>
                <ul className="text-[11px] text-slate-400 space-y-1 list-disc list-inside">
                  <li>Civil works heavy equipment telemetry</li>
                  <li>Subcontractor safety non-conformances</li>
                  <li>Private site risk assessments (HIRAs)</li>
                  <li>Dedicated isolated Bayesian graph</li>
                </ul>
              </div>

              <div className="text-[10px] font-mono text-slate-400 flex items-center gap-1 pt-1">
                <ShieldCheck className="w-3 h-3" />
                <span>Encrypted with Customer KMS Key #C-719</span>
              </div>
            </div>
          </div>

          {/* Prominent Impossibility Banner */}
          <div className="p-4 rounded-xl bg-rose-950/20 border-2 border-rose-600/60 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-md">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-lg bg-rose-950 border border-rose-700 text-rose-400 shrink-0">
                <Ban className="w-5 h-5 text-rose-400" />
              </div>
              <div>
                <span className="text-xs sm:text-sm font-bold text-white block">
                  Zero Cross-Tenant Data Leakage: Raw Organization Data is NEVER Shared
                </span>
                <p className="text-[11px] text-rose-200/90 leading-relaxed mt-0.5">
                  Organization A cannot see, query, or infer Organization B or C's records. Each tenant partition maintains a hard cryptographic wall, independent encryption keys, and isolated database schemas.
                </p>
              </div>
            </div>
            <div className="text-[10px] font-mono text-rose-300 bg-rose-950/80 px-2.5 py-1 rounded border border-rose-700 font-bold shrink-0 self-start sm:self-auto">
              NO CROSS-TENANT DATA FLOW
            </div>
          </div>
        </div>
      </div>

      {/* SECTION 2: AI DATA CONTROLS */}
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <div className="flex items-center gap-2">
              <ShieldAlert className="w-5 h-5 text-cyan-400" />
              <h2 className="text-base sm:text-lg font-bold text-white tracking-tight">
                AI Data Controls
              </h2>
            </div>
            <p className="text-xs text-slate-400">
              Granular enterprise governance controls enforcing tenant safety, PII minimization, and full lifecycle sovereignty.
            </p>
          </div>
          <span className="text-xs font-mono text-cyan-400 bg-cyan-950/80 px-2.5 py-1 rounded border border-cyan-800 font-semibold">
            8 Safeguard Directives Active
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {aiDataControls.map((ctrl) => {
            const isEmerald = ctrl.color === 'emerald';
            const isCyan = ctrl.color === 'cyan';
            const isBlue = ctrl.color === 'blue';
            const isAmber = ctrl.color === 'amber';
            const isPurple = ctrl.color === 'purple';
            const isRose = ctrl.color === 'rose';

            return (
              <div 
                key={ctrl.title}
                className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 flex flex-col justify-between space-y-2.5 hover:border-slate-700 transition-colors shadow-sm"
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-bold text-white">{ctrl.title}</span>
                  <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border shrink-0 ${
                    isEmerald ? 'bg-emerald-950 text-emerald-300 border-emerald-700' :
                    isCyan ? 'bg-cyan-950 text-cyan-300 border-cyan-700' :
                    isBlue ? 'bg-blue-950 text-blue-300 border-blue-700' :
                    isAmber ? 'bg-amber-950 text-amber-300 border-amber-700' :
                    isPurple ? 'bg-purple-950 text-purple-300 border-purple-700' :
                    'bg-rose-950 text-rose-300 border-rose-700'
                  }`}>
                    {ctrl.status}
                  </span>
                </div>
                <p className="text-[11px] text-slate-400 leading-snug">
                  {ctrl.desc}
                </p>
                <div className="pt-2 border-t border-slate-800/80 text-[10px] font-mono text-slate-500 flex items-center justify-between">
                  <span>Policy ID: SIE-POL-{ctrl.title.substring(0, 3).toUpperCase()}</span>
                  <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* SECTION 3: AI PROCESSING TRANSPARENCY */}
      <div className="p-6 rounded-xl bg-slate-900/90 border border-slate-800 space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 pb-3 border-b border-slate-800">
          <div>
            <div className="flex items-center gap-2">
              <Eye className="w-5 h-5 text-purple-400" />
              <h2 className="text-base sm:text-lg font-bold text-white tracking-tight">
                AI Processing Transparency
              </h2>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Complete explainability and auditable data lineage for an intelligence finding.
            </p>
          </div>

          {/* Finding Selector Tabs */}
          <div className="flex items-center gap-1.5 p-1 rounded-lg bg-slate-950 border border-slate-800 text-xs font-mono">
            <button
              onClick={() => setActiveFindingTab('lift')}
              className={`px-2.5 py-1 rounded transition-colors ${activeFindingTab === 'lift' ? 'bg-purple-600 text-white font-bold' : 'text-slate-400 hover:text-slate-200'}`}
            >
              Lifting Finding #9021
            </button>
            <button
              onClick={() => setActiveFindingTab('gas')}
              className={`px-2.5 py-1 rounded transition-colors ${activeFindingTab === 'gas' ? 'bg-purple-600 text-white font-bold' : 'text-slate-400 hover:text-slate-200'}`}
            >
              Gas Flange Finding #9022
            </button>
            <button
              onClick={() => setActiveFindingTab('vehicle')}
              className={`px-2.5 py-1 rounded transition-colors ${activeFindingTab === 'vehicle' ? 'bg-purple-600 text-white font-bold' : 'text-slate-400 hover:text-slate-200'}`}
            >
              Vehicle Finding #9023
            </button>
          </div>
        </div>

        {/* Selected Finding Transparency Inspector Card */}
        <div className="p-5 rounded-xl bg-slate-950 border border-purple-800/60 space-y-4 shadow-md">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-slate-800">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-purple-400" />
              <span>{selectedFinding.title}</span>
            </h3>
            <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-purple-950 text-purple-300 border border-purple-700">
              Audit Verified • Deterministic Lineage
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
            {/* Field 1: Data accessed */}
            <div className="p-3.5 rounded-lg bg-slate-900/90 border border-slate-800 space-y-1">
              <span className="text-[10px] font-mono uppercase text-cyan-400 font-bold block flex items-center gap-1.5">
                <Database className="w-3 h-3" />
                <span>Data accessed</span>
              </span>
              <p className="text-slate-200 font-mono text-[11px] leading-relaxed">
                {selectedFinding.dataAccessed}
              </p>
            </div>

            {/* Field 2: Knowledge accessed */}
            <div className="p-3.5 rounded-lg bg-slate-900/90 border border-slate-800 space-y-1">
              <span className="text-[10px] font-mono uppercase text-blue-400 font-bold block flex items-center gap-1.5">
                <Globe2 className="w-3 h-3" />
                <span>Knowledge accessed</span>
              </span>
              <p className="text-slate-200 font-mono text-[11px] leading-relaxed">
                {selectedFinding.knowledgeAccessed}
              </p>
            </div>

            {/* Field 3: Model used */}
            <div className="p-3.5 rounded-lg bg-slate-900/90 border border-slate-800 space-y-1">
              <span className="text-[10px] font-mono uppercase text-purple-400 font-bold block flex items-center gap-1.5">
                <Cpu className="w-3 h-3" />
                <span>Model used</span>
              </span>
              <p className="text-slate-200 font-mono text-[11px]">
                {selectedFinding.modelUsed}
              </p>
            </div>

            {/* Field 4: Timestamp */}
            <div className="p-3.5 rounded-lg bg-slate-900/90 border border-slate-800 space-y-1">
              <span className="text-[10px] font-mono uppercase text-amber-400 font-bold block flex items-center gap-1.5">
                <Clock className="w-3 h-3" />
                <span>Timestamp</span>
              </span>
              <p className="text-slate-200 font-mono text-[11px]">
                {selectedFinding.timestamp}
              </p>
            </div>

            {/* Field 5: Tenant */}
            <div className="p-3.5 rounded-lg bg-slate-900/90 border border-slate-800 space-y-1">
              <span className="text-[10px] font-mono uppercase text-emerald-400 font-bold block flex items-center gap-1.5">
                <Building2 className="w-3 h-3" />
                <span>Tenant</span>
              </span>
              <p className="text-slate-200 font-mono text-[11px]">
                {selectedFinding.tenant}
              </p>
            </div>

            {/* Field 6: User */}
            <div className="p-3.5 rounded-lg bg-slate-900/90 border border-slate-800 space-y-1">
              <span className="text-[10px] font-mono uppercase text-cyan-400 font-bold block flex items-center gap-1.5">
                <User className="w-3 h-3" />
                <span>User</span>
              </span>
              <p className="text-slate-200 font-mono text-[11px]">
                {selectedFinding.user}
              </p>
            </div>

            {/* Field 7: Evidence (Full Width) */}
            <div className="p-3.5 rounded-lg bg-slate-900/90 border border-slate-800 space-y-1 md:col-span-2">
              <span className="text-[10px] font-mono uppercase text-rose-400 font-bold block flex items-center gap-1.5">
                <FileText className="w-3 h-3" />
                <span>Evidence</span>
              </span>
              <p className="text-slate-200 text-xs leading-relaxed">
                {selectedFinding.evidence}
              </p>
            </div>

            {/* Field 8: Result (Full Width) */}
            <div className="p-3.5 rounded-lg bg-emerald-950/30 border border-emerald-800/80 space-y-1 md:col-span-2">
              <span className="text-[10px] font-mono uppercase text-emerald-300 font-bold block flex items-center gap-1.5">
                <CheckCircle2 className="w-3 h-3" />
                <span>Result</span>
              </span>
              <p className="text-emerald-100 text-xs font-medium leading-relaxed">
                {selectedFinding.result}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* SECTION 4: CROSS-ORGANIZATION LEARNING */}
      <div className="p-6 rounded-xl bg-slate-900/90 border border-slate-800 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 pb-3 border-b border-slate-800">
          <div>
            <div className="flex items-center gap-2">
              <Scale className="w-5 h-5 text-amber-400" />
              <h2 className="text-base sm:text-lg font-bold text-white tracking-tight">
                Cross-Organization Learning
              </h2>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Strict governance boundary regarding model training and cross-tenant intelligence sharing.
            </p>
          </div>

          <div className="flex items-center gap-2 text-xs font-mono px-3 py-1 rounded-lg bg-slate-950 border border-slate-800">
            <span className="text-slate-400">Status:</span>
            <span className="font-bold text-rose-400 flex items-center gap-1.5">
              <Ban className="w-3.5 h-3.5" />
              <span>Disabled by default</span>
            </span>
          </div>
        </div>

        {/* Prominent Formal Explanation Statement */}
        <div className="p-4 rounded-xl bg-slate-950 border border-amber-800/60 space-y-3">
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-lg bg-amber-950 border border-amber-800 text-amber-400 shrink-0">
              <Info className="w-5 h-5" />
            </div>
            <div className="space-y-1.5">
              <span className="text-xs font-bold text-amber-300 uppercase tracking-wider block font-mono">
                Mandatory Governance Guarantee
              </span>
              <p className="text-xs sm:text-sm text-slate-200 font-medium leading-relaxed italic">
                "Organization data is not automatically used to train or expose intelligence to other organizations. Any future aggregated learning capability must be explicitly governed, anonymized where appropriate and contractually permitted."
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2 text-[11px] font-mono border-t border-slate-800/80">
            <div className="p-2.5 rounded bg-slate-900/80 border border-slate-800 flex items-center justify-between">
              <span className="text-slate-400">Federated Training:</span>
              <strong className="text-rose-400">Blocked (Opt-In Only)</strong>
            </div>
            <div className="p-2.5 rounded bg-slate-900/80 border border-slate-800 flex items-center justify-between">
              <span className="text-slate-400">Differential Privacy:</span>
              <strong className="text-emerald-400">Enforced (ε=0.1)</strong>
            </div>
            <div className="p-2.5 rounded bg-slate-900/80 border border-slate-800 flex items-center justify-between">
              <span className="text-slate-400">Contractual Consent:</span>
              <strong className="text-amber-300">Explicit DPA Required</strong>
            </div>
          </div>
        </div>
      </div>

      {/* Model Registry & Active Versions */}
      <div className="p-6 rounded-xl bg-slate-900/90 border border-slate-800 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <Cpu className="w-4 h-4 text-cyan-400" />
              <span>Production AI Model Registry</span>
            </h3>
            <p className="text-[11px] text-slate-400">Active machine learning weights, version provenance, and statistical drift diagnostics</p>
          </div>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800">
            3 Production Models Live
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400 font-semibold uppercase tracking-wider text-[10px]">
                <th className="py-2.5 px-3">Model Architecture</th>
                <th className="py-2.5 px-3">Version</th>
                <th className="py-2.5 px-3">Runtime Status</th>
                <th className="py-2.5 px-3">Statistical Drift</th>
                <th className="py-2.5 px-3">Explainability Mode</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {modelGovernanceSpecs.map((m, idx) => (
                <tr key={idx} className="hover:bg-slate-800/50 transition-colors">
                  <td className="py-3 px-3 font-semibold text-slate-100">{m.name}</td>
                  <td className="py-3 px-3 font-mono text-cyan-400">{m.version}</td>
                  <td className="py-3 px-3">
                    <span className="px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800 font-mono text-[10px]">
                      {m.status}
                    </span>
                  </td>
                  <td className="py-3 px-3 font-mono text-slate-300">{m.drift}</td>
                  <td className="py-3 px-3 font-mono text-emerald-400 font-semibold">{m.explainability}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Compliance & Regulatory Certifications Strip */}
      <div className="p-6 rounded-xl bg-slate-900/90 border border-slate-800 space-y-4">
        <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
          <FileCheck2 className="w-4 h-4 text-emerald-400" />
          <span>Enterprise Compliance & Industry Certifications</span>
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {complianceCertifications.map((cert) => (
            <div key={cert.name} className="p-4 rounded-lg bg-slate-950/70 border border-slate-800 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-bold text-xs text-white">{cert.name}</span>
                <span className="text-[10px] font-mono font-bold px-1.5 py-0.2 rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
                  {cert.status}
                </span>
              </div>
              <p className="text-[11px] text-slate-400 leading-snug">{cert.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

