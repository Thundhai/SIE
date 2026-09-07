import { Info } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { PageContainer } from '../../components/layout/PageContainer';
import { Section } from '../../components/layout/Section';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { LoadingState } from '../../components/ui/LoadingState';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { Tabs } from '../../components/ui/Tabs';
import { getEnterpriseIntelligence, type EnterpriseIntelligence } from '../../services/api/intelligence';
import type { AsyncState } from '../../types/common';
import { formatCanonicalLabel } from '../events/eventStatus';
import {
  anomalyDirectionLabel,
  anomalyStatusLabel,
  anomalyStatusTone,
  associationLabel,
  dataSufficiencyLabel,
  dataSufficiencyTone,
  recurrenceLabel,
  recurrenceTone,
  riskClassificationLabel,
  riskClassificationTone,
  trendLabel,
  trendTone,
} from './intelligenceLabels';

const TABS = [
  { value: 'indicators', label: 'Indicators' },
  { value: 'anomalies', label: 'Anomalies' },
  { value: 'patterns', label: 'Patterns' },
  { value: 'associations', label: 'Associations' },
];

/**
 * Intelligence — the deterministic enterprise-intelligence workspace,
 * backed entirely by the real `GET /intelligence/enterprise` endpoint
 * (SIE Milestone 22/23, `INTELLIGENCE_READ`). No calculation is repeated
 * here: every score, classification, and count is exactly what the
 * backend returned. Plain HSE language throughout (see
 * `intelligenceLabels.ts`) — never "AI detected"/"AI prediction"
 * phrasing, and an anomaly is presented as a deviation from baseline,
 * never as an automatic risk conclusion. Site-level intelligence
 * (`GET /intelligence/sites/{site_id}`) and Risk Assessment
 * findings/controls/effectiveness stay for a later UI milestone — see
 * this file's own "known limitations" note in the completion report.
 */
export function IntelligencePage() {
  const auth = useAuth();
  const [state, setState] = useState<AsyncState<EnterpriseIntelligence>>({ status: 'loading' });
  const [reloadToken, setReloadToken] = useState(0);
  const [tab, setTab] = useState('indicators');

  useEffect(() => {
    if (!auth.organization) return;
    const controller = new AbortController();
    setState({ status: 'loading' });
    getEnterpriseIntelligence({ organizationId: auth.organization.id }, controller.signal)
      .then((data) => setState({ status: 'success', data }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load intelligence data.' });
      });
    return () => controller.abort();
  }, [auth.organization, reloadToken]);

  const isPermissionDenied = state.status === 'error' && state.message.toLowerCase().includes('missing') && state.message.toLowerCase().includes('permission');

  return (
    <PageContainer>
      <div>
        <h1 className="text-xl font-semibold text-navy-900">Intelligence</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Deterministic risk, trend, anomaly, and pattern intelligence computed from your organization's recorded events.
        </p>
      </div>

      {!auth.organization && (
        <EmptyState
          title="No organization context available"
          description="A development identity is not configured, or it could not be resolved against the backend. See docs/FRONTEND_ARCHITECTURE.md for setup."
        />
      )}

      {auth.organization && state.status === 'loading' && <LoadingState label="Loading intelligence data…" />}

      {auth.organization && state.status === 'error' && isPermissionDenied && (
        <EmptyState title="You don't have permission to view this" description="Ask an administrator for intelligence:read access in this organization." />
      )}

      {auth.organization && state.status === 'error' && !isPermissionDenied && (
        <ErrorState title="Could not load intelligence data" description={state.message} onRetry={() => setReloadToken((token) => token + 1)} />
      )}

      {auth.organization && state.status === 'success' && (
        <IntelligenceContent data={state.data} tab={tab} onTabChange={setTab} />
      )}
    </PageContainer>
  );
}

function IntelligenceContent({
  data,
  tab,
  onTabChange,
}: {
  data: EnterpriseIntelligence;
  tab: string;
  onTabChange: (value: string) => void;
}) {
  const insufficientData = data.data_sufficiency.status === 'INSUFFICIENT_DATA';

  return (
    <>
      {insufficientData && (
        <div className="flex items-start gap-2 rounded-md border border-informational/30 bg-informational-surface px-3 py-2.5 text-sm text-informational">
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <p>
            Insufficient data for a reliable enterprise picture ({data.provenance.event_count} recorded event
            {data.provenance.event_count === 1 ? '' : 's'} over the last {data.window_days} days). The figures below
            still reflect exactly what has been recorded so far.
          </p>
        </div>
      )}

      <Section title="Enterprise risk" description={`As of ${new Date(data.as_of).toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}, based on the last ${data.window_days} days.`}>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {/* SIE Milestone UI-DESIGN-01: the headline enterprise-risk
              number is this page's one Level-3 "elevated important
              content" tile — a restrained shadow on top of the ordinary
              card border. Classification/data-sufficiency stay plain
              Level-2 cards. */}
          <div className="rounded-lg border border-border bg-surface p-4 shadow-xs">
            <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Risk score</p>
            <p className="mt-1 text-2xl font-semibold text-text-primary">
              {data.deterministic_risk.score !== null ? data.deterministic_risk.score.toFixed(1) : '—'}
            </p>
            {data.deterministic_risk.insufficient_data_reason && (
              <p className="mt-1 text-xs text-text-muted">{data.deterministic_risk.insufficient_data_reason}</p>
            )}
          </div>
          <div className="rounded-lg border border-border bg-surface p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Risk classification</p>
            <div className="mt-1.5">
              <StatusBadge
                tone={riskClassificationTone(data.deterministic_risk.classification)}
                label={riskClassificationLabel(data.deterministic_risk.classification)}
              />
            </div>
          </div>
          <div className="rounded-lg border border-border bg-surface p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Data sufficiency</p>
            <div className="mt-1.5">
              <StatusBadge tone={dataSufficiencyTone(data.data_sufficiency.status)} label={dataSufficiencyLabel(data.data_sufficiency.status)} />
            </div>
          </div>
        </div>
      </Section>

      <Section title="Trend" description={data.trend.metric.replaceAll('_', ' ')}>
        <div className="flex items-center justify-between gap-3 rounded-lg border border-border bg-surface p-4">
          <div>
            <p className="text-sm text-text-primary">
              {data.trend.current_value} recorded, compared with {data.trend.previous_value} in the prior period
              {data.trend.percentage_change !== null ? ` (${data.trend.percentage_change > 0 ? '+' : ''}${data.trend.percentage_change.toFixed(1)}%)` : ''}.
            </p>
          </div>
          <StatusBadge tone={trendTone(data.trend.classification)} label={trendLabel(data.trend.classification)} />
        </div>
      </Section>

      <Section title="Details">
        <Tabs items={TABS} value={tab} onChange={onTabChange} />
        {tab === 'indicators' && <IndicatorsPanel data={data} />}
        {tab === 'anomalies' && <AnomaliesPanel data={data} />}
        {tab === 'patterns' && <PatternsPanel data={data} />}
        {tab === 'associations' && <AssociationsPanel data={data} />}
      </Section>

      <p className="text-xs text-text-muted">
        Generated {new Date(data.provenance.generated_at).toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
        {' · '}
        Based on {data.provenance.total_supporting_events} supporting event{data.provenance.total_supporting_events === 1 ? '' : 's'}.
      </p>
    </>
  );
}

function IndicatorsPanel({ data }: { data: EnterpriseIntelligence }) {
  if (data.indicators.length === 0) {
    return <EmptyState title="No indicators available" description="No indicator values were computed for the current window." />;
  }
  return (
    <ul className="mt-3 flex flex-col gap-2">
      {data.indicators.map((indicator) => (
        <li key={indicator.key} className="flex items-center justify-between gap-3 rounded-lg border border-border bg-surface p-3.5">
          <div>
            <p className="text-sm font-medium text-text-primary">{indicator.label}</p>
            <p className="mt-0.5 text-xs text-text-muted">
              {indicator.category.charAt(0) + indicator.category.slice(1).toLowerCase()} indicator · last {indicator.window_days} days
              {indicator.unavailable_reason ? ` · ${indicator.unavailable_reason}` : ''}
            </p>
          </div>
          <div className="text-right">
            <p className="text-lg font-semibold text-text-primary">{indicator.value}</p>
            <p className="text-xs text-text-muted">
              previously {indicator.previous_value}
              {indicator.percentage_change !== null ? ` (${indicator.percentage_change > 0 ? '+' : ''}${indicator.percentage_change.toFixed(1)}%)` : ''}
            </p>
          </div>
        </li>
      ))}
    </ul>
  );
}

function AnomaliesPanel({ data }: { data: EnterpriseIntelligence }) {
  if (data.anomalies.length === 0) {
    return <EmptyState title="No anomaly data available" description="No anomaly scan results were computed for the current window." />;
  }
  return (
    <ul className="mt-3 flex flex-col gap-2">
      {data.anomalies.map((anomaly) => (
        <li key={anomaly.metric} className="flex flex-col gap-1.5 rounded-lg border border-border bg-surface p-3.5">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm font-medium text-text-primary">{anomaly.label}</p>
            <StatusBadge tone={anomalyStatusTone(anomaly.status)} label={anomalyStatusLabel(anomaly.status)} />
          </div>
          <p className="text-xs text-text-secondary">
            Current value {anomaly.current_value}
            {anomaly.baseline_mean !== null ? `, baseline average ${anomaly.baseline_mean.toFixed(1)}` : ', no baseline available'}
            {anomaly.status === 'ANOMALOUS' ? ` — ${anomalyDirectionLabel(anomaly.direction)}` : ''}.
          </p>
          <p className="text-xs text-text-muted">
            {anomaly.supporting_event_count} supporting event{anomaly.supporting_event_count === 1 ? '' : 's'} · {anomaly.baseline_period_count} baseline period{anomaly.baseline_period_count === 1 ? '' : 's'}
          </p>
        </li>
      ))}
    </ul>
  );
}

function PatternsPanel({ data }: { data: EnterpriseIntelligence }) {
  if (data.patterns.length === 0) {
    return <EmptyState title="No recurring patterns" description="No recurring event patterns were detected for the current window." />;
  }
  return (
    <ul className="mt-3 flex flex-col gap-2">
      {data.patterns.map((pattern) => (
        <li key={pattern.pattern_key} className="flex items-center justify-between gap-3 rounded-lg border border-border bg-surface p-3.5">
          <div>
            <p className="text-sm font-medium text-text-primary">
              {formatCanonicalLabel(pattern.event_type)}
              {pattern.event_subtype && pattern.event_subtype !== pattern.event_type ? ` · ${formatCanonicalLabel(pattern.event_subtype)}` : ''}
            </p>
            <p className="mt-0.5 text-xs text-text-muted">
              {pattern.site_label} · {pattern.count} occurrence{pattern.count === 1 ? '' : 's'}
            </p>
          </div>
          <StatusBadge tone={recurrenceTone(pattern.classification)} label={recurrenceLabel(pattern.classification)} />
        </li>
      ))}
    </ul>
  );
}

function AssociationsPanel({ data }: { data: EnterpriseIntelligence }) {
  if (data.associations.length === 0) {
    return <EmptyState title="No associations available" description="No metric associations were computed for the current window." />;
  }
  return (
    <ul className="mt-3 flex flex-col gap-2">
      {data.associations.map((association) => (
        <li key={`${association.metric_a}-${association.metric_b}`} className="flex items-center justify-between gap-3 rounded-lg border border-border bg-surface p-3.5">
          <div>
            <p className="text-sm font-medium text-text-primary">
              {association.label_a} &amp; {association.label_b}
            </p>
            <p className="mt-0.5 text-xs text-text-muted">
              {association.period_count} period{association.period_count === 1 ? '' : 's'}
              {association.correlation_coefficient !== null ? ` · coefficient ${association.correlation_coefficient.toFixed(2)}` : ''}
            </p>
          </div>
          <StatusBadge tone="informational" label={associationLabel(association.classification)} />
        </li>
      ))}
    </ul>
  );
}
