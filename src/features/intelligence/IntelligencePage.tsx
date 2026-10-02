import { useEffect, useMemo, useState } from 'react';
import { Info } from 'lucide-react';
import { useAuth } from '../../auth/AuthContext';
import { PageContainer } from '../../components/layout/PageContainer';
import { Section } from '../../components/layout/Section';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { LoadingState } from '../../components/ui/LoadingState';
import { Select } from '../../components/ui/Select';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { Tabs } from '../../components/ui/Tabs';
import type { AttentionItem, AttentionResult } from '../../services/api/attention';
import { getAttention, getSiteAttention } from '../../services/api/attention';
import type { IntelligenceDecision } from '../../services/api/decisions';
import { listDecisions } from '../../services/api/decisions';
import type { FieldIntelligenceContext } from '../../services/api/fieldIntelligenceContext';
import { getFieldIntelligenceContext, getSiteFieldIntelligenceContext } from '../../services/api/fieldIntelligenceContext';
import { listSites, type Site } from '../../services/api/sites';
import type { AsyncState } from '../../types/common';
import { formatCanonicalLabel } from '../events/eventStatus';
import { AttentionList } from './AttentionList';
import { AttentionReviewDrawer } from './AttentionReviewDrawer';
import { DecisionHistorySection } from './DecisionHistorySection';
import { OrganizationalMemoryCard } from './OrganizationalMemoryCard';
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

const DETAIL_TABS = [
  { value: 'indicators', label: 'Indicators' },
  { value: 'anomalies', label: 'Anomalies' },
  { value: 'patterns', label: 'Patterns' },
  { value: 'associations', label: 'Associations' },
];

/**
 * Intelligence — SIE Milestone 42's primary intelligence workspace.
 * Follows the information hierarchy the milestone spec requires:
 *
 *   Current operational state -> Attention -> Intelligence context -> Decisions
 *
 * Three real, already-built backend read endpoints, called once each
 * per scope: `GET /intelligence/context` (SIE Milestone 32/41A — five
 * independent, never-merged categories), `GET /intelligence/attention`
 * (SIE Milestone 33 — the actual ranked prioritization the backend
 * already computed, rendered in the order it was returned), and
 * `GET /intelligence/decisions` (SIE Milestone 34 — recorded human
 * decisions). No calculation, ranking, or applicability judgment is
 * reproduced in this file.
 *
 * A "Scope" selector switches the whole workspace to one site's own
 * scope — this is the one place Predictive intelligence becomes
 * genuinely available (`PredictiveContext` is site-scoped only; see
 * `services/api/fieldIntelligenceContext.ts`'s own note), and attention
 * items narrow to that site specifically.
 */
export function IntelligencePage() {
  const auth = useAuth();
  const [siteId, setSiteId] = useState<string>('');
  const [sites, setSites] = useState<Site[]>([]);
  const [attentionState, setAttentionState] = useState<AsyncState<AttentionResult>>({ status: 'loading' });
  const [contextState, setContextState] = useState<AsyncState<FieldIntelligenceContext>>({ status: 'loading' });
  const [decisionsState, setDecisionsState] = useState<AsyncState<IntelligenceDecision[]>>({ status: 'loading' });
  const [reloadToken, setReloadToken] = useState(0);
  const [decisionRefreshToken, setDecisionRefreshToken] = useState(0);
  const [detailTab, setDetailTab] = useState('indicators');
  const [reviewItem, setReviewItem] = useState<AttentionItem | null>(null);

  useEffect(() => {
    if (!auth.organization) return;
    let cancelled = false;
    listSites(auth.organization.id).then((result) => {
      if (!cancelled) setSites(result);
    });
    return () => {
      cancelled = true;
    };
  }, [auth.organization]);

  useEffect(() => {
    if (!auth.organization) return;
    const controller = new AbortController();
    setAttentionState({ status: 'loading' });
    const request = siteId
      ? getSiteAttention({ organizationId: auth.organization.id, siteId }, controller.signal)
      : getAttention({ organizationId: auth.organization.id }, controller.signal);
    request
      .then((result) => setAttentionState({ status: 'success', data: result }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setAttentionState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load attention.' });
      });
    return () => controller.abort();
  }, [auth.organization, siteId, reloadToken]);

  useEffect(() => {
    if (!auth.organization) return;
    const controller = new AbortController();
    setContextState({ status: 'loading' });
    const request = siteId
      ? getSiteFieldIntelligenceContext({ organizationId: auth.organization.id, siteId }, controller.signal)
      : getFieldIntelligenceContext({ organizationId: auth.organization.id }, controller.signal);
    request
      .then((result) => setContextState({ status: 'success', data: result }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setContextState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load intelligence context.' });
      });
    return () => controller.abort();
  }, [auth.organization, siteId, reloadToken]);

  // Recent decisions, fetched org-wide (not site-filtered) so the
  // "already decided" annotation on the attention list stays correct
  // regardless of which scope is currently selected.
  useEffect(() => {
    if (!auth.organization) return;
    const controller = new AbortController();
    setDecisionsState({ status: 'loading' });
    listDecisions({ organizationId: auth.organization.id, pageSize: 100 }, controller.signal)
      .then((result) => setDecisionsState({ status: 'success', data: result.items }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setDecisionsState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load decisions.' });
      });
    return () => controller.abort();
  }, [auth.organization, decisionRefreshToken]);

  // Correlates two already-fetched, real datasets by the one key the
  // backend defines for exactly this purpose (`attention_reference`) —
  // never a frontend-invented ranking or applicability judgment.
  const decisionsByReference = useMemo(() => {
    const map = new Map<string, IntelligenceDecision>();
    if (decisionsState.status !== 'success') return map;
    for (const record of decisionsState.data) {
      if (!map.has(record.attention_reference)) {
        map.set(record.attention_reference, record); // newest first already
      }
    }
    return map;
  }, [decisionsState]);

  const isPermissionDenied =
    attentionState.status === 'error' &&
    attentionState.message.toLowerCase().includes('missing') &&
    attentionState.message.toLowerCase().includes('permission');

  return (
    <PageContainer>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-navy-900">Intelligence</h1>
          <p className="mt-1 text-sm text-text-secondary">
            What SIE currently knows, what deserves attention, and the decisions recorded against it.
          </p>
        </div>
        {sites.length > 0 && (
          <div className="w-56">
            <Select
              label="Scope"
              hideLabel
              value={siteId}
              onChange={(event) => setSiteId(event.target.value)}
              options={[{ value: '', label: 'Organization-wide' }, ...sites.map((site) => ({ value: site.id, label: site.name }))]}
            />
          </div>
        )}
      </div>

      {!auth.organization && (
        <EmptyState
          title="No organization context available"
          description="A development identity is not configured, or it could not be resolved against the backend. See docs/FRONTEND_ARCHITECTURE.md for setup."
        />
      )}

      {auth.organization && isPermissionDenied && (
        <EmptyState title="You don't have permission to view this" description="Ask an administrator for intelligence:read access in this organization." />
      )}

      {auth.organization && !isPermissionDenied && (
        <>
          <CurrentOperationalStateSection state={contextState} onRetry={() => setReloadToken((t) => t + 1)} />

          <Section title="Attention" description="What deserves attention first, in the order SIE's own ranking already determined.">
            {attentionState.status === 'loading' && <LoadingState label="Loading attention…" />}
            {attentionState.status === 'error' && (
              <ErrorState description={attentionState.message} onRetry={() => setReloadToken((t) => t + 1)} />
            )}
            {attentionState.status === 'success' && (
              <AttentionList
                items={attentionState.data.items}
                decisionsByReference={decisionsByReference}
                onReview={setReviewItem}
              />
            )}
          </Section>

          <IntelligenceContextSection
            state={contextState}
            onRetry={() => setReloadToken((t) => t + 1)}
            detailTab={detailTab}
            onDetailTabChange={setDetailTab}
          />

          <DecisionHistorySection organizationId={auth.organization.id} refreshToken={decisionRefreshToken} />
        </>
      )}

      {auth.organization && (
        <AttentionReviewDrawer
          isOpen={reviewItem !== null}
          onClose={() => setReviewItem(null)}
          item={reviewItem}
          organizationId={auth.organization.id}
          onDecided={() => setDecisionRefreshToken((t) => t + 1)}
        />
      )}
    </PageContainer>
  );
}

/**
 * Current operational state — SIE Milestone 42 correction. A concise
 * orientation layer, not a dashboard: "what is the current operational
 * state before I decide what deserves my attention?"
 *
 * Reuses the exact `FieldIntelligenceContext` already fetched for the
 * Intelligence Context section below (no new endpoint, no new
 * calculation, no duplicate fetch) and renders only the handful of
 * fields that answer that orientation question. Observed, deterministic,
 * and predictive values are kept visibly distinct — never merged into
 * one artificial score. Unavailable values are stated honestly, never
 * substituted with zero or a fabricated figure. This section has its own
 * loading/error state (mirroring `contextState`) so a failure here never
 * blocks Attention or the other Intelligence Context panels from
 * rendering independently.
 */
function CurrentOperationalStateSection({
  state,
  onRetry,
}: {
  state: AsyncState<FieldIntelligenceContext>;
  onRetry: () => void;
}) {
  return (
    <Section
      title="Current operational state"
      description="A brief orientation to what SIE currently observes — not a conclusion or an automated decision. See Attention below for what needs a human decision."
    >
      {state.status === 'loading' && <LoadingState label="Loading current operational state…" />}
      {state.status === 'error' && <ErrorState description={state.message} onRetry={onRetry} />}
      {state.status === 'success' && <OperationalStateSummary context={state.data} />}
    </Section>
  );
}

function OperationalStateSummary({ context }: { context: FieldIntelligenceContext }) {
  const { observed, deterministic: det, predictive, operational_scope } = context;
  const scopeLabel = operational_scope?.level === 'SITE' && operational_scope.site ? operational_scope.site.name : 'Organization-wide';

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Scope: {scopeLabel}</p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-lg border border-border bg-surface p-3.5">
          <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Deterministic risk</p>
          {det.deterministic_risk.score !== null ? (
            <>
              <p className="mt-1 text-xl font-semibold text-text-primary">{det.deterministic_risk.score.toFixed(1)}</p>
              <div className="mt-1.5">
                <StatusBadge tone={riskClassificationTone(det.deterministic_risk.classification)} label={riskClassificationLabel(det.deterministic_risk.classification)} />
              </div>
            </>
          ) : (
            <p className="mt-1 text-sm text-text-muted">
              Not available{det.deterministic_risk.insufficient_data_reason ? ` — ${det.deterministic_risk.insufficient_data_reason}` : '.'}
            </p>
          )}
        </div>

        <div className="rounded-lg border border-border bg-surface p-3.5">
          <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Data sufficiency</p>
          <div className="mt-1.5">
            <StatusBadge tone={dataSufficiencyTone(det.data_sufficiency.status)} label={dataSufficiencyLabel(det.data_sufficiency.status)} />
          </div>
        </div>

        <div className="rounded-lg border border-border bg-surface p-3.5">
          <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Observed activity</p>
          {observed.outcome === 'UNAVAILABLE' ? (
            <p className="mt-1 text-sm text-text-muted">Unavailable{observed.unavailable_reason ? `: ${observed.unavailable_reason}` : '.'}</p>
          ) : (
            <p className="mt-1 text-sm text-text-primary">
              {observed.event_count} event{observed.event_count === 1 ? '' : 's'} recorded
              {' · '}
              {observed.open_finding_count} open finding{observed.open_finding_count === 1 ? '' : 's'}
              {observed.actions
                ? ` · ${observed.actions.open_action_count} open action${observed.actions.open_action_count === 1 ? '' : 's'}`
                : ''}
            </p>
          )}
        </div>

        <div className="rounded-lg border border-border bg-surface p-3.5">
          <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Predictive intelligence</p>
          {predictive.outcome === 'AVAILABLE' && predictive.value ? (
            <p className="mt-1 text-sm text-text-primary">
              Model-derived: {predictive.value.risk_category ?? (predictive.value.risk_score !== null ? `score ${predictive.value.risk_score}` : 'available')}
            </p>
          ) : predictive.outcome === 'EXCLUDED_GENERATED_AFTER_AS_OF' ? (
            <p className="mt-1 text-sm text-text-muted">Withheld — generated after this view's cutoff.</p>
          ) : context.entity_id ? (
            <p className="mt-1 text-sm text-text-muted">Not available for this site yet.</p>
          ) : (
            <p className="mt-1 text-sm text-text-muted">Not available at organization scope — select a site above.</p>
          )}
        </div>
      </div>
    </div>
  );
}

function IntelligenceContextSection({
  state,
  onRetry,
  detailTab,
  onDetailTabChange,
}: {
  state: AsyncState<FieldIntelligenceContext>;
  onRetry: () => void;
  detailTab: string;
  onDetailTabChange: (value: string) => void;
}) {
  return (
    <Section title="Intelligence context" description="Five independent categories — never merged into one undifferentiated feed.">
      {state.status === 'loading' && <LoadingState label="Loading intelligence context…" />}
      {state.status === 'error' && <ErrorState description={state.message} onRetry={onRetry} />}
      {state.status === 'success' && (
        <div className="flex flex-col gap-6">
          <ObservedPanel context={state.data} />
          <DeterministicPanel context={state.data} detailTab={detailTab} onDetailTabChange={onDetailTabChange} />
          <PredictivePanel context={state.data} />
          <KnowledgePanel context={state.data} />
          <OrganizationalMemoryPanel context={state.data} />
        </div>
      )}
    </Section>
  );
}

function CategoryHeading({ label }: { label: string }) {
  return <h3 className="text-xs font-semibold uppercase tracking-wide text-text-muted">{label}</h3>;
}

function ObservedPanel({ context }: { context: FieldIntelligenceContext }) {
  const { observed } = context;
  return (
    <div>
      <CategoryHeading label="Observed — what has actually happened" />
      {observed.outcome === 'UNAVAILABLE' ? (
        <p className="mt-2 text-sm text-text-muted">Observed data is unavailable{observed.unavailable_reason ? `: ${observed.unavailable_reason}` : '.'}</p>
      ) : (
        <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-lg border border-border bg-surface p-3.5">
            <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Recorded events</p>
            <p className="mt-1 text-xl font-semibold text-text-primary">{observed.event_count}</p>
          </div>
          <div className="rounded-lg border border-border bg-surface p-3.5">
            <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Open findings</p>
            <p className="mt-1 text-xl font-semibold text-text-primary">{observed.open_finding_count}</p>
          </div>
          {observed.actions && (
            <>
              <div className="rounded-lg border border-border bg-surface p-3.5">
                <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Open actions</p>
                <p className="mt-1 text-xl font-semibold text-text-primary">{observed.actions.open_action_count}</p>
              </div>
              <div className="rounded-lg border border-border bg-surface p-3.5">
                <p className="text-xs font-medium uppercase tracking-wide text-text-muted">High-priority actions</p>
                <p className="mt-1 text-xl font-semibold text-text-primary">{observed.actions.high_priority_action_count}</p>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function DeterministicPanel({
  context,
  detailTab,
  onDetailTabChange,
}: {
  context: FieldIntelligenceContext;
  detailTab: string;
  onDetailTabChange: (value: string) => void;
}) {
  const det = context.deterministic;
  return (
    <div>
      <CategoryHeading label="Deterministic — patterns, trends, and risk computed from recorded events" />
      <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="rounded-lg border border-border bg-surface p-4 shadow-xs">
          <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Risk score</p>
          <p className="mt-1 text-2xl font-semibold text-text-primary">
            {det.deterministic_risk.score !== null ? det.deterministic_risk.score.toFixed(1) : '—'}
          </p>
        </div>
        <div className="rounded-lg border border-border bg-surface p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Risk classification</p>
          <div className="mt-1.5">
            <StatusBadge tone={riskClassificationTone(det.deterministic_risk.classification)} label={riskClassificationLabel(det.deterministic_risk.classification)} />
          </div>
        </div>
        <div className="rounded-lg border border-border bg-surface p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Data sufficiency</p>
          <div className="mt-1.5">
            <StatusBadge tone={dataSufficiencyTone(det.data_sufficiency.status)} label={dataSufficiencyLabel(det.data_sufficiency.status)} />
          </div>
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between gap-3 rounded-lg border border-border bg-surface p-4">
        <p className="text-sm text-text-primary">
          {det.trend.current_value} recorded, compared with {det.trend.previous_value} in the prior period
          {det.trend.percentage_change !== null ? ` (${det.trend.percentage_change > 0 ? '+' : ''}${det.trend.percentage_change.toFixed(1)}%)` : ''}.
        </p>
        <StatusBadge tone={trendTone(det.trend.classification)} label={trendLabel(det.trend.classification)} />
      </div>

      <Tabs items={DETAIL_TABS} value={detailTab} onChange={onDetailTabChange} className="mt-4" />
      {detailTab === 'indicators' && <IndicatorsPanel det={det} />}
      {detailTab === 'anomalies' && <AnomaliesPanel det={det} />}
      {detailTab === 'patterns' && <PatternsPanel det={det} />}
      {detailTab === 'associations' && <AssociationsPanel det={det} />}
    </div>
  );
}

function IndicatorsPanel({ det }: { det: FieldIntelligenceContext['deterministic'] }) {
  if (det.indicators.length === 0) {
    return <EmptyState title="No indicators available" description="No indicator values were computed for the current window." />;
  }
  return (
    <ul className="mt-3 flex flex-col gap-2">
      {det.indicators.map((indicator) => (
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

function AnomaliesPanel({ det }: { det: FieldIntelligenceContext['deterministic'] }) {
  if (det.anomalies.length === 0) {
    return <EmptyState title="No anomaly data available" description="No anomaly scan results were computed for the current window." />;
  }
  return (
    <ul className="mt-3 flex flex-col gap-2">
      {det.anomalies.map((anomaly) => (
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

function PatternsPanel({ det }: { det: FieldIntelligenceContext['deterministic'] }) {
  if (det.patterns.length === 0) {
    return <EmptyState title="No recurring patterns" description="No recurring event patterns were detected for the current window." />;
  }
  return (
    <ul className="mt-3 flex flex-col gap-2">
      {det.patterns.map((pattern) => (
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

function AssociationsPanel({ det }: { det: FieldIntelligenceContext['deterministic'] }) {
  if (det.associations.length === 0) {
    return <EmptyState title="No associations available" description="No metric associations were computed for the current window." />;
  }
  return (
    <ul className="mt-3 flex flex-col gap-2">
      {det.associations.map((association) => (
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

function PredictivePanel({ context }: { context: FieldIntelligenceContext }) {
  const { predictive } = context;
  return (
    <div>
      <CategoryHeading label="Predictive — model-derived signal" />
      {predictive.outcome === 'NOT_AVAILABLE' && (
        <p className="mt-2 flex items-start gap-1.5 text-sm text-text-muted">
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          {context.entity_id
            ? 'No prediction has been recorded for this site yet.'
            : 'Predictive intelligence is evaluated per site — choose a site above to view it.'}
        </p>
      )}
      {predictive.outcome === 'EXCLUDED_GENERATED_AFTER_AS_OF' && (
        <p className="mt-2 flex items-start gap-1.5 text-sm text-text-muted">
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          A prediction exists but was generated after this view's cutoff — withheld to avoid presenting it as
          contemporaneous.
        </p>
      )}
      {predictive.outcome === 'AVAILABLE' && predictive.value && (
        <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="rounded-lg border border-border bg-surface p-3.5">
            <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Model-derived risk score</p>
            <p className="mt-1 text-xl font-semibold text-text-primary">{predictive.value.risk_score ?? '—'}</p>
          </div>
          <div className="rounded-lg border border-border bg-surface p-3.5">
            <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Risk category</p>
            <p className="mt-1 text-sm text-text-primary">{predictive.value.risk_category ?? 'Not available'}</p>
          </div>
          <div className="rounded-lg border border-border bg-surface p-3.5">
            <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Model version</p>
            <p className="mt-1 text-sm text-text-primary">{predictive.value.model_version ?? 'Not available'}</p>
          </div>
        </div>
      )}
    </div>
  );
}

function KnowledgePanel({ context }: { context: FieldIntelligenceContext }) {
  const { knowledge } = context;
  return (
    <div>
      <CategoryHeading label="Knowledge — retrieved organizational and documentary evidence" />
      {knowledge.outcome === 'NOT_QUERIED' && (
        <p className="mt-2 flex items-start gap-1.5 text-sm text-text-muted">
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          Knowledge and evidence retrieval has not been queried for this view.
        </p>
      )}
      {knowledge.outcome === 'UNAVAILABLE' && (
        <p className="mt-2 flex items-start gap-1.5 text-sm text-text-muted">
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          Knowledge retrieval is unavailable{knowledge.unavailable_reason ? `: ${knowledge.unavailable_reason}` : '.'}
        </p>
      )}
      {knowledge.outcome === 'NO_RELEVANT_EVIDENCE' && (
        <p className="mt-2 flex items-start gap-1.5 text-sm text-text-muted">
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          No relevant evidence was found for this query.
        </p>
      )}
      {knowledge.outcome === 'RESULTS' && (
        <ul className="mt-2 flex flex-col gap-2">
          {knowledge.results.map((result) => (
            <li key={result.rank} className="rounded-lg border border-border bg-surface p-3.5">
              <p className="text-sm text-text-primary">{result.content}</p>
              <p className="mt-1 text-xs text-text-muted">
                {result.document} · {result.source}
                {result.location ? ` · ${result.location}` : ''}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function OrganizationalMemoryPanel({ context }: { context: FieldIntelligenceContext }) {
  const { organizational_memory: memory } = context;
  return (
    <div>
      <CategoryHeading label="Organizational memory — governed knowledge from past learning" />
      {memory.outcome === 'UNAVAILABLE' && (
        <p className="mt-2 flex items-start gap-1.5 text-sm text-text-muted">
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          Organizational memory is unavailable{memory.unavailable_reason ? `: ${memory.unavailable_reason}` : '.'}
        </p>
      )}
      {memory.outcome === 'OK' && memory.items.length === 0 && (
        <p className="mt-2 flex items-start gap-1.5 text-sm text-text-muted">
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          No governed organizational memory applies to this scope right now.
        </p>
      )}
      {memory.outcome === 'OK' && memory.items.length > 0 && (
        <div className="mt-2 flex flex-col gap-2">
          {memory.items.map((item) => (
            <OrganizationalMemoryCard key={item.memory_id} memory={item} />
          ))}
        </div>
      )}
    </div>
  );
}
