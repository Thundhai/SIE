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
  orgRecordsCount: number;
  externalSourcesCount: number;
  modelsUsedCount: number;
  summary: string;
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
  organizationEvidence: {
    id: string;
    type: 'Observation' | 'Near Miss' | 'Inspection Defect' | 'Audit Finding' | 'Permit Exception';
    title: string;
    severity: 'Low' | 'Medium' | 'High' | 'Critical';
    date: string;
    location: string;
    details: string;
    reporterRole: string;
    status: 'Open' | 'Overdue' | 'Closed' | 'In Remediation';
  }[];
  externalEvidence: {
    id: string;
    publisher: string;
    documentTitle: string;
    code: string;
    publicationDate: string;
    topic: string;
    reliability: 'High' | 'Very High' | 'Moderate';
    jurisdiction: string;
    keyExcerpt: string;
  }[];
  aiReasoning: string;
}

export interface KnowledgeDocument {
  id: string;
  source: string;
  title: string;
  documentCode: string;
  type: 'Regulatory Standard' | 'Technical Guidance' | 'Safety Alert' | 'Research Paper' | 'Industry Benchmark' | 'Internal SOP';
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

export interface GovernanceLog {
  id: string;
  timestamp: string;
  actor: string;
  event: string;
  resource: string;
  securityDomain: string;
  status: 'Success' | 'Protected' | 'Audited';
}
