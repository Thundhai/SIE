import { EmergingRisk, PredictionMethodology, LineageStageId, EvidenceStrengthLevel } from '../types';

export const DEFAULT_METHODOLOGY: PredictionMethodology = {
  predictionType: 'Emerging Risk Forecast',
  forecastPeriod: 'Next 30 Days',
  dataWindow: 'Previous 90 Days',
  modelMethod: 'Multi-Model Ensemble (Bayesian Network + NLP Semantic Co-occurrence + Cox Proportional Hazards)',
  orgRecordsAnalyzed: 1284,
  externalKnowledgeSources: 14,
  contributingFactorsCount: 4,
  analyticalModelsCount: 3,
  modelVersion: 'SIE Risk Engine v0.1',
  generatedDate: '2026-08-28 08:30 UTC',
  dataQualityScore: 94,
  evidenceStrength: 'Very Strong',
  historicalCoverage: 87
};

export const RISK_METHODOLOGIES: Record<string, Partial<PredictionMethodology>> = {
  'RISK-LIFT-01': {
    predictionType: 'Emerging Risk Forecast',
    forecastPeriod: 'Next 30 Days',
    dataWindow: 'Previous 90 Days',
    modelMethod: 'Bayesian Causal Network + Tag Line Velocity Tracker',
    orgRecordsAnalyzed: 1284,
    externalKnowledgeSources: 14,
    contributingFactorsCount: 4,
    analyticalModelsCount: 3,
    modelVersion: 'SIE Risk Engine v0.1',
    generatedDate: '2026-08-28 08:30 UTC',
    dataQualityScore: 94,
    evidenceStrength: 'Very Strong',
    historicalCoverage: 87
  },
  'RISK-PROC-02': {
    predictionType: 'Process Safety Hazard Precursor',
    forecastPeriod: 'Next 45 Days',
    dataWindow: 'Previous 120 Days',
    modelMethod: 'Fault Tree Synthesis + Flange Degradation Classifier',
    orgRecordsAnalyzed: 1840,
    externalKnowledgeSources: 18,
    contributingFactorsCount: 5,
    analyticalModelsCount: 3,
    modelVersion: 'SIE Risk Engine v0.1',
    generatedDate: '2026-08-27 14:15 UTC',
    dataQualityScore: 96,
    evidenceStrength: 'Very Strong',
    historicalCoverage: 91
  },
  'RISK-CONT-03': {
    predictionType: 'Subcontractor Safety Variance Forecast',
    forecastPeriod: 'Next 30 Days',
    dataWindow: 'Previous 60 Days',
    modelMethod: 'Time-to-Event Survival Analysis + Onboarding Turnover Index',
    orgRecordsAnalyzed: 942,
    externalKnowledgeSources: 11,
    contributingFactorsCount: 4,
    analyticalModelsCount: 3,
    modelVersion: 'SIE Risk Engine v0.1',
    generatedDate: '2026-08-28 06:45 UTC',
    dataQualityScore: 91,
    evidenceStrength: 'Strong',
    historicalCoverage: 84
  },
  'RISK-VEH-04': {
    predictionType: 'Traffic Interaction & Blind-Spot Forecast',
    forecastPeriod: 'Next 30 Days',
    dataWindow: 'Previous 90 Days',
    modelMethod: 'Spatial Congestion Heatmap + Near Miss Markov Process',
    orgRecordsAnalyzed: 1120,
    externalKnowledgeSources: 12,
    contributingFactorsCount: 4,
    analyticalModelsCount: 3,
    modelVersion: 'SIE Risk Engine v0.1',
    generatedDate: '2026-08-26 11:20 UTC',
    dataQualityScore: 93,
    evidenceStrength: 'Strong',
    historicalCoverage: 89
  },
  'RISK-HEI-05': {
    predictionType: 'Scaffold & Fall Protection Degradation Forecast',
    forecastPeriod: 'Next 30 Days',
    dataWindow: 'Previous 90 Days',
    modelMethod: 'Bayesian Inspection Defect Clustering + Environmental Wind Factor',
    orgRecordsAnalyzed: 860,
    externalKnowledgeSources: 15,
    contributingFactorsCount: 4,
    analyticalModelsCount: 3,
    modelVersion: 'SIE Risk Engine v0.1',
    generatedDate: '2026-08-27 17:00 UTC',
    dataQualityScore: 92,
    evidenceStrength: 'Moderate',
    historicalCoverage: 86
  },
  'RISK-CONF-06': {
    predictionType: 'Atmospheric Gas & Ventilation Hazard Forecast',
    forecastPeriod: 'Next 60 Days',
    dataWindow: 'Previous 90 Days',
    modelMethod: 'Sensor Baseline Drift Model + Permit Deviation Cross-Referencing',
    orgRecordsAnalyzed: 740,
    externalKnowledgeSources: 16,
    contributingFactorsCount: 4,
    analyticalModelsCount: 3,
    modelVersion: 'SIE Risk Engine v0.1',
    generatedDate: '2026-08-28 09:10 UTC',
    dataQualityScore: 95,
    evidenceStrength: 'Very Strong',
    historicalCoverage: 88
  }
};

export function getRiskMethodology(risk: EmergingRisk): PredictionMethodology {
  const custom = RISK_METHODOLOGIES[risk.id] || {};
  return {
    ...DEFAULT_METHODOLOGY,
    contributingFactorsCount: risk.contributingFactors?.length || 4,
    orgRecordsAnalyzed: (risk.orgRecordsCount ? risk.orgRecordsCount * 52 : 1284),
    externalKnowledgeSources: risk.externalSourcesCount || 14,
    analyticalModelsCount: risk.modelsUsedCount || 3,
    forecastPeriod: risk.forecastPeriod || 'Next 30 Days',
    evidenceStrength: risk.evidenceStrength || 'Strong',
    ...custom,
    ...(risk.methodology || {})
  };
}

export interface LineageStageDetail {
  id: LineageStageId;
  stepNumber: number;
  label: string;
  shortDescription: string;
  icon: string;
  category: string;
  methodologyDetails: {
    title: string;
    description: string;
    keyInputs: string[];
    assumptions: string[];
    mathematicalMethod: string;
    limitations: string[];
  };
}

export const LINEAGE_STAGES: LineageStageDetail[] = [
  {
    id: 'prediction',
    stepNumber: 1,
    label: 'Prediction',
    shortDescription: 'Bayesian estimated likelihood of modeled hazard condition',
    icon: 'BrainCircuit',
    category: 'Analytical Output',
    methodologyDetails: {
      title: 'Bayesian Posterior Probability Calculation',
      description: 'Calculates the probabilistic likelihood that leading indicators and precursor clusters will manifest into an incident within the 30-day lookahead window.',
      keyInputs: [
        'Historical event baselines over 90-day data window',
        'Current precursor escalation rate (+14% trend)',
        'Active operational exposure tempo and SIMOPS index'
      ],
      assumptions: [
        'Operational conditions continue on current baseline trajectory',
        'Reporting rate of unsafe acts represents field reality without systematic suppression',
        'Precursor frequency correlates exponentially with high-potential event risk'
      ],
      mathematicalMethod: 'P(Incident | Precursors) = [P(Precursors | Incident) * P(Incident)] / P(Precursors)',
      limitations: [
        'Does NOT predict exact timestamp or deterministic incident occurrence',
        'Subject to reporting latency if field teams delay submitting observation cards'
      ]
    }
  },
  {
    id: 'risk-factors',
    stepNumber: 2,
    label: 'Analytical Factors',
    shortDescription: 'Ranked contributing precursors, baseline deviations and variance',
    icon: 'Sliders',
    category: 'Factor Attribution',
    methodologyDetails: {
      title: 'Analytical Evidence & Precursor Attribution',
      description: 'Isolates and weights individual contributing drivers, measuring current deviation against historical operational baselines.',
      keyInputs: [
        'Rigging gear inspection lag (34% variance, +128% vs 90d baseline)',
        'Contractor turnover and onboarding tenure (28% variance)',
        'Spatial SIMOPS and congestion density (22% variance)',
        'Environmental meteorological factors (16% variance)'
      ],
      assumptions: [
        'Factors have orthogonal additive effects on total hazard score',
        'Variance weights sum to 100% normalized baseline'
      ],
      mathematicalMethod: 'Shapley Value Attribution & Principal Component Weighting (PCA)',
      limitations: [
        'Second-order interaction effects between three or more concurrent variables may introduce residual non-linearities'
      ]
    }
  },
  {
    id: 'org-evidence',
    stepNumber: 3,
    label: 'Organization Records',
    shortDescription: 'Ingested internal observations, near misses, permits & audit records',
    icon: 'FileText',
    category: 'Empirical Data',
    methodologyDetails: {
      title: 'Organization Evidence Grounding (DEMO / SIMULATED)',
      description: 'Correlates raw field incident reports, near miss forms, permit exceptions, and corrective action registers across the tenant workspace.',
      keyInputs: [
        '1,284 total organization records parsed across 90-day window',
        '24 direct high-severity lifting records matched in Yard 4 & Pier 2',
        '3 overdue CAPA items on rigging equipment recertification'
      ],
      assumptions: [
        'Field classifications are verified by site HSE superintendents',
        'Tenant data isolation is cryptographically enforced'
      ],
      mathematicalMethod: 'NLP Entity Extraction & Causal Co-occurrence Semantic Graph',
      limitations: [
        'Unreported near misses cannot be captured in the empirical stream'
      ]
    }
  },
  {
    id: 'external-evidence',
    stepNumber: 4,
    label: 'External Knowledge',
    shortDescription: 'Verified regulatory standards, OSHA, HSE UK & API benchmarks',
    icon: 'Sparkles',
    category: 'Domain Knowledge',
    methodologyDetails: {
      title: 'Statutory Standards & Research Benchmarks (DEMO / SIMULATED)',
      description: 'Validates internal precursor patterns against authoritative international safety standards, engineering guidelines, and peer-reviewed safety science.',
      keyInputs: [
        '14 verified external knowledge publications considered',
        'OSHA 1926.1400 (Cranes and Derricks in Construction)',
        'HSE UK Guidance L113 (Safe Use of Lifting Equipment)',
        'API RP 54 (Safety in Oil & Gas Rigging Operations)'
      ],
      assumptions: [
        'Statutory standards define verified threshold limits for engineering safety barriers',
        'Jurisdictional relevance is mapped accurately to site operating conditions'
      ],
      mathematicalMethod: 'Semantic Vector Similarity & Rule-Constraint Verification Engine',
      limitations: [
        'External standards provide normative guidance but cannot replace site-specific risk assessments'
      ]
    }
  },
  {
    id: 'analytical-method',
    stepNumber: 5,
    label: 'Model / Method',
    shortDescription: 'Multi-model ensemble algorithms & confidence calculation',
    icon: 'Activity',
    category: 'Model Architecture',
    methodologyDetails: {
      title: 'Ensemble Modeling & Confidence Scored Architecture',
      description: 'Combines 3 distinct analytical models to prevent single-algorithm hallucination or overfitting.',
      keyInputs: [
        'Model 1: Dynamic Bayesian Network (prior + likelihood updating)',
        'Model 2: NLP Semantic Co-occurrence Graph (latent thematic risk clusters)',
        'Model 3: Cox Proportional Hazards Survival Analysis (time-to-event estimation)'
      ],
      assumptions: [
        'Ensemble consensus reduces epistemic uncertainty and model bias',
        'Confidence score is derived from data completeness, sample size, and cross-model agreement'
      ],
      mathematicalMethod: 'Confidence = W_data(Data Quality) + W_model(Inter-model Agreement) + W_hist(Historical Coverage)',
      limitations: [
        'Model accuracy requires minimum sample threshold (>50 observations per operational quarter)'
      ]
    }
  },
  {
    id: 'recommendation',
    stepNumber: 6,
    label: 'Recommendation',
    shortDescription: 'Targeted HSE barriers, CAPA actions & field verification protocols',
    icon: 'ShieldAlert',
    category: 'Operational Action',
    methodologyDetails: {
      title: 'Targeted Barrier Reinforcement & Intervention Synthesis',
      description: 'Synthesizes verified preventive controls and field verifications tailored to disrupt the identified causal chain.',
      keyInputs: [
        'Precursor hierarchy of controls (engineering > administrative > PPE)',
        'Identified root causes (rigging recertification, tag line compliance, rigger competency)',
        'Designated site role assignments and operational lead times'
      ],
      assumptions: [
        'Executing recommended actions restores safety barriers to nominal integrity',
        'Post-intervention leading indicators will demonstrate downward trend'
      ],
      mathematicalMethod: 'Bowtie Analysis & Safety Barrier Integrity Index',
      limitations: [
        'Interventions require field validation by competent HSE professionals'
      ]
    }
  }
];
