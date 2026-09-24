import { useEffect, useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { PageContainer } from '../../components/layout/PageContainer';
import { Section } from '../../components/layout/Section';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { LoadingState } from '../../components/ui/LoadingState';
import { PriorityBadge } from '../../components/ui/PriorityBadge';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { actionStatusLabel, actionStatusTone, actionTypeLabel, toPriorityLevel } from '../actions/actionStatus';
import { eventStatusLabel, eventStatusTone, formatCanonicalLabel } from '../events/eventStatus';
import {
  anomalyDirectionLabel,
  anomalyStatusLabel,
  anomalyStatusTone,
  associationLabel,
  concentrationLabel,
  dataSufficiencyLabel,
  dataSufficiencyTone,
  recurrenceLabel,
  recurrenceTone,
  riskClassificationLabel,
  riskClassificationTone,
  trendLabel,
  trendTone,
} from '../intelligence/intelligenceLabels';
import { signalDescription, signalSeverityLabel, signalSeverityTone } from './reportsLabels';
import { listActions, type ActionListResponse, type ActionResponse } from '../../services/api/actions';
import { getAnalyticsSummary, type AnalyticsSummary } from '../../services/api/analytics';
import { listEvents, type EventSummaryResponse } from '../../services/api/events';
import { getEnterpriseIntelligence, type EnterpriseIntelligence } from '../../services/api/intelligence';
import type { AsyncState } from '../../types/common';

const WINDOW_DAYS = 30;
const ACTION_PRIORITY_RANK: Record<string, number> = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

interface ReportData {
  intelligence: EnterpriseIntelligence;
  analytics: AnalyticsSummary;
  events: EventSummaryResponse[];
  actions: ActionListResponse;
}

/**
 * Reports — an authoritative management view assembled entirely from
 * already-computed backend responses (`GET /intelligence/enterprise`,
 * `GET /intelligence/analytics/summary`, `GET /events`, `GET /actions`).
 * No risk score, trend, indicator, pattern, anomaly, association, or
 * concentration is recalculated here — every number and classification
 * on this page is exactly what the backend returned, formatted for
 * display only (see `intelligenceLabels.ts`/`actionStatus.ts`/
 * `eventStatus.ts` for the plain-language mapping of governed backend
 * vocabularies this page reuses rather than reinvents).
 */
export function ReportsPage() {
  const auth = useAuth();
  const [state, setState] = useState<AsyncState<ReportData>>({ status: 'loading' });
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    if (!auth.organization) return;
    const controller = new AbortController();
    setState({ status: 'loading' });

    Promise.all([
      getEnterpriseIntelligence({ organizationId: auth.organization.id, windowDays: WINDOW_DAYS }, controller.signal),
      getAnalyticsSummary({ organizationId: auth.organization.id, windowDays: WINDOW_DAYS }, controller.signal),
      listEvents({ organizationId: auth.organization.id, page: 1, pageSize: 100, signal: controller.signal }),
      listActions({ organizationId: auth.organization.id, page: 1, pageSize: 100 }),
    ])
      .then(([intelligence, analytics, eventResult, actions]) => {
        setState({ status: 'success', data: { intelligence, analytics, events: eventResult.items, actions } });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load report data.' });
      });

    return () => controller.abort();
  }, [auth.organization, reloadToken]);

  if (!auth.organization) {
    return (
      <PageContainer>
        <h1 className="text-xl font-semibold text-navy-900">Reports</h1>
        <EmptyState title="No organization context available" description="A development identity is not configured, or it could not be resolved against the backend." />
      </PageContainer>
    );
  }

  const isPermissionDenied = state.status === 'error' && state.message.toLowerCase().includes('permission');

  return (
    <PageContainer>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-navy-900">Reports</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Management view of recorded safety activity and deterministic intelligence for the organization. This report
            displays calculations already performed by the backend — nothing is recalculated in the browser.
          </p>
        </div>
        <div className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-text-secondary">
          Reporting window: last {WINDOW_DAYS} days
        </div>
      </div>

      {state.status === 'loading' && <LoadingState label="Loading report data…" />}

      {state.status === 'error' && isPermissionDenied && (
        <EmptyState title="You don't have permission to view this report" description="Ask an administrator for intelligence:read access in this organization." />
      )}

      {state.status === 'error' && !isPermissionDenied && (
        <ErrorState title="Could not load report data" description={state.message} onRetry={() => setReloadToken((token) => token + 1)} />
      )}

      {state.status === 'success' && <ReportContent data={state.data} />}
    </PageContainer>
  );
}

function ReportContent({ data }: { data: ReportData }) {
  const { intelligence, analytics, events, actions } = data;
  const risk = intelligence.deterministic_risk;
  const trend = intelligence.trend;

  return (
    <>
      <Section
        title="Reporting period"
        description="The current analysis window and the immediately preceding, equal-length comparison window the backend measures every trend against."
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-lg border border-border bg-surface p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Current period</p>
            <p className="mt-1 text-sm font-medium text-text-primary">
              {formatDate(trend.current_period_start)} – {formatDate(trend.current_period_end)}
            </p>
          </div>
          <div className="rounded-lg border border-border bg-surface p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Comparison period</p>
            <p className="mt-1 text-sm font-medium text-text-primary">
              {formatDate(trend.previous_period_start)} – {formatDate(trend.previous_period_end)}
            </p>
          </div>
        </div>
      </Section>

      <Section title="Executive summary" description="This report is assembled from authoritative SIE backend responses. It does not recalculate risk in the browser.">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <Metric label="Risk score" value={risk.score === null ? '—' : risk.score.toFixed(1)} />
          <Metric label="Recorded events" value={analytics.event_count} />
          <Metric label="Open actions" value={intelligence.actions_context?.open_action_count ?? 0} />
          <Metric label="High-priority actions" value={intelligence.actions_context?.high_priority_action_count ?? 0} />
          <Metric label="Overdue actions" value={intelligence.actions_context?.overdue_action_count ?? 0} />
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <div className="rounded-lg border border-border bg-surface p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Risk classification</p>
            <div className="mt-2">
              <StatusBadge tone={riskClassificationTone(risk.classification)} label={riskClassificationLabel(risk.classification)} />
            </div>
          </div>
          <div className="rounded-lg border border-border bg-surface p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Data sufficiency</p>
            <div className="mt-2">
              <StatusBadge tone={dataSufficiencyTone(intelligence.data_sufficiency.status)} label={dataSufficiencyLabel(intelligence.data_sufficiency.status)} />
            </div>
          </div>
          <div className="rounded-lg border border-border bg-surface p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Incident trend</p>
            <div className="mt-2">
              <StatusBadge tone={trendTone(trend.classification)} label={trendLabel(trend.classification)} />
            </div>
          </div>
        </div>

        {intelligence.explanations.length > 0 && (
          <div className="mt-4">
            <p className="text-xs font-medium uppercase tracking-wide text-text-muted">What the numbers show</p>
            <ul className="mt-2 flex flex-col gap-2">
              {intelligence.explanations.map((explanation, index) => (
                <li key={`${explanation.code}-${index}`} className="rounded-lg border border-border bg-surface p-3.5">
                  <p className="text-sm text-text-primary">{explanation.message}</p>
                  <p className="mt-1 text-xs text-text-muted">Evidence: {explanation.evidence_reference}</p>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Section>

      <Section
        title="Risk profile"
        description={`Deterministic risk score version ${risk.version} — every component below is a backend-computed contribution, not a frontend calculation.`}
      >
        {risk.score === null ? (
          <EmptyState title="Risk score not available" description={risk.insufficient_data_reason ?? 'Insufficient data to compute a risk score for the current window.'} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-left text-sm">
              <thead>
                <tr className="border-b border-border text-xs uppercase tracking-wide text-text-muted">
                  <th className="px-3 py-2">Component</th>
                  <th className="px-3 py-2">Raw score</th>
                  <th className="px-3 py-2">Weight</th>
                  <th className="px-3 py-2">Contribution</th>
                </tr>
              </thead>
              <tbody>
                {risk.components.map((component) => (
                  <tr key={component.key} className="border-b border-border">
                    <td className="px-3 py-3 font-medium text-text-primary">{component.label}</td>
                    <td className="px-3 py-3 text-text-secondary">{component.raw_score.toFixed(1)} / 100</td>
                    <td className="px-3 py-3 text-text-secondary">{component.normalized_weight.toFixed(1)}%</td>
                    <td className="px-3 py-3 text-text-secondary">{component.contribution.toFixed(1)} pts</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <IndicatorsSection indicators={intelligence.indicators} />

      <ActionStatusSection actions={actions.items} />

      <SignalsSection signals={analytics.signals} />

      <Section title="Recurring patterns" description="Deterministic recurrence detection over the current reporting window.">
        {intelligence.patterns.length === 0 ? (
          <EmptyState title="No recurring patterns" description="No recurring event patterns were detected for the current window." />
        ) : (
          <ul className="flex flex-col gap-2">
            {intelligence.patterns.map((pattern) => (
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
        )}
      </Section>

      <Section title="Anomalies" description="Metrics whose current-period value deviates statistically from their own recent baseline — a deviation, not automatically a risk conclusion.">
        {intelligence.anomalies.filter((a) => a.status === 'ANOMALOUS').length === 0 ? (
          <EmptyState title="No anomalies detected" description="No metric in the current window deviated from its baseline." />
        ) : (
          <ul className="flex flex-col gap-2">
            {intelligence.anomalies
              .filter((anomaly) => anomaly.status === 'ANOMALOUS')
              .map((anomaly) => (
                <li key={anomaly.metric} className="flex flex-col gap-1.5 rounded-lg border border-border bg-surface p-3.5">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-medium text-text-primary">{anomaly.label}</p>
                    <StatusBadge tone={anomalyStatusTone(anomaly.status)} label={anomalyDirectionLabel(anomaly.direction)} />
                  </div>
                  <p className="text-xs text-text-secondary">
                    Current value {anomaly.current_value}
                    {anomaly.baseline_mean !== null ? `, baseline average ${anomaly.baseline_mean.toFixed(1)}` : ', no baseline available'}.
                  </p>
                </li>
              ))}
          </ul>
        )}
      </Section>

      <Section title="Risk concentration" description="How concentrated recorded events are within a single site, event type, or other dimension — a share-of-total reading, unrelated to the enterprise risk score's own 0–100 scale.">
        {intelligence.concentrations.length === 0 ? (
          <EmptyState title="No concentration data" description="No concentration analysis was computed for the current window." />
        ) : (
          <ul className="flex flex-col gap-2">
            {intelligence.concentrations.map((c) => (
              <li key={`${c.dimension}-${c.key}`} className="flex items-center justify-between gap-3 rounded-lg border border-border bg-surface p-3.5">
                <div>
                  <p className="text-sm font-medium text-text-primary">{c.label}</p>
                  <p className="mt-0.5 text-xs text-text-muted">
                    {formatCanonicalLabel(c.dimension)} · {c.count} of {c.total} ({c.percentage.toFixed(1)}%)
                  </p>
                </div>
                <StatusBadge tone={c.classification === 'HIGH' ? 'warning' : c.classification === 'MODERATE' ? 'informational' : 'neutral'} label={concentrationLabel(c.classification)} />
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Associations" description="Correlation between two metrics' period-over-period movement — a co-movement observation, never a claim that one causes the other.">
        {intelligence.associations.length === 0 ? (
          <EmptyState title="No associations available" description="No metric associations were computed for the current window." />
        ) : (
          <ul className="flex flex-col gap-2">
            {intelligence.associations.map((association) => (
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
        )}
      </Section>

      <DataQualitySection dataSufficiency={analytics.data_sufficiency} eventCount={analytics.event_count} sourceReliability={analytics.source_reliability} />

      <Section title="Recent safety activity" description="Recorded events in the reporting window.">
        {events.length === 0 ? (
          <EmptyState title="No events recorded" description="No safety events were returned for this reporting window." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[680px] text-left text-sm">
              <thead>
                <tr className="border-b border-border text-xs uppercase tracking-wide text-text-muted">
                  <th className="px-3 py-2">Date</th>
                  <th className="px-3 py-2">Event</th>
                  <th className="px-3 py-2">Site</th>
                  <th className="px-3 py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {events.slice(0, 20).map((event) => (
                  <tr key={event.id} className="border-b border-border">
                    <td className="px-3 py-3">{new Date(event.event_time).toLocaleDateString()}</td>
                    <td className="px-3 py-3">
                      {formatCanonicalLabel(event.event_type)}
                      {event.event_subtype ? ' · ' + formatCanonicalLabel(event.event_subtype) : ''}
                    </td>
                    <td className="px-3 py-3">{event.site_name ?? '—'}</td>
                    <td className="px-3 py-3">
                      {event.status ? <StatusBadge tone={eventStatusTone(event.status)} label={eventStatusLabel(event.status)} /> : 'Unspecified'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section title="Report provenance" description="Calculation source and generation details — use these values when interpreting or exporting this report.">
        <div className="grid gap-3 sm:grid-cols-3">
          <Metric label="As of" value={formatDateTime(intelligence.as_of)} />
          <Metric label="Events supporting intelligence" value={intelligence.provenance.event_count} />
          <Metric label="Generated" value={formatDateTime(intelligence.provenance.generated_at)} />
        </div>
        {Object.keys(intelligence.provenance.calculation_versions).length > 0 && (
          <div className="mt-4">
            <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Calculation source</p>
            <ul className="mt-2 grid gap-1.5 sm:grid-cols-2">
              {Object.entries(intelligence.provenance.calculation_versions).map(([key, version]) => (
                <li key={key} className="rounded-md bg-surface-muted px-3 py-2 text-xs text-text-secondary">
                  <span className="font-medium text-text-primary">{formatCanonicalLabel(key)}</span> — {version}
                </li>
              ))}
            </ul>
          </div>
        )}
      </Section>
    </>
  );
}

function IndicatorsSection({ indicators }: { indicators: EnterpriseIntelligence['indicators'] }) {
  const lagging = indicators.filter((i) => i.category === 'LAGGING');
  const leading = indicators.filter((i) => i.category === 'LEADING');

  return (
    <Section title="Event activity" description="Every recorded indicator for the current period compared with the immediately preceding period — lagging indicators (outcomes already realized) and leading indicators (activity believed to precede outcomes), grouped as the backend itself categorizes them.">
      {indicators.length === 0 ? (
        <EmptyState title="No indicators available" description="The current reporting window did not produce enterprise indicators." />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          <IndicatorGroup title="Lagging indicators" items={lagging} />
          <IndicatorGroup title="Leading indicators" items={leading} />
        </div>
      )}
    </Section>
  );
}

function IndicatorGroup({ title, items }: { title: string; items: EnterpriseIntelligence['indicators'] }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-text-primary">{title}</h3>
      <ul className="mt-2 flex flex-col gap-2">
        {items.map((indicator) => (
          <li key={indicator.key} className="flex items-center justify-between gap-3 rounded-lg border border-border bg-surface p-3">
            <p className="text-sm text-text-primary">{indicator.label}</p>
            <div className="text-right">
              <p className="text-sm font-semibold text-text-primary">{indicator.value}</p>
              <p className="text-xs text-text-muted">
                was {indicator.previous_value}
                {indicator.percentage_change !== null ? ` (${indicator.percentage_change > 0 ? '+' : ''}${indicator.percentage_change.toFixed(1)}%)` : ''}
              </p>
            </div>
          </li>
        ))}
        {items.length === 0 && <p className="text-xs text-text-muted">None recorded.</p>}
      </ul>
    </div>
  );
}

function ActionStatusSection({ actions }: { actions: ActionResponse[] }) {
  const sorted = [...actions]
    .filter((action) => action.status !== 'COMPLETED' && action.status !== 'CANCELLED')
    .sort((a, b) => (ACTION_PRIORITY_RANK[a.priority] ?? 9) - (ACTION_PRIORITY_RANK[b.priority] ?? 9));

  return (
    <Section title="Action status" description="Open corrective actions, ranked by priority — the highest-priority open items management should review first.">
      {sorted.length === 0 ? (
        <EmptyState title="No open actions" description="Every corrective action in this organization is completed or cancelled." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead>
              <tr className="border-b border-border text-xs uppercase tracking-wide text-text-muted">
                <th className="px-3 py-2">Action</th>
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2">Priority</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Due</th>
                <th className="px-3 py-2">Owner</th>
              </tr>
            </thead>
            <tbody>
              {sorted.slice(0, 15).map((action) => (
                <tr key={action.id} className="border-b border-border">
                  <td className="px-3 py-3 font-medium text-text-primary">{action.title}</td>
                  <td className="px-3 py-3 text-text-secondary">{actionTypeLabel(action.action_type)}</td>
                  <td className="px-3 py-3">
                    <PriorityBadge priority={toPriorityLevel(action.priority)} />
                  </td>
                  <td className="px-3 py-3">
                    <StatusBadge tone={actionStatusTone(action.status)} label={actionStatusLabel(action.status)} />
                  </td>
                  <td className="px-3 py-3 text-text-secondary">{action.due_date ? formatDate(action.due_date) : '—'}</td>
                  <td className="px-3 py-3 text-text-secondary">{action.owner_name ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {sorted.length > 15 && <p className="mt-2 text-xs text-text-muted">Showing the 15 highest-priority of {sorted.length} open actions.</p>}
        </div>
      )}
    </Section>
  );
}

function SignalsSection({ signals }: { signals: AnalyticsSummary['signals'] }) {
  return (
    <Section title="Intelligence signals" description="Deterministic, rule-based signals computed from recorded events — never a prediction or probability.">
      {signals.length === 0 ? (
        <EmptyState title="No signals at this time" description="Nothing in the current window has crossed a signal threshold." />
      ) : (
        <ul className="flex flex-col gap-2">
          {signals.map((signal, index) => (
            <li key={`${signal.signal_type}-${index}`} className="flex items-center justify-between gap-3 rounded-lg border border-border bg-surface p-3.5">
              <div>
                <p className="text-sm font-medium text-text-primary">{signalDescription(signal.signal_type)}</p>
                <p className="mt-0.5 text-xs text-text-muted">
                  {new Date(signal.observed_period_start).toLocaleDateString()} – {new Date(signal.observed_period_end).toLocaleDateString()}
                </p>
              </div>
              <StatusBadge tone={signalSeverityTone(signal.severity)} label={signalSeverityLabel(signal.severity)} />
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

function DataQualitySection({
  dataSufficiency,
  eventCount,
  sourceReliability,
}: {
  dataSufficiency: string;
  eventCount: number;
  sourceReliability: AnalyticsSummary['source_reliability'];
}) {
  return (
    <Section title="Data quality and sufficiency" description="How much recorded data this report rests on, and the reliability of each ingestion source feeding it.">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-lg border border-border bg-surface p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Overall data sufficiency</p>
          <div className="mt-2">
            <StatusBadge tone={dataSufficiencyTone(dataSufficiency)} label={dataSufficiencyLabel(dataSufficiency)} />
          </div>
        </div>
        <Metric label="Events in window" value={eventCount} />
      </div>

      {sourceReliability.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[680px] text-left text-sm">
            <thead>
              <tr className="border-b border-border text-xs uppercase tracking-wide text-text-muted">
                <th className="px-3 py-2">Source system</th>
                <th className="px-3 py-2">Valid</th>
                <th className="px-3 py-2">Partial</th>
                <th className="px-3 py-2">Invalid</th>
                <th className="px-3 py-2">Quarantined</th>
                <th className="px-3 py-2">Freshness</th>
              </tr>
            </thead>
            <tbody>
              {sourceReliability.map((source) => (
                <tr key={source.source_system} className="border-b border-border">
                  <td className="px-3 py-3 font-medium text-text-primary">{source.source_system}</td>
                  <td className="px-3 py-3 text-text-secondary">{source.valid_count}</td>
                  <td className="px-3 py-3 text-text-secondary">{source.partial_count}</td>
                  <td className="px-3 py-3 text-text-secondary">{source.invalid_count}</td>
                  <td className="px-3 py-3 text-text-secondary">{source.quarantined_count}</td>
                  <td className="px-3 py-3">
                    {source.is_stale ? (
                      <StatusBadge tone="warning" label={`Stale (>${source.freshness_threshold_days}d)`} />
                    ) : (
                      <StatusBadge tone="success" label="Current" />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-text-muted">{label}</p>
      <p className="mt-1 text-xl font-semibold text-text-primary">{value}</p>
    </div>
  );
}
