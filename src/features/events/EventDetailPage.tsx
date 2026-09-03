import { Info } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Breadcrumb } from '../../components/layout/Breadcrumb';
import { PageContainer } from '../../components/layout/PageContainer';
import { Section } from '../../components/layout/Section';
import { DocumentReference } from '../../components/data/DocumentReference';
import { RelatedRecord } from '../../components/data/RelatedRecord';
import { InsightPanel } from '../../components/intelligence/InsightPanel';
import { Button } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { LoadingState } from '../../components/ui/LoadingState';
import { StatusBadge } from '../../components/ui/StatusBadge';
import type { AsyncState } from '../../types/common';
import type { EventStatus, SafetyEventDetail } from '../../types/events';
import { useEventRepository } from './useEventRepository';

const STATUS_TONE: Record<EventStatus, 'success' | 'warning' | 'informational' | 'neutral'> = {
  open: 'informational',
  under_review: 'warning',
  closed: 'success',
  quarantined: 'neutral',
};

const STATUS_LABEL: Record<EventStatus, string> = {
  open: 'Open',
  under_review: 'Under review',
  closed: 'Closed',
  quarantined: 'Quarantined',
};

/**
 * Event Detail — "What exactly happened, and what evidence supports it?"
 *
 * Same fixture-backed data source as Events (§15) — see
 * `useEventRepository.ts`. The "What SIE found" section uses
 * `InsightPanel`, which shows an "insufficient evidence" state rather
 * than a fabricated conclusion whenever a fixture event has no
 * associated finding (most of them — see `src/fixtures/events.ts`'s own
 * `DETAIL_OVERRIDES`).
 */
export function EventDetailPage() {
  const { eventId } = useParams<{ eventId: string }>();
  const repository = useEventRepository();
  const navigate = useNavigate();
  const [state, setState] = useState<AsyncState<SafetyEventDetail | null>>({ status: 'loading' });
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    if (!eventId) return;
    let cancelled = false;
    setState({ status: 'loading' });
    repository
      .getById(eventId)
      .then((detail) => {
        if (!cancelled) setState({ status: 'success', data: detail });
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load this event.' });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [repository, eventId, reloadToken]);

  return (
    <PageContainer>
      <Breadcrumb items={[{ label: 'Events', href: '/events' }, { label: eventId ?? 'Event' }]} />

      <div className="flex items-start gap-2 rounded-md border border-informational/30 bg-informational-surface px-3 py-2.5 text-sm text-informational">
        <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <p>Showing example event data — see the Events page for details on this limitation.</p>
      </div>

      {state.status === 'loading' && <LoadingState label="Loading event…" />}

      {state.status === 'error' && (
        <ErrorState description={state.message} onRetry={() => setReloadToken((token) => token + 1)} />
      )}

      {state.status === 'success' && state.data === null && (
        <EmptyState
          title="Event not found"
          description="This event may have been removed, or the link may be incorrect."
          action={
            <Button variant="secondary" size="sm" onClick={() => navigate('/events')}>
              Back to Events
            </Button>
          }
        />
      )}

      {state.status === 'success' && state.data && <EventDetailContent event={state.data} />}
    </PageContainer>
  );
}

function EventDetailContent({ event }: { event: SafetyEventDetail }) {
  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-text-primary">{event.title}</h1>
          <p className="mt-1 text-sm text-text-secondary">
            {new Date(event.date).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' })} · {event.site}
          </p>
        </div>
        <StatusBadge tone={STATUS_TONE[event.status]} label={STATUS_LABEL[event.status]} />
      </div>

      <Section title="Classification">
        <dl className="grid grid-cols-2 gap-4 rounded-lg border border-border bg-surface p-4 sm:grid-cols-4">
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-text-muted">Event type</dt>
            <dd className="mt-0.5 text-sm text-text-primary">{event.eventType}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-text-muted">Subtype</dt>
            <dd className="mt-0.5 text-sm text-text-primary">{event.subtype ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-text-muted">Source</dt>
            <dd className="mt-0.5 text-sm text-text-primary">{event.sourceSystem}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-text-muted">Event ID</dt>
            <dd className="mt-0.5 font-mono text-sm text-text-primary">{event.id}</dd>
          </div>
        </dl>
      </Section>

      <Section title="Source narrative">
        <p className="rounded-lg border border-border bg-surface p-4 text-sm leading-relaxed text-text-primary">
          {event.narrative}
        </p>
      </Section>

      <Section title="What SIE found">
        <InsightPanel heading="Finding" finding={event.finding} context={event.findingContext} evidence={event.evidence} />
      </Section>

      {event.relatedRecords.length > 0 && (
        <Section title="Related records">
          <div className="flex flex-col gap-2">
            {event.relatedRecords.map((record) => (
              <RelatedRecord key={record.id} record={record} />
            ))}
          </div>
        </Section>
      )}

      {event.relevantKnowledge.length > 0 && (
        <Section title="Relevant knowledge">
          <div className="flex flex-col gap-2">
            {event.relevantKnowledge.map((doc) => (
              <DocumentReference key={doc.id} document={doc} />
            ))}
          </div>
        </Section>
      )}
    </>
  );
}
