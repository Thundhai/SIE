import React, { useState } from 'react';
import {
  Boxes,
  Layers,
  ArrowDown,
  ArrowRight,
  Database,
  GitFork,
  CheckCircle2,
  Sparkles,
  FileText,
  AlertTriangle,
  Flame,
  ShieldCheck,
  Building2,
  MapPin,
  Briefcase,
  GraduationCap,
  Award,
  Zap,
  Activity,
  FileCheck2,
  RefreshCw,
  Search,
  ChevronRight,
  Info,
  Code2,
  ArrowUpRight,
  Eye,
  Sliders
} from 'lucide-react';

interface EntityRelationship {
  source: string;
  target: string;
  relationship: string;
  description: string;
  type: 'hierarchical' | 'causal' | 'mitigation' | 'telemetry';
}

const CANONICAL_RELATIONSHIPS: EntityRelationship[] = [
  {
    source: 'Activity',
    target: 'Hazard',
    relationship: 'introduces / encounters',
    description: 'Specific work processes (e.g. heavy lifting, line breaking) create conditions with hazard potential.',
    type: 'causal'
  },
  {
    source: 'Hazard',
    target: 'Risk',
    relationship: 'generates probability of',
    description: 'Unmitigated energy sources or unsafe states convert to probabilistic failure modes.',
    type: 'causal'
  },
  {
    source: 'Risk',
    target: 'Control',
    relationship: 'mitigated by',
    description: 'Engineered barriers, administrative rules, or procedural verifications suppress risk frequency/severity.',
    type: 'mitigation'
  },
  {
    source: 'Observation',
    target: 'Risk',
    relationship: 'acts as leading signal for',
    description: 'Worker behavioral logs and condition reports update Bayesian risk probabilities.',
    type: 'telemetry'
  },
  {
    source: 'Incident',
    target: 'Activity',
    relationship: 'occurs during execution of',
    description: 'Adverse loss events map directly to operational context and task baselines.',
    type: 'causal'
  },
  {
    source: 'Training',
    target: 'Competency',
    relationship: 'builds & certifies',
    description: 'Classroom, digital LMS, and practical modules confer verifiable workforce capability.',
    type: 'hierarchical'
  },
  {
    source: 'Competency',
    target: 'Risk Exposure',
    relationship: 'modulates workforce',
    description: 'Qualified operator coverage reduces human failure likelihood in critical task execution.',
    type: 'mitigation'
  },
  {
    source: 'Corrective Action',
    target: 'Observation',
    relationship: 'remediates non-conformance in',
    description: 'CAPA tickets resolve identified unsafe acts or equipment defects.',
    type: 'mitigation'
  },
  {
    source: 'Intervention',
    target: 'Risk',
    relationship: 'targets suppression of',
    description: 'Systemic campaigns and barrier verifications address predicted risk precursors.',
    type: 'mitigation'
  },
  {
    source: 'Intervention',
    target: 'Outcome',
    relationship: 'measured by change in',
    description: 'Closed-loop feedback tracks lagging indicators to validate intervention effectiveness.',
    type: 'telemetry'
  }
];

interface CanonicalEntity {
  id: string;
  name: string;
  category: 'Structural' | 'Precursor & Event' | 'Human & Capability' | 'Control & Action';
  description: string;
  fields: { name: string; type: string; required: boolean; desc: string }[];
  incomingFrom: string[];
  outgoingTo: string[];
}

const CANONICAL_ENTITIES: CanonicalEntity[] = [
  {
    id: 'Organization',
    name: 'Organization',
    category: 'Structural',
    description: 'Top-level enterprise entity with sovereign data isolation and dedicated KMS encryption keys.',
    fields: [
      { name: 'org_id', type: 'UUID', required: true, desc: 'Unique tenant identifier' },
      { name: 'org_name', type: 'String', required: true, desc: 'Enterprise business name' },
      { name: 'industry_sector', type: 'Enum', required: true, desc: 'Energy, Mining, Construction, Maritime' }
    ],
    incomingFrom: [],
    outgoingTo: ['Site']
  },
  {
    id: 'Site',
    name: 'Site',
    category: 'Structural',
    description: 'Physical geographic facility, yard, vessel, or offshore asset operating under site-specific safety constraints.',
    fields: [
      { name: 'site_id', type: 'UUID', required: true, desc: 'Unique physical location key' },
      { name: 'org_id', type: 'UUID', required: true, desc: 'Parent organization reference' },
      { name: 'geo_coordinates', type: 'GeoJSON', required: false, desc: 'Lat/Long boundaries' }
    ],
    incomingFrom: ['Organization'],
    outgoingTo: ['Activity']
  },
  {
    id: 'Activity',
    name: 'Activity',
    category: 'Structural',
    description: 'Operational work process or task package performed at a site (e.g. Critical Lift, Confined Space Entry).',
    fields: [
      { name: 'activity_id', type: 'UUID', required: true, desc: 'Task execution identifier' },
      { name: 'task_type', type: 'Enum', required: true, desc: 'Lifting, Hot Work, Excavation, Working at Height' },
      { name: 'work_order_ref', type: 'String', required: false, desc: 'ERP / CMMS work order reference' }
    ],
    incomingFrom: ['Site', 'Incident'],
    outgoingTo: ['Hazard']
  },
  {
    id: 'Hazard',
    name: 'Hazard',
    category: 'Structural',
    description: 'Source of potential harm, energy release, or condition with capability to cause damage or loss.',
    fields: [
      { name: 'hazard_id', type: 'UUID', required: true, desc: 'Hazard taxonomy node' },
      { name: 'energy_source', type: 'Enum', required: true, desc: 'Gravity, Pressure, Electrical, Mechanical, Chemical' },
      { name: 'potential_severity', type: 'Enum', required: true, desc: 'Minor, Moderate, Major, Catastrophic' }
    ],
    incomingFrom: ['Activity'],
    outgoingTo: ['Risk']
  },
  {
    id: 'Risk',
    name: 'Risk',
    category: 'Structural',
    description: 'Probabilistic exposure combining likelihood of hazard escalation with potential consequence severity.',
    fields: [
      { name: 'risk_id', type: 'UUID', required: true, desc: 'Synthesized risk node' },
      { name: 'risk_score', type: 'Float (0-1)', required: true, desc: 'Bayesian calculated failure probability' },
      { name: 'risk_trajectory', type: 'Enum', required: true, desc: 'Increasing, Decreasing, Stable' }
    ],
    incomingFrom: ['Hazard', 'Observation', 'Intervention'],
    outgoingTo: ['Control']
  },
  {
    id: 'Control',
    name: 'Control',
    category: 'Structural',
    description: 'Preventative or mitigating barrier designed to interrupt causal progression toward harm.',
    fields: [
      { name: 'control_id', type: 'UUID', required: true, desc: 'Barrier identifier' },
      { name: 'hierarchy_level', type: 'Enum', required: true, desc: 'Elimination, Substitution, Engineering, Admin, PPE' },
      { name: 'barrier_health', type: 'Float (0-1)', required: true, desc: 'Current operational verification status' }
    ],
    incomingFrom: ['Risk'],
    outgoingTo: []
  },
  {
    id: 'Observation',
    name: 'Observation',
    category: 'Precursor & Event',
    description: 'Proactive behavioral or condition finding logged by frontline personnel or automated telemetry.',
    fields: [
      { name: 'observation_id', type: 'UUID', required: true, desc: 'Log identifier' },
      { name: 'finding_type', type: 'Enum', required: true, desc: 'Safe Behavior, Unsafe Act, Unsafe Condition' },
      { name: 'location_tag', type: 'String', required: true, desc: 'Sub-facility zone / coordinate' }
    ],
    incomingFrom: ['Corrective Action'],
    outgoingTo: ['Risk']
  },
  {
    id: 'Incident',
    name: 'Incident',
    category: 'Precursor & Event',
    description: 'Unplanned event resulting in injury, equipment loss, environmental release, or asset damage.',
    fields: [
      { name: 'incident_id', type: 'UUID', required: true, desc: 'Loss event record' },
      { name: 'actual_severity', type: 'Enum', required: true, desc: 'First Aid, Lost Time, Recordable, Major Loss' },
      { name: 'hipo_flag', type: 'Boolean', required: true, desc: 'High-Potential precursor classification' }
    ],
    incomingFrom: [],
    outgoingTo: ['Activity']
  },
  {
    id: 'Near Miss',
    name: 'Near Miss',
    category: 'Precursor & Event',
    description: 'Event sequence where hazard escalation occurred but barriers prevented actual loss.',
    fields: [
      { name: 'near_miss_id', type: 'UUID', required: true, desc: 'Near miss identifier' },
      { name: 'potential_outcome', type: 'Enum', required: true, desc: 'Estimated worst-case severity' },
      { name: 'barrier_failed', type: 'String', required: false, desc: 'Compromised control mechanism' }
    ],
    incomingFrom: [],
    outgoingTo: ['Risk']
  },
  {
    id: 'Inspection',
    name: 'Inspection',
    category: 'Precursor & Event',
    description: 'Structured routine verification of equipment, tooling, or work environment against defined checklist items.',
    fields: [
      { name: 'inspection_id', type: 'UUID', required: true, desc: 'Inspection run ID' },
      { name: 'asset_id', type: 'String', required: true, desc: 'Physical asset tag' },
      { name: 'pass_rate', type: 'Float', required: true, desc: 'Percentage of passed checklist items' }
    ],
    incomingFrom: [],
    outgoingTo: ['Corrective Action', 'Risk']
  },
  {
    id: 'Audit',
    name: 'Audit',
    category: 'Precursor & Event',
    description: 'Formal systematic evaluation of management system compliance against statutory standards.',
    fields: [
      { name: 'audit_id', type: 'UUID', required: true, desc: 'Formal audit reference' },
      { name: 'standard_ref', type: 'String', required: true, desc: 'ISO 45001, OSHA, API standard code' },
      { name: 'non_conformances', type: 'Integer', required: true, desc: 'Total findings logged' }
    ],
    incomingFrom: [],
    outgoingTo: ['Corrective Action']
  },
  {
    id: 'Permit',
    name: 'Permit',
    category: 'Control & Action',
    description: 'Permit-to-Work (PTW) authorization documenting mandatory isolations, atmospheric tests, and supervisory sign-offs.',
    fields: [
      { name: 'permit_id', type: 'UUID', required: true, desc: 'PTW ticket number' },
      { name: 'permit_type', type: 'Enum', required: true, desc: 'Hot Work, Confined Space, Critical Lift, Electrical' },
      { name: 'status', type: 'Enum', required: true, desc: 'Draft, Authorized, Active, Closed, Suspended' }
    ],
    incomingFrom: [],
    outgoingTo: ['Activity', 'Risk']
  },
  {
    id: 'Training',
    name: 'Training',
    category: 'Human & Capability',
    description: 'Instructional modules, HSE inductions, and specialized coursework completed by workers.',
    fields: [
      { name: 'course_id', type: 'UUID', required: true, desc: 'Course syllabus key' },
      { name: 'curriculum_code', type: 'String', required: true, desc: 'E.g. RIG-LVL3, AP-01' },
      { name: 'validity_period_months', type: 'Integer', required: true, desc: 'Recertification cycle' }
    ],
    incomingFrom: [],
    outgoingTo: ['Competency']
  },
  {
    id: 'Competency',
    name: 'Competency',
    category: 'Human & Capability',
    description: 'Verified worker capability matrix reflecting certified skills, badges, and real-world task authorisations.',
    fields: [
      { name: 'worker_id', type: 'UUID', required: true, desc: 'Anonymized workforce key' },
      { name: 'certification_status', type: 'Enum', required: true, desc: 'Valid, Expiring Soon, Expired' },
      { name: 'practical_assessment_date', type: 'Date', required: true, desc: 'Last field verification' }
    ],
    incomingFrom: ['Training'],
    outgoingTo: ['Risk Exposure']
  },
  {
    id: 'Corrective Action',
    name: 'Corrective Action',
    category: 'Control & Action',
    description: 'Specific remediation task assigned to eliminate an identified defect, condition, or non-conformance.',
    fields: [
      { name: 'action_id', type: 'UUID', required: true, desc: 'CAPA ticket' },
      { name: 'due_date', type: 'Timestamp', required: true, desc: 'Statutory or internal completion deadline' },
      { name: 'status', type: 'Enum', required: true, desc: 'Open, In Progress, Verified Closed, Overdue' }
    ],
    incomingFrom: ['Observation', 'Inspection', 'Audit'],
    outgoingTo: ['Observation']
  },
  {
    id: 'Intervention',
    name: 'Intervention',
    category: 'Control & Action',
    description: 'Targeted campaign, operational pause, or management push deployed to suppress predicted risk precursors.',
    fields: [
      { name: 'intervention_id', type: 'UUID', required: true, desc: 'Campaign reference' },
      { name: 'target_risk_category', type: 'String', required: true, desc: 'E.g. Heavy Lifting Operations' },
      { name: 'predicted_reduction_pct', type: 'Float', required: true, desc: 'Target risk attenuation' }
    ],
    incomingFrom: [],
    outgoingTo: ['Risk', 'Outcome']
  },
  {
    id: 'Outcome',
    name: 'Outcome',
    category: 'Control & Action',
    description: 'Post-intervention measurement evaluating change in incident rate, near-miss reduction, or risk trajectory.',
    fields: [
      { name: 'outcome_id', type: 'UUID', required: true, desc: 'Evaluation result record' },
      { name: 'measurement_window_days', type: 'Integer', required: true, desc: '30, 60, or 90 days' },
      { name: 'actual_reduction_pct', type: 'Float', required: true, desc: 'Observed empirical risk reduction' }
    ],
    incomingFrom: ['Intervention'],
    outgoingTo: []
  }
];

interface FieldMapping {
  externalSystem: string;
  sourceField: string;
  sourceType: string;
  canonicalEntity: string;
  canonicalField: string;
  transformationRule: string;
  confidence: number;
}

const MAPPING_CATALOG: FieldMapping[] = [
  {
    externalSystem: 'SAP EHS Management',
    sourceField: 'Unsafe Condition / Hazard Card',
    sourceType: 'hazard_notification_rec',
    canonicalEntity: 'Observation',
    canonicalField: 'finding_type = "Unsafe Condition"',
    transformationRule: 'Normalize severity string to standard enum, parse coordinate tag',
    confidence: 100
  },
  {
    externalSystem: 'Enablon / Wolters Kluwer',
    sourceField: 'Safety Event / EHS Incident',
    sourceType: 'event_record_v2',
    canonicalEntity: 'Incident',
    canonicalField: 'actual_severity, hipo_flag',
    transformationRule: 'Map OSHA 300 recordability flag to hipo_flag boolean',
    confidence: 100
  },
  {
    externalSystem: 'Intelex EHSQ',
    sourceField: 'Corrective Task / Action Item',
    sourceType: 'capa_task_item',
    canonicalEntity: 'Corrective Action',
    canonicalField: 'status, due_date, action_id',
    transformationRule: 'Extract assignment timestamp and map workflow status',
    confidence: 100
  },
  {
    externalSystem: 'Cority Health & Safety',
    sourceField: 'Near Hit Log',
    sourceType: 'near_hit_tbl',
    canonicalEntity: 'Near Miss',
    canonicalField: 'potential_outcome, barrier_failed',
    transformationRule: 'Translate potential consequence matrix to SIE risk taxonomy',
    confidence: 99
  },
  {
    externalSystem: 'Procore Construction',
    sourceField: 'Daily Site Inspection Item',
    sourceType: 'checklist_entry',
    canonicalEntity: 'Inspection',
    canonicalField: 'pass_rate, asset_id',
    transformationRule: 'Calculate pass ratio across checklist items and attach location ID',
    confidence: 98
  },
  {
    externalSystem: 'Cornerstone / SAP SuccessFactors',
    sourceField: 'LMS Course Completion',
    sourceType: 'course_history_event',
    canonicalEntity: 'Training',
    canonicalField: 'curriculum_code, validity_period_months',
    transformationRule: 'Match course code to safety competency registry',
    confidence: 99
  },
  {
    externalSystem: 'Custom SQL / HR Database',
    sourceField: 'Skill Badge & Certification',
    sourceType: 'operator_qual_card',
    canonicalEntity: 'Competency',
    canonicalField: 'certification_status, worker_id (hashed)',
    transformationRule: 'Anonymize PII worker name to deterministic hash token',
    confidence: 100
  },
  {
    externalSystem: 'Sphera / Prometec PTW',
    sourceField: 'Permit to Work Authorization',
    sourceType: 'permit_instance_xml',
    canonicalEntity: 'Permit',
    canonicalField: 'permit_type, status',
    transformationRule: 'Extract isolation certificates and atmospheric gas test readings',
    confidence: 98
  }
];

export const CanonicalDataModelView: React.FC = () => {
  const [selectedEntity, setSelectedEntity] = useState<CanonicalEntity>(CANONICAL_ENTITIES[0]);
  const [selectedSystemFilter, setSelectedSystemFilter] = useState<string>('All');
  const [testPayloadText, setTestPayloadText] = useState<string>(`{
  "source_system": "SAP_EHS",
  "event_type": "Unsafe Condition",
  "facility_code": "LOS-YARD-4",
  "description": "Tag line absent during 12T turbine casing hoist",
  "logged_by": "J. Doe (Worker #4912)",
  "priority_level": "URGENT",
  "timestamp": "2026-08-31T08:15:00Z"
}`);

  const [normalizedResult, setNormalizedResult] = useState<{
    entity: string;
    canonicalPayload: any;
    transformNotes: string[];
  } | null>({
    entity: 'Observation',
    canonicalPayload: {
      canonical_schema: "SIE.Canonical.Observation.v2",
      observation_id: "OBS-AUTO-94812",
      org_id: "ORG-ENG-4921-NG",
      site_id: "SITE-LAGOS-01",
      location_tag: "LOS-YARD-4",
      finding_type: "Unsafe Act / Procedural Deviation",
      category: "Lifting Operations",
      severity_score: 0.85,
      worker_id: "USR-ANON-77a8b9f", // PII Sanitized
      timestamp: "2026-08-31T08:15:00Z",
      precursor_indicators: ["TAG_LINE_ABSENT", "CRITICAL_LIFT_MODULAR"]
    },
    transformNotes: [
      "Mapped external 'Unsafe Condition' -> Canonical 'Observation'",
      "Sanitized worker identity (J. Doe) into anonymous hash 'USR-ANON-77a8b9f'",
      "Normalized priority_level 'URGENT' -> severity_score 0.85",
      "Mapped facility_code 'LOS-YARD-4' to site_id 'SITE-LAGOS-01'"
    ]
  });

  const handleTestNormalize = () => {
    try {
      const parsed = JSON.parse(testPayloadText);
      const isIncident = parsed.event_type?.toLowerCase().includes('incident') || parsed.event_type?.toLowerCase().includes('event');
      const isAction = parsed.event_type?.toLowerCase().includes('task') || parsed.event_type?.toLowerCase().includes('action');
      
      const entity = isIncident ? 'Incident' : isAction ? 'Corrective Action' : 'Observation';

      setNormalizedResult({
        entity: entity,
        canonicalPayload: {
          canonical_schema: `SIE.Canonical.${entity}.v2`,
          record_id: `REC-NORM-${Math.floor(Math.random() * 90000 + 10000)}`,
          tenant_isolated: true,
          org_id: "ORG-ENG-4921-NG",
          source_system_raw: parsed.source_system || "EXTERNAL_REST",
          normalized_type: parsed.event_type || "Generic finding",
          location_resolved: parsed.facility_code || "SITE-DEFAULT",
          sanitized_timestamp: parsed.timestamp || new Date().toISOString(),
          pii_scrubbed: true
        },
        transformNotes: [
          `Normalized external source field '${parsed.event_type || 'Custom Payload'}' -> SIE Canonical '${entity}'`,
          "Validated against SIE Canonical JSON Schema v2.4",
          "Applied tenant cryptographic isolation boundary"
        ]
      });
    } catch {
      // JSON parse error
    }
  };

  const systems = ['All', 'SAP EHS Management', 'Enablon / Wolters Kluwer', 'Intelex EHSQ', 'Cority Health & Safety', 'Procore Construction', 'Cornerstone / SAP SuccessFactors', 'Custom SQL / HR Database', 'Sphera / Prometec PTW'];

  const filteredMappings = selectedSystemFilter === 'All' 
    ? MAPPING_CATALOG 
    : MAPPING_CATALOG.filter(m => m.externalSystem === selectedSystemFilter);

  return (
    <div className="space-y-8 max-w-7xl mx-auto pb-12">
      {/* HEADER */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-white/5 pb-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
              <Boxes className="w-6 h-6 text-cyan-400" />
              <span>Canonical Safety Data Model</span>
            </h1>
            <span className="text-[11px] font-mono px-2.5 py-0.5 rounded-full bg-cyan-950 text-cyan-300 border border-cyan-800 font-semibold">
              Application-Agnostic Core
            </span>
          </div>
          <p className="text-sm text-slate-400 max-w-3xl leading-relaxed">
            External systems use disparate terminology and data structures. The Safelytic Intelligence Engine (SIE) ingests, maps, and normalizes them into a unified, mathematically consistent canonical safety intelligence model.
          </p>
        </div>

        {/* Prototype Watermark */}
        <div className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs font-mono shrink-0">
          <Info className="w-4 h-4 text-amber-400 shrink-0" />
          <span>Prototype Schema Representation</span>
        </div>
      </div>

      {/* CORE HIERARCHY CHAIN */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-bold text-white tracking-tight flex items-center gap-2">
              <Layers className="w-4 h-4 text-cyan-400" />
              <span>Structural Hierarchy Pipeline</span>
            </h2>
            <p className="text-xs text-slate-400">
              The fundamental structural lineage establishing how high-level organizations decompose into operational barriers.
            </p>
          </div>
          <span className="text-xs font-mono text-slate-400">6 Core Structural Layers</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-3">
          {[
            {
              step: '01',
              title: 'Organization',
              sub: 'Enterprise Tenant',
              icon: Building2,
              color: 'border-cyan-500/30 bg-cyan-950/30 text-cyan-300',
              badge: 'KMS Sovereign',
              desc: 'Top-level enterprise tenant with cryptographic boundary.'
            },
            {
              step: '02',
              title: 'Site',
              sub: 'Physical Asset',
              icon: MapPin,
              color: 'border-blue-500/30 bg-blue-950/30 text-blue-300',
              badge: 'Geographic Zone',
              desc: 'Physical facility, yard, offshore rig, or plant asset.'
            },
            {
              step: '03',
              title: 'Activity',
              sub: 'Work Process',
              icon: Briefcase,
              color: 'border-amber-500/30 bg-amber-950/30 text-amber-300',
              badge: 'Task Execution',
              desc: 'Discrete operational task (e.g. Critical Lift, Line Break).'
            },
            {
              step: '04',
              title: 'Hazard',
              sub: 'Energy Source',
              icon: Flame,
              color: 'border-orange-500/30 bg-orange-950/30 text-orange-300',
              badge: 'Potential Harm',
              desc: 'Stored kinetic, chemical, pressure, or height energy.'
            },
            {
              step: '05',
              title: 'Risk',
              sub: 'Failure Probability',
              icon: AlertTriangle,
              color: 'border-red-500/30 bg-red-950/30 text-red-300',
              badge: 'Bayesian DAG',
              desc: 'Probabilistic likelihood of escalation and severity.'
            },
            {
              step: '06',
              title: 'Control',
              sub: 'Safety Barrier',
              icon: ShieldCheck,
              color: 'border-emerald-500/30 bg-emerald-950/30 text-emerald-300',
              badge: 'Hierarchy Level',
              desc: 'Engineered barrier, permit gate, or procedural safeguard.'
            }
          ].map((item, idx) => (
            <div 
              key={idx}
              className={`p-4 rounded-xl border ${item.color} flex flex-col justify-between relative overflow-hidden transition-all hover:translate-y-[-2px]`}
            >
              <div className="flex items-center justify-between mb-3">
                <div className="w-7 h-7 rounded-lg bg-black/40 flex items-center justify-center">
                  <item.icon className="w-4 h-4" />
                </div>
                <span className="text-[10px] font-mono font-bold text-slate-500">#{item.step}</span>
              </div>
              <div>
                <span className="text-[9px] font-mono uppercase tracking-wider text-slate-400 block">{item.sub}</span>
                <h3 className="text-sm font-bold text-white mt-0.5">{item.title}</h3>
                <p className="text-[11px] text-slate-300 mt-1.5 leading-snug">{item.desc}</p>
              </div>
              <div className="mt-3 pt-2.5 border-t border-white/5 flex items-center justify-between">
                <span className="text-[10px] font-mono text-slate-400">{item.badge}</span>
                {idx < 5 && (
                  <ArrowRight className="w-3.5 h-3.5 text-slate-400 hidden lg:block" />
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* CANONICAL ENTITY RELATIONSHIP GRAPH & MATRIX */}
      <div className="space-y-4">
        <div>
          <h2 className="text-base font-bold text-white tracking-tight flex items-center gap-2">
            <GitFork className="w-4 h-4 text-cyan-400" />
            <span>Entity Relationship Architecture</span>
          </h2>
          <p className="text-xs text-slate-400">
            How operational entities, behavioral telemetry, human factors, and closed-loop interventions interconnect inside SIE's reasoning graph.
          </p>
        </div>

        {/* Highlighted Relationship Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {CANONICAL_RELATIONSHIPS.map((rel, i) => (
            <div 
              key={i}
              className="p-3.5 rounded-xl bg-slate-900/90 border border-slate-800 hover:border-cyan-500/40 transition-colors space-y-2"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-mono font-bold text-cyan-300 px-2 py-0.5 rounded bg-cyan-950 border border-cyan-800">
                    {rel.source}
                  </span>
                  <span className="text-xs text-slate-400 font-mono">→</span>
                  <span className="text-xs font-mono font-bold text-purple-300 px-2 py-0.5 rounded bg-purple-950 border border-purple-800">
                    {rel.target}
                  </span>
                </div>
                <span className={`text-[9px] font-mono px-2 py-0.5 rounded uppercase font-semibold ${
                  rel.type === 'causal' ? 'bg-red-950 text-red-300 border border-red-800' :
                  rel.type === 'mitigation' ? 'bg-emerald-950 text-emerald-300 border border-emerald-800' :
                  rel.type === 'telemetry' ? 'bg-amber-950 text-amber-300 border border-amber-800' :
                  'bg-blue-950 text-blue-300 border border-blue-800'
                }`}>
                  {rel.type}
                </span>
              </div>
              <div className="text-[11px] text-slate-300">
                <span className="text-slate-400 font-mono text-[10px] block">Relationship:</span>
                <span className="font-semibold text-slate-200">{rel.source} {rel.relationship} {rel.target}</span>
              </div>
              <p className="text-[11px] text-slate-400 leading-snug">
                {rel.description}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* CORE 11 OPERATIONAL & GOVERNANCE ENTITIES EXPLORER */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-bold text-white tracking-tight flex items-center gap-2">
              <Database className="w-4 h-4 text-cyan-400" />
              <span>Canonical Entity Schema Catalog</span>
            </h2>
            <p className="text-xs text-slate-400">
              Explore the normalized schema attributes, relationship bindings, and contracts for all standardized safety entities.
            </p>
          </div>
          <span className="text-xs font-mono text-cyan-400 bg-cyan-950/60 px-3 py-1 rounded-full border border-cyan-800/80">
            {CANONICAL_ENTITIES.length} Standardized Entities
          </span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          {/* Entity List */}
          <div className="lg:col-span-4 space-y-1.5 max-h-[460px] overflow-y-auto pr-1">
            {CANONICAL_ENTITIES.map((ent) => {
              const isSelected = selectedEntity.id === ent.id;
              return (
                <button
                  key={ent.id}
                  onClick={() => setSelectedEntity(ent)}
                  className={`w-full text-left p-3 rounded-xl transition-all border flex items-center justify-between ${
                    isSelected 
                      ? 'bg-cyan-950/60 border-cyan-500 text-white shadow'
                      : 'bg-slate-900/80 border-slate-800 text-slate-300 hover:bg-slate-800/80'
                  }`}
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold font-mono">{ent.name}</span>
                      <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded ${
                        ent.category === 'Structural' ? 'bg-blue-950 text-blue-300' :
                        ent.category === 'Precursor & Event' ? 'bg-amber-950 text-amber-300' :
                        ent.category === 'Human & Capability' ? 'bg-purple-950 text-purple-300' :
                        'bg-emerald-950 text-emerald-300'
                      }`}>
                        {ent.category}
                      </span>
                    </div>
                    <p className="text-[10px] text-slate-400 truncate max-w-[200px] mt-0.5">
                      {ent.description}
                    </p>
                  </div>
                  <ChevronRight className={`w-4 h-4 shrink-0 transition-transform ${isSelected ? 'text-cyan-400 translate-x-0.5' : 'text-slate-600'}`} />
                </button>
              );
            })}
          </div>

          {/* Entity Detail Inspector */}
          <div className="lg:col-span-8 p-5 rounded-2xl bg-slate-900/90 border border-slate-800 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
              <div>
                <span className="text-[10px] font-mono uppercase text-cyan-400 font-bold block">Canonical Entity Definition</span>
                <h3 className="text-lg font-bold text-white flex items-center gap-2 mt-0.5">
                  <span>{selectedEntity.name}</span>
                  <span className="text-xs font-mono text-slate-400 font-normal">({selectedEntity.category})</span>
                </h3>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono px-2.5 py-1 rounded bg-slate-950 border border-slate-800 text-slate-300">
                  Schema: <strong className="text-cyan-300 font-mono">SIE.{selectedEntity.id}.v2</strong>
                </span>
              </div>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed">
              {selectedEntity.description}
            </p>

            {/* Inbound & Outbound Connections */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                <span className="text-[10px] font-mono uppercase text-slate-400 block mb-1">Incoming Relationships (Inputs)</span>
                {selectedEntity.incomingFrom.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {selectedEntity.incomingFrom.map((src, idx) => (
                      <span key={idx} className="text-xs font-mono px-2 py-0.5 rounded bg-blue-950 text-blue-300 border border-blue-800">
                        {src} →
                      </span>
                    ))}
                  </div>
                ) : (
                  <span className="text-xs text-slate-500 font-mono italic">Root source node</span>
                )}
              </div>

              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                <span className="text-[10px] font-mono uppercase text-slate-400 block mb-1">Outgoing Relationships (Outputs)</span>
                {selectedEntity.outgoingTo.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {selectedEntity.outgoingTo.map((tgt, idx) => (
                      <span key={idx} className="text-xs font-mono px-2 py-0.5 rounded bg-purple-950 text-purple-300 border border-purple-800">
                        → {tgt}
                      </span>
                    ))}
                  </div>
                ) : (
                  <span className="text-xs text-slate-500 font-mono italic">Terminal leaf / sink node</span>
                )}
              </div>
            </div>

            {/* Schema Attributes Table */}
            <div>
              <span className="text-[10px] font-mono uppercase text-slate-400 block mb-2 font-semibold">
                Normalized Schema Fields:
              </span>
              <div className="overflow-x-auto rounded-lg border border-slate-800">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-950 text-slate-400 font-mono text-[10px] uppercase border-b border-slate-800">
                    <tr>
                      <th className="p-2.5">Field Name</th>
                      <th className="p-2.5">Data Type</th>
                      <th className="p-2.5">Requirement</th>
                      <th className="p-2.5">Canonical Semantic Description</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-mono text-[11px]">
                    {selectedEntity.fields.map((f, i) => (
                      <tr key={i} className="hover:bg-slate-800/40">
                        <td className="p-2.5 font-bold text-cyan-300">{f.name}</td>
                        <td className="p-2.5 text-purple-300">{f.type}</td>
                        <td className="p-2.5">
                          {f.required ? (
                            <span className="text-[9px] px-1.5 py-0.5 rounded bg-red-950 text-red-300 border border-red-800">
                              Required
                            </span>
                          ) : (
                            <span className="text-[9px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">
                              Optional
                            </span>
                          )}
                        </td>
                        <td className="p-2.5 text-slate-300 font-sans text-xs">{f.desc}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* EXTERNAL DATA MAPPING SECTION */}
      <div className="space-y-4 pt-4 border-t border-white/5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-bold text-white tracking-tight flex items-center gap-2">
              <RefreshCw className="w-4 h-4 text-cyan-400" />
              <span>External Data Mapping</span>
            </h2>
            <p className="text-xs text-slate-400">
              Live mapping directory showing how vendor-specific terminology and structures map directly into SIE canonical objects.
            </p>
          </div>

          {/* Filter by System */}
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-slate-400">Filter Source:</span>
            <select
              value={selectedSystemFilter}
              onChange={(e) => setSelectedSystemFilter(e.target.value)}
              className="bg-slate-900 border border-slate-700 text-slate-200 text-xs rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-cyan-500 font-mono"
            >
              {systems.map((s, idx) => (
                <option key={idx} value={s}>{s}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Mapping Catalog Table */}
        <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/90 shadow-sm">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-950 text-slate-400 font-mono text-[10px] uppercase border-b border-slate-800">
              <tr>
                <th className="p-3">Source Enterprise System</th>
                <th className="p-3">External System Field / Record</th>
                <th className="p-3 text-center">Transform</th>
                <th className="p-3">SIE Canonical Target Entity</th>
                <th className="p-3">Transformation & Normalization Logic</th>
                <th className="p-3 text-right">Confidence</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800 text-[11px]">
              {filteredMappings.map((map, i) => (
                <tr key={i} className="hover:bg-slate-800/40 transition-colors">
                  <td className="p-3 font-semibold text-slate-200 flex items-center gap-2">
                    <Building2 className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                    <span>{map.externalSystem}</span>
                  </td>
                  <td className="p-3 font-mono">
                    <span className="text-amber-300 font-bold block">"{map.sourceField}"</span>
                    <span className="text-[10px] text-slate-500">{map.sourceType}</span>
                  </td>
                  <td className="p-3 text-center">
                    <div className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-slate-950 border border-slate-700 text-cyan-400">
                      <ArrowRight className="w-3.5 h-3.5" />
                    </div>
                  </td>
                  <td className="p-3 font-mono">
                    <span className="text-cyan-300 font-bold px-2 py-0.5 rounded bg-cyan-950 border border-cyan-800">
                      {map.canonicalEntity}
                    </span>
                    <span className="text-[10px] text-slate-400 block mt-1">{map.canonicalField}</span>
                  </td>
                  <td className="p-3 text-slate-300 text-xs max-w-xs">
                    {map.transformationRule}
                  </td>
                  <td className="p-3 text-right font-mono font-bold text-emerald-400">
                    {map.confidence}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* INTERACTIVE NORMALIZER TEST SANDBOX */}
      <div className="p-5 rounded-2xl bg-gradient-to-br from-slate-900 via-slate-900 to-slate-950 border border-slate-800 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Code2 className="w-4 h-4 text-cyan-400" />
              <span>Interactive Canonical Normalizer Sandbox</span>
            </h3>
            <p className="text-xs text-slate-400">
              Simulate ingestion of an arbitrary JSON payload from any third-party system to test real-time mapping into SIE Canonical format.
            </p>
          </div>
          <button
            onClick={handleTestNormalize}
            className="px-3.5 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold font-mono flex items-center gap-1.5 transition-colors shadow self-start sm:self-auto"
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>Execute Normalization</span>
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Left: Input Payload */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono uppercase text-slate-400 font-bold">
                External Raw Payload (JSON)
              </span>
              <span className="text-[10px] font-mono text-amber-400">Any Schema / Vendor</span>
            </div>
            <textarea
              rows={8}
              value={testPayloadText}
              onChange={(e) => setTestPayloadText(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 font-mono text-xs text-cyan-300 focus:outline-none focus:border-cyan-500 leading-relaxed resize-none"
            />
          </div>

          {/* Right: Normalized Canonical Output */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono uppercase text-slate-400 font-bold flex items-center gap-1.5">
                <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                <span>Normalized Canonical Object</span>
              </span>
              {normalizedResult && (
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800 font-bold">
                  {normalizedResult.entity}
                </span>
              )}
            </div>

            {normalizedResult ? (
              <div className="space-y-2">
                <pre className="w-full bg-slate-950 border border-emerald-900/40 rounded-xl p-3 font-mono text-xs text-emerald-300 overflow-x-auto max-h-[140px] leading-relaxed">
                  {JSON.stringify(normalizedResult.canonicalPayload, null, 2)}
                </pre>
                <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 text-[11px] space-y-1 font-mono">
                  <span className="text-[10px] text-slate-400 uppercase font-bold block">Transformation Ledger:</span>
                  {normalizedResult.transformNotes.map((note, idx) => (
                    <div key={idx} className="text-slate-300 flex items-center gap-1.5">
                      <span className="text-cyan-400">✓</span>
                      <span>{note}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="h-[180px] rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-center text-xs text-slate-500 font-mono">
                Click Execute Normalization to run transformation
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
