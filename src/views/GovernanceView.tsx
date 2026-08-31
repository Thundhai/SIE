import React from 'react';
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
  Sparkles
} from 'lucide-react';

export const GovernanceView: React.FC = () => {
  const complianceCertifications = [
    { name: 'ISO 27001', desc: 'Information Security Management System Certified', status: 'Certified' },
    { name: 'SOC 2 Type II', desc: 'Enterprise Security, Availability & Confidentiality Audited', status: 'Audited' },
    { name: 'ISO 45001', desc: 'Occupational Health and Safety Systems Standard Aligned', status: 'Aligned' },
    { name: 'GDPR / Enterprise Privacy', desc: 'Isolated European & Regional Data Boundary Enforcement', status: 'Enforced' }
  ];

  const modelGovernanceSpecs = [
    { name: 'Causal Synthesis Bayesian Engine', version: 'v4.6.2', status: 'Active Production', drift: '0.012% (Nominal)', explainability: '100% Deterministic' },
    { name: 'Regulatory Standards Parser', version: 'v2.1.0', status: 'Active Production', drift: '0.000% (Strict)', explainability: 'Direct Citation Tree' },
    { name: 'Prescriptive Action Generator', version: 'v3.8.4', status: 'Active Production', drift: '0.024% (Nominal)', explainability: 'Rule Matrix' }
  ];

  return (
    <div className="space-y-6 animate-in fade-in duration-200">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl sm:text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
              <ShieldCheck className="w-6 h-6 text-emerald-400" />
              <span>Privacy & AI Governance</span>
            </h1>
            <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-300 border border-emerald-800">
              Enterprise Trust & Safeguards
            </span>
          </div>
          <p className="text-xs sm:text-sm text-slate-400 mt-1 max-w-3xl leading-relaxed">
            Cryptographic tenant isolation, complete explainability, zero public LLM training data leakage, and human-in-the-loop safety approvals.
          </p>
        </div>

        <div className="flex items-center gap-2 text-xs text-slate-400 font-mono">
          <span className="w-2 h-2 rounded-full bg-emerald-400" />
          <span>Tenant: Demo Energy & Engineering Ltd. (Isolated)</span>
        </div>
      </div>

      {/* 4 Core Pillars of Trust Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {/* Pillar 1: Data Privacy & Tenant Boundary */}
        <div className="p-6 rounded-xl bg-slate-900/90 border border-slate-800 space-y-3">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-cyan-950 border border-cyan-800 text-cyan-400">
              <Lock className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-white">1. Strict Tenant Isolation & Zero Data Leakage</h3>
              <p className="text-[11px] text-slate-400">AES-256 at rest, TLS 1.3 in transit, Dedicated Encryption Keys</p>
            </div>
          </div>
          <p className="text-xs text-slate-300 leading-relaxed">
            Your proprietary safety records, near-miss reports, contractor names, and operational telemetry are strictly isolated in a dedicated tenant partition. Safelytic Intelligence Engine <strong className="text-emerald-300">never sends customer data to public LLMs</strong> or third-party training pools.
          </p>
          <div className="p-3 rounded-lg bg-slate-950/70 border border-slate-800 text-[11px] text-slate-400 font-mono">
            Isolated VPC • Hardware Security Module (HSM) Encryption Key: Encrypted
          </div>
        </div>

        {/* Pillar 2: Explainability & No Black Box AI */}
        <div className="p-6 rounded-xl bg-slate-900/90 border border-slate-800 space-y-3">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-purple-950 border border-purple-800 text-purple-400">
              <Eye className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-white">2. Full Explainability (No Black-Box Output)</h3>
              <p className="text-[11px] text-slate-400">Deterministic Causal Graphs & Verifiable Lineage</p>
            </div>
          </div>
          <p className="text-xs text-slate-300 leading-relaxed">
            Every risk prediction, probability score, and intervention recommendation provides a transparent causal factor chain and clickable source citations pointing to verified regulatory documents or exact internal observation IDs.
          </p>
          <div className="p-3 rounded-lg bg-slate-950/70 border border-slate-800 text-[11px] text-slate-400 font-mono">
            Bayesian Directed Acyclic Graph (DAG) • 100% Auditable Lineage
          </div>
        </div>

        {/* Pillar 3: Human-in-the-Loop Safeguards */}
        <div className="p-6 rounded-xl bg-slate-900/90 border border-slate-800 space-y-3">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-emerald-950 border border-emerald-800 text-emerald-400">
              <UserCheck className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-white">3. Human-in-the-Loop Safety Safeguards</h3>
              <p className="text-[11px] text-slate-400">Expert Approval Thresholds for High-Consequence Actions</p>
            </div>
          </div>
          <p className="text-xs text-slate-300 leading-relaxed">
            SIE operates as an advisory intelligence engine. High-consequence interventions, work stoppages, and critical regulatory updates require explicit sign-off from designated HSE Managers or CMIOSH safety professionals before field deployment.
          </p>
          <div className="p-3 rounded-lg bg-slate-950/70 border border-slate-800 text-[11px] text-slate-400 font-mono">
            Role-Based Access Control (RBAC) • Mandatory CMIOSH Review Gates
          </div>
        </div>

        {/* Pillar 4: Model Drift & Calibration Governance */}
        <div className="p-6 rounded-xl bg-slate-900/90 border border-slate-800 space-y-3">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-amber-950 border border-amber-800 text-amber-400">
              <Scale className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-white">4. Continuous Model Calibration & Drift Audit</h3>
              <p className="text-[11px] text-slate-400">Dynamic Performance Benchmarking Against Real Outcomes</p>
            </div>
          </div>
          <p className="text-xs text-slate-300 leading-relaxed">
            The closed-loop learning engine continuously tracks actual post-intervention telemetry against predicted trajectory curves. When variance exceeds nominal thresholds, automated recalibration is paused until expert peer review.
          </p>
          <div className="p-3 rounded-lg bg-slate-950/70 border border-slate-800 text-[11px] text-slate-400 font-mono">
            Automated Kolmogorov-Smirnov Drift Testing • Real-time Health
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
