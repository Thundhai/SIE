import { useEffect, useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { PageContainer } from '../../components/layout/PageContainer';
import { Section } from '../../components/layout/Section';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { LoadingState } from '../../components/ui/LoadingState';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { getAnalyticsSummary, type AnalyticsSummary, type RiskSignal } from '../../services/api/analytics';
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
 * Home — "What needs my attention?" A calm overview of the
 * organization's current safety position, backed entirely by the real
 * `GET /intelligence/analytics/summary` endpoint (no fixture data — see
 * `docs/FRONTEND_ARCHITECTURE.md`). Deliberately restrained: no wall of
 * large KPI tiles, no invented "recent activity" feed (the backend has
 * no such endpoint — see §13's own instruction to omit rather than
 * fabricate).
 */
export function HomePage() {
  const auth = useAuth();
  const [state, setState] = useState<AsyncState<AnalyticsSummary>>({ status: 'loading' });
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    if (!auth.organization) return;
    const controller = new AbortController();
    setState({ status: 'loading' });
    getAnalyticsSummary({ organizationId: auth.organization.id }, controller.signal)
      .then((summary) => setState({ status: 'success', data: summary }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load analytics.' });
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

      {auth.organization && state.status === 'loading' && <LoadingState label="Loading your safety overview…" />}

      {auth.organization && state.status === 'error' && (
        <ErrorState
          title="Could not load your safety overview"
          description={state.message}
          onRetry={() => setReloadToken((token) => token + 1)}
        />
      )}

      {auth.organization && state.status === 'success' && <HomeSummary summary={state.data} />}
    </PageContainer>
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
