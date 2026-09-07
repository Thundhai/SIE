import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { PageContainer } from '../../components/layout/PageContainer';
import { Section } from '../../components/layout/Section';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { LoadingState } from '../../components/ui/LoadingState';
import { StatusBadge } from '../../components/ui/StatusBadge';
import {
  anomalyDirectionLabel,
  anomalyStatusLabel,
  anomalyStatusTone,
  dataSufficiencyLabel,
  dataSufficiencyTone,
  riskClassificationLabel,
  riskClassificationTone,
} from '../intelligence/intelligenceLabels';
import { getAnalyticsSummary, type AnalyticsSummary, type RiskSignal } from '../../services/api/analytics';
import { listEvents, type EventSummaryResponse } from '../../services/api/events';
import { getEnterpriseIntelligence, type EnterpriseIntelligence } from '../../services/api/intelligence';
import { eventStatusLabel, eventStatusTone, formatCanonicalLabel } from '../events/eventStatus';
import type { AsyncState, StatusTone } from '../../types/common';

const SUFFICIENCY_LABEL: Record<string, string> = {
  SUFFICIENT_DATA: 'Sufficient data',
  LIMITED_DATA: 'Limited data',
  INSUFFICIENT_DATA: 'Insufficient data',
};

const SUFFICIENCY_TONE: Record<string, StatusTone> = {
  SUFFICIENT_DATA: 'success',
  LIMITED_DATA: 'informational',
  INSUFFICIENT_DATA: 'warning',
};

const SEVERITY_LABEL: Record<string, string> = { LOW: 'Low', MEDIUM: 'Medium', HIGH: 'High' };
const SEVERITY_TONE: Record<string, StatusTone> = { LOW: 'neutral', MEDIUM: 'warning', HIGH: 'critical' };

const RECENT_EVENTS_COUNT = 5;

function signalDescription(signal: RiskSignal): string {
  // A restrained, human-readable rendering of the signal type — never
  // an invented narrative beyond what the backend's own signal_type
  // value names (app/intelligence/enums.py). Falls back to the raw
  // value for any type not covered, so nothing is ever hidden.
  const known: Record<string, string> = {
    OVERDUE_ACTION_SURGE: 'A surge in overdue corrective actions was detected.',
  };
  return known[signal.signal_type] ?? signal.signal_type.replaceAll('_', ' ').toLowerCase();
}

/**
 * Home — "What needs my attention?" SIE Milestone UI-01 upgrades this
 * screen with the enterprise risk score, a plain-language "what is
 * changing" summary, a "needs attention" glance, and recent events — all
 * from real, already-built backend endpoints
 * (`GET /intelligence/enterprise`, `GET /events`), never a second risk
 * calculation reproduced here. The pre-existing "At a glance"/"Signals
 * requiring attention"/"Key indicators" sections (backed by
 * `GET /intelligence/analytics/summary`, SIE Frontend Foundation v0.1)
 * are kept exactly as they were — a genuinely distinct, rule-based
 * signal mechanism, not redundant with the anomaly/pattern data above
 * it. Each section fetches independently, so one section's failure never
 * blanks out the rest of the page (§17 "PARTIAL_DATA").
 */
export function HomePage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [analyticsState, setAnalyticsState] = useState<AsyncState<AnalyticsSummary>>({ status: 'loading' });
  const [intelligenceState, setIntelligenceState] = useState<AsyncState<EnterpriseIntelligence>>({ status: 'loading' });
  const [eventsState, setEventsState] = useState<AsyncState<EventSummaryResponse[]>>({ status: 'loading' });
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    if (!auth.organization) return;
    const controller = new AbortController();
    setAnalyticsState({ status: 'loading' });
    getAnalyticsSummary({ organizationId: auth.organization.id }, controller.signal)
      .then((summary) => setAnalyticsState({ status: 'success', data: summary }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setAnalyticsState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load analytics.' });
      });
    return () => controller.abort();
  }, [auth.organization, reloadToken]);

  useEffect(() => {
    if (!auth.organization) return;
    const controller = new AbortController();
    setIntelligenceState({ status: 'loading' });
    getEnterpriseIntelligence({ organizationId: auth.organization.id }, controller.signal)
      .then((data) => setIntelligenceState({ status: 'success', data }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setIntelligenceState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load enterprise risk data.' });
      });
    return () => controller.abort();
  }, [auth.organization, reloadToken]);

  useEffect(() => {
    if (!auth.organization) return;
    const controller = new AbortController();
    setEventsState({ status: 'loading' });
    listEvents({ organizationId: auth.organization.id, page: 1, pageSize: RECENT_EVENTS_COUNT, signal: controller.signal })
      .then((result) => setEventsState({ status: 'success', data: result.items }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setEventsState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load recent events.' });
      });
    return () => controller.abort();
  }, [auth.organization, reloadToken]);

  return (
    <PageContainer>
      <div>
        <h1 className="text-xl font-semibold text-text-primary">Home</h1>
        <p className="mt-1 text-sm text-text-secondary">What needs your attention right now.</p>
      </div>

      {!auth.organization && (
        <EmptyState
          title="No organization context available"
          description="A development identity is not configured (VITE_DEV_USER_ID/VITE_DEV_ORGANIZATION_ID), or it could not be resolved against the backend. See docs/FRONTEND_ARCHITECTURE.md for setup."
        />
      )}

      {auth.organization && (
        <>
          <EnterpriseRiskSection state={intelligenceState} onRetry={() => setReloadToken((t) => t + 1)} />
          <WhatIsChangingSection state={intelligenceState} />
          <NeedsAttentionSection state={intelligenceState} />
          <RecentEventsSection state={eventsState} onRetry={() => setReloadToken((t) => t + 1)} onOpenEvent={(id) => navigate(`/events/${id}`)} />

          {analyticsState.status === 'loading' && <LoadingState label="Loading your safety overview…" />}
          {analyticsState.status === 'error' && (
            <ErrorState title="Could not load your safety overview" description={analyticsState.message} onRetry={() => setReloadToken((token) => token + 1)} />
          )}
          {analyticsState.status === 'success' && <HomeSummary summary={analyticsState.data} />}
        </>
      )}
    </PageContainer>
  );
}

function EnterpriseRiskSection({
  state,
  onRetry,
}: {
  state: AsyncState<EnterpriseIntelligence>;
  onRetry: () => void;
}) {
  return (
    <Section title="Enterprise risk" description="The organization's current deterministic risk position.">
      {state.status === 'loading' && <LoadingState label="Loading enterprise risk…" />}
      {state.status === 'error' && <ErrorState description={state.message} onRetry={onRetry} />}
      {state.status === 'success' && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="rounded-lg border border-border bg-surface p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Risk score</p>
            <p className="mt-1 text-2xl font-semibold text-text-primary">
              {state.data.deterministic_risk.score !== null ? state.data.deterministic_risk.score.toFixed(1) : '—'}
            </p>
          </div>
          <div className="rounded-lg border border-border bg-surface p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Risk classification</p>
            <div className="mt-1.5">
              <StatusBadge tone={riskClassificationTone(state.data.deterministic_risk.classification)} label={riskClassificationLabel(state.data.deterministic_risk.classification)} />
            </div>
          </div>
          <div className="rounded-lg border border-border bg-surface p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Data sufficiency</p>
            <div className="mt-1.5">
              <StatusBadge tone={dataSufficiencyTone(state.data.data_sufficiency.status)} label={dataSufficiencyLabel(state.data.data_sufficiency.status)} />
            </div>
          </div>
        </div>
      )}
    </Section>
  );
}

function WhatIsChangingSection({ state }: { state: AsyncState<EnterpriseIntelligence> }) {
  if (state.status !== 'success') return null;
  const { anomalies } = state.data;

  return (
    <Section title="What is changing" description="Metrics compared against their own recent baseline — a deviation, not a conclusion about risk.">
      {anomalies.length === 0 ? (
        <EmptyState title="No baseline comparisons available" description="No metrics had enough history for a baseline comparison in the current window." />
      ) : (
        <ul className="flex flex-col gap-2">
          {anomalies.map((anomaly) => (
            <li key={anomaly.metric} className="flex items-center justify-between gap-3 rounded-lg border border-border bg-surface p-3.5">
              <p className="text-sm font-medium text-text-primary">{anomaly.label}</p>
              <StatusBadge
                tone={anomalyStatusTone(anomaly.status)}
                label={anomaly.status === 'ANOMALOUS' ? anomalyDirectionLabel(anomaly.direction) : anomalyStatusLabel(anomaly.status)}
              />
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

function NeedsAttentionSection({ state }: { state: AsyncState<EnterpriseIntelligence> }) {
  if (state.status !== 'success') return null;
  const { actions_context, anomalies, patterns } = state.data;
  const anomalousCount = anomalies.filter((a) => a.status === 'ANOMALOUS').length;
  const recurringCount = patterns.filter((p) => p.classification === 'RECURRING' || p.classification === 'HIGH_RECURRENCE').length;

  const tiles: { label: string; value: number }[] = [];
  if (actions_context) {
    tiles.push({ label: 'Open actions', value: actions_context.open_action_count });
    tiles.push({ label: 'High-priority actions', value: actions_context.high_priority_action_count });
  }
  tiles.push({ label: 'Anomalous indicators', value: anomalousCount });
  tiles.push({ label: 'Recurring patterns', value: recurringCount });

  return (
    <Section title="Needs attention" description="Deterministic counts from actions and intelligence — nothing inferred beyond what is shown.">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {tiles.map((tile) => (
          <div key={tile.label} className="rounded-lg border border-border bg-surface p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-text-muted">{tile.label}</p>
            <p className="mt-1 text-2xl font-semibold text-text-primary">{tile.value}</p>
          </div>
        ))}
      </div>
    </Section>
  );
}

function RecentEventsSection({
  state,
  onRetry,
  onOpenEvent,
}: {
  state: AsyncState<EventSummaryResponse[]>;
  onRetry: () => void;
  onOpenEvent: (eventId: string) => void;
}) {
  return (
    <Section title="Recent events" description="The most recently recorded safety events.">
      {state.status === 'loading' && <LoadingState label="Loading recent events…" />}
      {state.status === 'error' && <ErrorState description={state.message} onRetry={onRetry} />}
      {state.status === 'success' && state.data.length === 0 && (
        <EmptyState title="No events recorded yet" description="No safety events have been recorded for this organization." />
      )}
      {state.status === 'success' && state.data.length > 0 && (
        <ul className="flex flex-col gap-2">
          {state.data.map((event) => (
            <li key={event.id}>
              <button
                type="button"
                onClick={() => onOpenEvent(event.id)}
                className="flex w-full items-center justify-between gap-3 rounded-lg border border-border bg-surface p-3.5 text-left transition-colors hover:bg-surface-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600"
              >
                <div>
                  <p className="text-sm font-medium text-text-primary">
                    {formatCanonicalLabel(event.event_type)}
                    {event.event_subtype ? ` · ${formatCanonicalLabel(event.event_subtype)}` : ''}
                  </p>
                  <p className="mt-0.5 text-xs text-text-muted">
                    {new Date(event.event_time).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}
                    {event.site_name ? ` · ${event.site_name}` : ''}
                  </p>
                </div>
                <StatusBadge tone={eventStatusTone(event.status ?? 'Unspecified')} label={eventStatusLabel(event.status ?? 'Unspecified')} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

function HomeSummary({ summary }: { summary: AnalyticsSummary }) {
  return (
    <>
      <Section title="At a glance" description={`Based on the last ${summary.window_days} days.`}>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="rounded-lg border border-border bg-surface p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Recorded events</p>
            <p className="mt-1 text-2xl font-semibold text-text-primary">{summary.event_count}</p>
          </div>
          <div className="rounded-lg border border-border bg-surface p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Data sufficiency</p>
            <div className="mt-1.5">
              <StatusBadge
                tone={SUFFICIENCY_TONE[summary.data_sufficiency] ?? 'neutral'}
                label={SUFFICIENCY_LABEL[summary.data_sufficiency] ?? summary.data_sufficiency}
              />
            </div>
          </div>
          <div className="rounded-lg border border-border bg-surface p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Current signals</p>
            <p className="mt-1 text-2xl font-semibold text-text-primary">{summary.signals.length}</p>
          </div>
        </div>
      </Section>

      <Section title="Signals requiring attention" description="Deterministic signals computed from your organization's recorded events.">
        {summary.signals.length === 0 ? (
          <EmptyState title="No signals at this time" description="Nothing in the current window has crossed a signal threshold." />
        ) : (
          <ul className="flex flex-col gap-2">
            {summary.signals.map((signal, index) => (
              <li key={`${signal.signal_type}-${index}`} className="flex items-center justify-between gap-3 rounded-lg border border-border bg-surface p-3.5">
                <div>
                  <p className="text-sm font-medium text-text-primary">{signalDescription(signal)}</p>
                  <p className="mt-0.5 text-xs text-text-muted">
                    {new Date(signal.observed_period_start).toLocaleDateString()} – {new Date(signal.observed_period_end).toLocaleDateString()}
                  </p>
                </div>
                <StatusBadge tone={SEVERITY_TONE[signal.severity] ?? 'neutral'} label={SEVERITY_LABEL[signal.severity] ?? signal.severity} />
              </li>
            ))}
          </ul>
        )}
      </Section>

      {summary.indicators.length > 0 && (
        <Section title="Key indicators">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {summary.indicators.map((indicator) => (
              <div key={indicator.name} className="rounded-lg border border-border bg-surface p-3.5">
                <p className="text-xs font-medium uppercase tracking-wide text-text-muted">{indicator.category}</p>
                <p className="mt-0.5 text-sm font-medium text-text-primary">{indicator.name.replaceAll('_', ' ')}</p>
                <p className="mt-1 text-lg font-semibold text-text-primary">
                  {indicator.feature.value ?? '—'}
                </p>
              </div>
            ))}
          </div>
        </Section>
      )}
    </>
  );
}
