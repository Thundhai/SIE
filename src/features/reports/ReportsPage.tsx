import { useEffect, useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { PageContainer } from '../../components/layout/PageContainer';
import { Section } from '../../components/layout/Section';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { LoadingState } from '../../components/ui/LoadingState';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { getEnterpriseIntelligence, type EnterpriseIntelligence } from '../../services/api/intelligence';
import { getAnalyticsSummary, type AnalyticsSummary } from '../../services/api/analytics';
import { listEvents, type EventSummaryResponse } from '../../services/api/events';
import { listActions, type ActionListResponse } from '../../services/api/actions';

export function ReportsPage() {
  const auth = useAuth();
  const [intelligence, setIntelligence] = useState<EnterpriseIntelligence | null>(null);
  const [analytics, setAnalytics] = useState<AnalyticsSummary | null>(null);
  const [events, setEvents] = useState<EventSummaryResponse[]>([]);
  const [actions, setActions] = useState<ActionListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const windowDays = 30;

  useEffect(() => {
    if (!auth.organization) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);

    Promise.all([
      getEnterpriseIntelligence({ organizationId: auth.organization.id, windowDays }, controller.signal),
      getAnalyticsSummary({ organizationId: auth.organization.id, windowDays }, controller.signal),
      listEvents({ organizationId: auth.organization.id, page: 1, pageSize: 100, signal: controller.signal }),
      listActions({ organizationId: auth.organization.id, page: 1, pageSize: 100 }),
    ])
      .then(([enterprise, summary, eventResult, actionResult]) => {
        setIntelligence(enterprise);
        setAnalytics(summary);
        setEvents(eventResult.items);
        setActions(actionResult);
      })
      .catch((requestError: unknown) => {
        if (controller.signal.aborted) return;
        setError(requestError instanceof Error ? requestError.message : 'Could not load report data.');
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [auth.organization]);

  if (!auth.organization) {
    return (
      <PageContainer>
        <h1 className="text-xl font-semibold text-navy-900">Reports</h1>
        <EmptyState title="No organization context available" description="A development identity is not configured, or it could not be resolved against the backend." />
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-navy-900">Reports</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Management view of recorded safety activity and deterministic intelligence for the organization.
          </p>
        </div>
        <div className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-text-secondary">
          Reporting window: last {windowDays} days
        </div>
      </div>

      {loading && <LoadingState label="Loading report data…" />}
      {error && !loading && <ErrorState title="Could not load report data" description={error} onRetry={() => window.location.reload()} />}

      {!loading && !error && intelligence && analytics && actions && (
        <>
          <Section title="Executive safety summary" description="This report is assembled from authoritative SIE backend responses. It does not recalculate risk in the browser.">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
              <Metric label="Risk score" value={intelligence.deterministic_risk.score === null ? '—' : intelligence.deterministic_risk.score.toFixed(1)} />
              <Metric label="Recorded events" value={analytics.event_count} />
              <Metric label="Open actions" value={intelligence.actions_context?.open_action_count ?? 0} />
              <Metric label="High-priority actions" value={intelligence.actions_context?.high_priority_action_count ?? 0} />
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg border border-border bg-surface p-4">
                <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Risk classification</p>
                <div className="mt-2"><StatusBadge tone={intelligence.deterministic_risk.classification === 'LOW' ? 'success' : 'warning'} label={intelligence.deterministic_risk.classification ?? 'Not available'} /></div>
              </div>
              <div className="rounded-lg border border-border bg-surface p-4">
                <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Data sufficiency</p>
                <div className="mt-2"><StatusBadge tone={intelligence.data_sufficiency.status === 'SUFFICIENT_DATA' ? 'success' : 'warning'} label={intelligence.data_sufficiency.status.replaceAll('_', ' ')} /></div>
              </div>
            </div>
          </Section>

          <Section title="What changed" description="Current-period enterprise intelligence compared with the backend's defined prior baseline.">
            <div className="grid gap-2">
              {intelligence.indicators.slice(0, 8).map((indicator) => (
                <div key={indicator.key} className="flex items-center justify-between gap-4 rounded-lg border border-border bg-surface p-3.5">
                  <div>
                    <p className="text-sm font-medium text-text-primary">{indicator.label}</p>
                    <p className="mt-0.5 text-xs text-text-muted">Current {indicator.value} · previous {indicator.previous_value}</p>
                  </div>
                  <span className="text-sm text-text-secondary">{indicator.percentage_change === null ? '—' : indicator.percentage_change.toFixed(1) + '%'}</span>
                </div>
              ))}
              {intelligence.indicators.length === 0 && <EmptyState title="No indicators available" description="The current reporting window did not produce enterprise indicators." />}
            </div>
          </Section>

          <Section title="Recurring patterns and anomalies" description="Deterministic intelligence findings from the current reporting window.">
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="rounded-lg border border-border bg-surface p-4">
                <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Recurring patterns</p>
                <p className="mt-1 text-2xl font-semibold text-text-primary">{intelligence.patterns.length}</p>
              </div>
              <div className="rounded-lg border border-border bg-surface p-4">
                <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Anomalies</p>
                <p className="mt-1 text-2xl font-semibold text-text-primary">{intelligence.anomalies.filter((item) => item.status === 'ANOMALOUS').length}</p>
              </div>
            </div>
            <div className="mt-3 grid gap-2">
              {intelligence.patterns.slice(0, 6).map((pattern) => (
                <div key={pattern.pattern_key} className="rounded-lg border border-border bg-surface p-3.5">
                  <p className="text-sm font-medium text-text-primary">{pattern.event_type.replaceAll('_', ' ')}</p>
                  <p className="mt-1 text-xs text-text-secondary">{pattern.site_label} · {pattern.count} occurrences · {pattern.classification.replaceAll('_', ' ')}</p>
                </div>
              ))}
            </div>
          </Section>

          <Section title="Recent safety activity" description="Recorded events in the reporting window.">
            {events.length === 0 ? (
              <EmptyState title="No events recorded" description="No safety events were returned for this reporting window." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[680px] text-left text-sm">
                  <thead><tr className="border-b border-border text-xs uppercase tracking-wide text-text-muted">
                    <th className="px-3 py-2">Date</th><th className="px-3 py-2">Event</th><th className="px-3 py-2">Site</th><th className="px-3 py-2">Status</th>
                  </tr></thead>
                  <tbody>
                    {events.slice(0, 20).map((event) => (
                      <tr key={event.id} className="border-b border-border">
                        <td className="px-3 py-3">{new Date(event.event_time).toLocaleDateString()}</td>
                        <td className="px-3 py-3">{event.event_type.replaceAll('_', ' ')}{event.event_subtype ? ' · ' + event.event_subtype.replaceAll('_', ' ') : ''}</td>
                        <td className="px-3 py-3">{event.site_name ?? '—'}</td>
                        <td className="px-3 py-3">{event.status ?? 'Unspecified'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>

          <Section title="Report provenance" description="Use these values when interpreting or exporting the report later.">
            <div className="grid gap-3 sm:grid-cols-3">
              <Metric label="As of" value={new Date(intelligence.as_of).toLocaleString()} />
              <Metric label="Events supporting intelligence" value={intelligence.provenance.event_count} />
              <Metric label="Generated" value={new Date(intelligence.provenance.generated_at).toLocaleString()} />
            </div>
          </Section>
        </>
      )}
    </PageContainer>
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
