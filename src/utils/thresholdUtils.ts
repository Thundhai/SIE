import { AlertThresholdConfig, EmergingRisk, NotificationItem } from '../types';

export const DEFAULT_ALERT_CONFIG: AlertThresholdConfig = {
  globalMinProbability: 70,
  globalMinConfidence: 75,
  alertOnSurgeDelta: true,
  surgeDeltaThreshold: 10,
  notifyOnOverdueActions: true,
  sensitivityPreset: 'balanced',
  channels: {
    inAppAlerts: true,
    urgentBadge: true,
    smsUrgent: true,
    emailDigest: true,
    webhookDispatch: false
  },
  categoryOverrides: [
    {
      category: 'Process Safety',
      enabled: true,
      minProbability: 60,
      minConfidence: 70,
      autoInterventionTrigger: true,
      priorityRouting: 'Critical SMS & App'
    },
    {
      category: 'Lifting Operations',
      enabled: true,
      minProbability: 70,
      minConfidence: 75,
      autoInterventionTrigger: true,
      priorityRouting: 'Critical SMS & App'
    },
    {
      category: 'Working at Height',
      enabled: true,
      minProbability: 65,
      minConfidence: 75,
      autoInterventionTrigger: false,
      priorityRouting: 'Urgent In-App'
    },
    {
      category: 'Vehicle Movement',
      enabled: true,
      minProbability: 60,
      minConfidence: 70,
      autoInterventionTrigger: false,
      priorityRouting: 'Urgent In-App'
    },
    {
      category: 'Confined Space',
      enabled: true,
      minProbability: 55,
      minConfidence: 65,
      autoInterventionTrigger: true,
      priorityRouting: 'Critical SMS & App'
    }
  ],
  userPreferences: {
    recipientName: 'Dr. Alistair Vance',
    recipientRole: 'Lead HSE Director • CMIOSH',
    email: 'alistair.vance@safelytic-engine.internal',
    phone: '+234 803 555 0192',
    designatedSites: ['Lagos Operations', 'Port Harcourt Project'],
    quietHoursEnabled: false,
    quietHoursStart: '22:00',
    quietHoursEnd: '06:00'
  }
};

export const SENSITIVITY_PRESETS: Record<'strict' | 'balanced' | 'conservative', {
  label: string;
  description: string;
  globalMinProbability: number;
  globalMinConfidence: number;
  surgeDeltaThreshold: number;
}> = {
  strict: {
    label: 'High Sensitivity (Early Warning)',
    description: 'Catches nascent risks early (lower thresholds: 55% prob / 60% conf). Recommended during high SIMOPS or major turnarounds.',
    globalMinProbability: 55,
    globalMinConfidence: 60,
    surgeDeltaThreshold: 5
  },
  balanced: {
    label: 'Balanced Standard (Default)',
    description: 'Optimal balance of statistical reliability and early intervention signal (70% prob / 75% conf).',
    globalMinProbability: 70,
    globalMinConfidence: 75,
    surgeDeltaThreshold: 10
  },
  conservative: {
    label: 'High Confidence (Low Noise)',
    description: 'Only triggers alerts for mathematically confirmed high-criticality trajectories (80% prob / 85% conf).',
    globalMinProbability: 80,
    globalMinConfidence: 85,
    surgeDeltaThreshold: 15
  }
};

export interface RiskEvaluationResult {
  riskId: string;
  title: string;
  category: string;
  probability: number;
  confidence: number;
  trendPercentage: number;
  site: string;
  isTriggered: boolean;
  triggerReasons: string[];
  severity: 'Critical' | 'High' | 'Moderate' | 'Info';
  routingChannel: string;
}

export function evaluateRisk(
  risk: EmergingRisk,
  config: AlertThresholdConfig
): RiskEvaluationResult {
  const triggerReasons: string[] = [];
  let isTriggered = false;
  let severity: 'Critical' | 'High' | 'Moderate' | 'Info' = 'Moderate';
  let routingChannel = 'In-App Alerts';

  // Site matching check
  const siteAllowed =
    config.userPreferences.designatedSites.length === 0 ||
    config.userPreferences.designatedSites.includes(risk.site) ||
    config.userPreferences.designatedSites.includes('All Sites');

  if (!siteAllowed) {
    return {
      riskId: risk.id,
      title: risk.title,
      category: risk.category,
      probability: risk.probability,
      confidence: risk.confidence,
      trendPercentage: risk.trendPercentage,
      site: risk.site,
      isTriggered: false,
      triggerReasons: ['Excluded by designated site filter'],
      severity: 'Info',
      routingChannel: 'Filtered'
    };
  }

  // 1. Check Category Override vs Global Threshold
  const override = config.categoryOverrides.find(
    o => o.category.toLowerCase() === risk.category.toLowerCase() && o.enabled
  );

  const minProb = override ? override.minProbability : config.globalMinProbability;
  const minConf = override ? override.minConfidence : config.globalMinConfidence;

  if (override) {
    routingChannel = override.priorityRouting;
  }

  // Evaluate Probability & Confidence
  if (risk.probability >= minProb && risk.confidence >= minConf) {
    isTriggered = true;
    triggerReasons.push(
      `Risk Probability ${risk.probability}% ≥ ${minProb}% threshold & Confidence ${risk.confidence}% ≥ ${minConf}%`
    );
    if (risk.probability >= 75 || risk.level === 'Critical') {
      severity = 'Critical';
    } else if (risk.probability >= 60 || risk.level === 'High') {
      severity = 'High';
    }
  }

  // 2. Evaluate Surge Trajectory Trigger
  if (config.alertOnSurgeDelta && risk.trendPercentage >= config.surgeDeltaThreshold) {
    isTriggered = true;
    triggerReasons.push(
      `Velocity Surge: +${risk.trendPercentage}% trend exceeds ${config.surgeDeltaThreshold}% surge threshold`
    );
    if (severity !== 'Critical') {
      severity = 'High';
    }
  }

  // 3. Evaluate Overdue Corrective Action Trigger
  if (config.notifyOnOverdueActions && risk.organizationEvidence) {
    const hasOverdue = risk.organizationEvidence.some(ev => ev.status === 'Overdue');
    if (hasOverdue) {
      isTriggered = true;
      triggerReasons.push('Linked to unresolved overdue corrective actions in field');
    }
  }

  return {
    riskId: risk.id,
    title: risk.title,
    category: risk.category,
    probability: risk.probability,
    confidence: risk.confidence,
    trendPercentage: risk.trendPercentage,
    site: risk.site,
    isTriggered,
    triggerReasons,
    severity,
    routingChannel
  };
}

export function evaluateAllRisks(
  risks: EmergingRisk[],
  config: AlertThresholdConfig
): RiskEvaluationResult[] {
  return risks.map(risk => evaluateRisk(risk, config));
}

export function generatePersonalizedNotifications(
  risks: EmergingRisk[],
  config: AlertThresholdConfig
): NotificationItem[] {
  const evaluations = evaluateAllRisks(risks, config);
  const triggered = evaluations.filter(e => e.isTriggered);

  return triggered.map((item, idx) => ({
    id: `CUSTOM-ALERT-${item.riskId}-${Date.now()}-${idx}`,
    title: `[Threshold Alert] ${item.title}`,
    category: 'Risk Alert',
    message: `${config.userPreferences.recipientName}: Alert triggered for ${item.category} (${item.site}). ${item.triggerReasons.join(' • ')}`,
    timestamp: 'Just now',
    severity: item.severity,
    isRead: false,
    relatedRiskId: item.riskId
  }));
}
