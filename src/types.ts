export type RiskLevel = 'Low' | 'Moderate' | 'High' | 'Critical';
export type TrendDirection = 'Increasing' | 'Decreasing' | 'Stable';
export type VerificationStatus = 'Verified' | 'Pending Review' | 'Flagged' | 'Rejected';
export type InterventionStatus = 'Recommended' | 'Active' | 'Under Review' | 'Completed' | 'Dismissed';

export type DateRangePreset = '7d' | '30d' | '90d' | '180d' | 'ytd' | 'custom';

export type DataSourceFilter = 
  | 'Observation'
  | 'Near Miss'
  | 'Incident'
  | 'Audit Finding'
  | 'Permit Exception'
  | 'External Standard'
  | 'IoT Telemetry';

export interface GlobalFilterState {
  dateRangePreset: DateRangePreset;
  customStartDate?: string;
  customEndDate?: string;
  riskLevels: RiskLevel[];
  dataSources: DataSourceFilter[];
  searchQuery: string;
  selectedCategory?: string | null;
}

export type AppScreen = 
  | 'overview'
  | 'intelligence'
  | 'prediction-detail'
  | 'knowledge-center'
  | 'source-verification'
  | 'organization-data'
  | 'intelligence-learning'
  | 'interventions'
  | 'outcome-learning'
  | 'assistant'
  | 'api-integrations'
  | 'canonical-model'
  | 'governance'
  | 'settings';

export interface CategoryThresholdOverride {
  category: string;
  enabled: boolean;
  minProbability: number;
  minConfidence: number;
  autoInterventionTrigger: boolean;
  priorityRouting: 'Critical SMS & App' | 'Urgent In-App' | 'Daily Digest';
}

export interface AlertThresholdConfig {
  globalMinProbability: number;
  globalMinConfidence: number;
  alertOnSurgeDelta: boolean;
  surgeDeltaThreshold: number;
  notifyOnOverdueActions: boolean;
  sensitivityPreset: 'strict' | 'balanced' | 'conservative' | 'custom';
  channels: {
    inAppAlerts: boolean;
    urgentBadge: boolean;
    smsUrgent: boolean;
    emailDigest: boolean;
    webhookDispatch: boolean;
  };
  categoryOverrides: CategoryThresholdOverride[];
  userPreferences: {
    recipientName: string;
    recipientRole: string;
    email: string;
    phone: string;
    designatedSites: string[];
    quietHoursEnabled: boolean;
    quietHoursStart: string;
    quietHoursEnd: string;
  };
}

export interface EvidenceModalData {
  id: string;
  title: string;
  type: string;
  severity: string;
  date: string;
  details: string;
  source: string;
  metrics?: string;
  ruleCode?: string;
  citationLink?: string;
}

export interface NotificationItem {
  id: string;
  title: string;
  category: 'Risk Alert' | 'Intervention' | 'Knowledge Update' | 'Data Stream';
  message: string;
  timestamp: string;
  severity: 'Critical' | 'High' | 'Moderate' | 'Info';
  isRead: boolean;
  relatedRiskId?: string;
}

export interface AssistantChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  timestamp: string;
  intelligenceContext?: {
    orgRecords: number;
    externalKnowledgeSources: number;
    historicalAnalysisDays: number;
    predictiveModelsCount: number;
  };
  evidenceUsed?: {
    organizationEvidence: string[];
    externalKnowledge: string[];
    analyticalResults: string[];
  };
  relatedRiskId?: string;
  citations?: {
    id: string;
    title: string;
    type: string;
    severity: string;
    date: string;
    details: string;
  }[];
}

export interface ApiEndpoint {
  path: string;
  method: 'GET' | 'POST';
  description: string;
  sampleRequest: string;
  sampleResponse: string;
}

export type EvidenceStrengthLevel = 'Very Strong' | 'Strong' | 'Moderate' | 'Weak' | 'Insufficient';

export interface OrganizationEvidenceItem {
  id: string; // e.g. OBS-1044
  type: 'Observation' | 'Near Miss' | 'Incident' | 'Audit Finding' | 'Permit Exception' | 'Inspection Defect';
  title: string;
  date: string; // e.g. 18 Aug 2026
  site: string; // e.g. Lagos Operations
  location?: string; // e.g. Yard 4 Staging Pad
  activity: string; // e.g. Lifting operation
  hazard: string; // e.g. Unsafe sling angle exceeding 60-degree safe envelope
  risk: string; // e.g. Dropped load / Rigging parting failure
  severity: 'Low' | 'Medium' | 'High' | 'Critical';
  status: 'Open' | 'Overdue' | 'Closed' | 'In Remediation';
  sourceSystem: string; // e.g. Intelex HSE Cloud, Cority Mobile, Enablon PTW
  details: string;
  reporterRole?: string;
  isSimulated?: boolean;
}

export interface ExternalEvidenceItem {
  id: string;
  publisher: string; // e.g. HSE UK (Health and Safety Executive)
  documentTitle: string; // e.g. LOLER 1998 Approved Code of Practice & Rigging Failure Causation Analysis
  documentType: 'Regulatory Standard' | 'Technical Guidance' | 'Safety Alert' | 'Research Benchmark' | 'Approved Code of Practice' | 'International Standard';
  code: string; // e.g. HSE L113 / 2026 Rev
  jurisdiction: string; // e.g. United Kingdom / Global Best Practice
  publicationDate: string; // e.g. 2026
  revisionVersion: string; // e.g. Rev 4.2 (2026 Amendment)
  verificationStatus: 'Verified' | 'Active Standard' | 'Validated Benchmark';
  reliability: 'Very High' | 'High' | 'Moderate' | 'Unverified';
  topic: string; // e.g. Lifting Equipment Inspection & Pre-use Controls
  sourceReference: string; // e.g. HSE L113 § 14.2 / Table 3.1: Sling Angles and Capacity Derating
  keyExcerpt: string;
  isSimulated?: boolean;
}

export interface AnalyticalEvidenceItem {
  id: string;
  trend: string; // e.g. +14% 30-Day Escalation Slope
  baseline: string; // e.g. 2.1 precursors / 10,000 crane lift cycles
  currentValue: string; // e.g. 4.8 precursors / 10,000 crane lift cycles
  deviation: string; // e.g. +128% vs Historical 90-Day Moving Average (z-score +2.4)
  historicalComparison: string; // e.g. Highest precursor concentration since Q3 2024 turnaround
  contributingFactors: {
    name: string;
    percentage: number;
    impact: 'High' | 'Medium' | 'Low';
    description: string;
  }[];
  modelTechnique?: string;
  confidenceInterval?: string;
  isSimulated?: boolean;
}

export interface PredictionMethodology {
  predictionType: string;
  forecastPeriod: string;
  dataWindow: string;
  modelMethod: string;
  orgRecordsAnalyzed: number;
  externalKnowledgeSources: number;
  contributingFactorsCount: number;
  analyticalModelsCount: number;
  modelVersion: string;
  generatedDate: string;
  dataQualityScore: number; // e.g. 94 (%)
  evidenceStrength: EvidenceStrengthLevel;
  historicalCoverage: number; // e.g. 87 (%)
}

export type LineageStageId = 
  | 'prediction' 
  | 'risk-factors' 
  | 'org-evidence' 
  | 'external-evidence' 
  | 'analytical-method' 
  | 'recommendation';

export interface EmergingRisk {
  id: string;
  category: string;
  title: string;
  level: RiskLevel;
  probability: number; // percentage e.g. 78
  confidence: number; // percentage e.g. 82
  trajectory: TrendDirection;
  trendPercentage: number; // e.g. +14
  location: string;
  site: string;
  identifiedDate: string;
  mainDriver: string;
  drivers: string[];
  status: 'Elevated' | 'Emerging' | 'Critical Warning' | 'Monitored';
  forecastPeriod?: string;
  evidenceStrength: EvidenceStrengthLevel;
  orgRecordsCount: number;
  externalSourcesCount: number;
  modelsUsedCount: number;
  summary: string;
  methodology?: PredictionMethodology;
  causalChain: {
    step: number;
    title: string;
    description: string;
    metricChange?: string;
  }[];
  contributingFactors: {
    name: string;
    percentage: number;
    impact: 'High' | 'Medium' | 'Low';
    description: string;
  }[];
  organizationEvidence: OrganizationEvidenceItem[];
  externalEvidence: ExternalEvidenceItem[];
  analyticalEvidence?: AnalyticalEvidenceItem;
  aiReasoning: string;
}

export type KnowledgeFreshness = 'Current' | 'Recently Updated' | 'Review Required' | 'Expired/Obsolete';

export interface KnowledgeDocument {
  id: string;
  source: string;
  title: string;
  documentCode: string;
  type: 'Regulatory Standard' | 'Technical Guidance' | 'Safety Alert' | 'Research Paper' | 'Industry Benchmark' | 'Internal SOP' | 'Risk Assessment' | 'Incident Report' | 'Policy' | 'Internal Standard';
  domain: 'Global Safety Knowledge' | 'Industry Knowledge' | 'Organization Knowledge';
  jurisdiction: string;
  publicationDate: string;
  lastUpdated: string;
  verification: VerificationStatus;
  reliability: 'High' | 'Very High' | 'Moderate' | 'Unverified';
  topics: string[];
  applicableIndustries: string[];
  summary: string;
  extractedKeyRules: string[];
  // Extended Trust & Metadata fields
  sourceAuthority?: string;
  verificationStatus?: 'Verified' | 'Pending Review' | 'Audited' | 'Flagged' | 'Rejected';
  revision?: string;
  reviewDate?: string;
  freshness?: KnowledgeFreshness;
  organizationScope?: string; // e.g. "Organization-scoped knowledge (Private Tenant)"
  isSimulated?: boolean;
  verificationHistory: {
    date: string;
    action: string;
    reviewer: string;
    notes: string;
  }[];
}

export interface InterventionItem {
  id: string;
  title: string;
  targetRiskId: string;
  targetRiskCategory: string;
  priority: 'Immediate' | 'High' | 'Medium' | 'Planned';
  reason: string;
  status: InterventionStatus;
  dateRecommended: string;
  assignee?: string;
  deadline?: string;
  recommendedActions: {
    id: number;
    title: string;
    description: string;
    assignedRole: string;
    completed?: boolean;
  }[];
  expectedIndicators: {
    metric: string;
    expectedShift: string;
  }[];
  outcomeData?: {
    baselineRisk: number;
    currentRisk: number;
    observationShift: string;
    complianceShift: string;
    nearMissShift: string;
    verdict: 'Likely Effective' | 'Highly Effective' | 'Partially Effective' | 'Inconclusive' | 'Ineffective';
    confidence: number;
    evaluationPeriod: string;
    expertAssessments: {
      id: string;
      expertName: string;
      role: string;
      date: string;
      rating: 'Effective' | 'Partially Effective' | 'Not Effective';
      comments: string;
    }[];
  };
}

export interface DataIngestionSource {
  id: string;
  name: string;
  type: 'Safelytic Core' | 'Excel / CSV' | 'Enterprise ERP' | 'External EHS' | 'IoT Telemetry' | 'REST Webhook API';
  connected: boolean;
  recordsProcessed: number;
  lastSync: string;
  dataQualityScore: number;
  syncFrequency: string;
  statusText: string;
}

export interface LearningPipelineItem {
  id: string;
  timestamp: string;
  category: 'Knowledge Ingested' | 'Expert Feedback' | 'Validated Prediction' | 'Intervention Outcome';
  title: string;
  description: string;
  impactWeightDelta: string;
  systemEffect: string;
}

export interface KnowledgeIngestionItem {
  id: string;
  title: string;
  category: 'Regulators' | 'Research' | 'Industry Sources' | 'Safety Alerts' | 'Organization Documents';
  sourceAuthority: string;
  processedDate: string;
  verificationStatus: 'Verified' | 'Audited' | 'Active Benchmark';
  itemsExtracted: number;
  summary: string;
  isSimulated?: boolean;
}

export interface PredictiveModelModule {
  id: string;
  name: 'Emerging-Risk Detection' | 'Anomaly Detection' | 'Trend Forecasting' | 'Recurring-Risk Detection';
  tagline: string;
  description: string;
  inputDataTypes: string[];
  algorithmType: string;
  improvementMetric: string;
  currentAccuracy: string;
  lastCalibrated: string;
  recalibrationMechanism: string;
}

export interface ExpertFeedbackItem {
  id: string;
  expertName: string;
  role: string;
  actionType: 'Confirming Prediction' | 'Correcting Prediction' | 'Challenging Assumption' | 'Rating Recommendation';
  targetRiskId: string;
  targetRiskTitle: string;
  date: string;
  notes: string;
  rating?: number;
  adjustment?: string;
  status: 'Applied to Model' | 'Under Review' | 'Verified';
  isSimulated?: boolean;
}

export interface OutcomeLearningRecord {
  id: string;
  riskId: string;
  riskTitle: string;
  prediction: string;
  intervention: string;
  outcome: string;
  effectiveness: string;
  modelEvaluation: string;
  date: string;
  status: 'Evaluation Completed' | 'Monitoring in Progress';
  isSimulated?: boolean;
}

export interface GovernanceLog {
  id: string;
  timestamp: string;
  actor: string;
  event: string;
  resource: string;
  securityDomain: string;
  status: 'Success' | 'Protected' | 'Audited';
}

export interface ManagementAttentionItem {
  id: string;
  title: string;
  scope: string;
  severity: 'Critical' | 'High' | 'Moderate';
  trend: string;
  trendDirection: 'Increasing' | 'Decreasing' | 'Chronic' | 'Emerging';
  owner: string;
  recommendedAction: string;
  dueDate: string;
  urgency: 'Immediate' | 'Within 48h' | 'Within 72h' | 'Within 5 Days';
  category: string;
}
