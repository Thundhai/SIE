import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { Section } from '../../components/layout/Section';
import { Button } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { LoadingState } from '../../components/ui/LoadingState';
import { PriorityBadge } from '../../components/ui/PriorityBadge';
import { StatusBadge } from '../../components/ui/StatusBadge';
import type { AsyncState } from '../../types/common';
import type { SafetyAction } from '../../types/actions';
import { ActionFormDrawer } from './ActionFormDrawer';
import { actionStatusLabel, actionStatusTone, toPriorityLevel } from './actionStatus';
import { useActionRepository } from './useActionRepository';

export interface RelatedActionSectionProps {
  sourceEventId: string;
}

/**
 * Event Detail's "Related action" area — SIE Milestone 18: Actions &
 * Intervention UX & API Integration v0.1, §8. Queries the real Actions
 * domain (`ActionRepository.list({ sourceEventId })`) for whichever
 * action, if any, was raised from this event — a genuinely separate
 * mechanism from `EventDetailContent`'s older, generic
 * `relatedRecords`/`RelatedRecord` display (fixture-illustrative,
 * unrelated to the Actions domain, left untouched by this milestone).
 * Renders exactly the real state: the one related action found, an
 * honest "none yet" empty state (with an optional, permission-gated
 * "Create action" entry point), or a genuine load error — never a
 * fabricated action or recommendation.
 */
export function RelatedActionSection({ sourceEventId }: RelatedActionSectionProps) {
  const repository = useActionRepository();
  const { hasPermission } = useAuth();
  const navigate = useNavigate();
  const canCreate = hasPermission('intervention:manage');

  const [state, setState] = useState<AsyncState<SafetyAction | null>>({ status: 'loading' });
  const [reloadToken, setReloadToken] = useState(0);
  const [isCreateOpen, setCreateOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setState({ status: 'loading' });
    repository
      .list({ page: 1, pageSize: 1, sourceEventId })
      .then((result) => {
        if (!cancelled) setState({ status: 'success', data: result.items[0] ?? null });
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({
            status: 'error',
            message: error instanceof Error ? error.message : 'Could not load the related action.',
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [repository, sourceEventId, reloadToken]);

  return (
    <Section title="Related action">
      {state.status === 'loading' && <LoadingState label="Checking for a related action…" />}

      {state.status === 'error' && (
        <ErrorState description={state.message} onRetry={() => setReloadToken((token) => token + 1)} />
      )}

      {state.status === 'success' && state.data && (
        <button
          type="button"
          onClick={() => navigate(`/actions/${state.data?.id}`)}
          className="flex w-full flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface p-4 text-left hover:bg-surface-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600"
        >
          <div>
            <p className="font-medium text-text-primary">{state.data.title}</p>
            <p className="text-xs text-text-muted">{state.data.ownerName ?? 'Unassigned'}</p>
          </div>
          <div className="flex items-center gap-2">
            <PriorityBadge priority={toPriorityLevel(state.data.priority)} />
            <StatusBadge tone={actionStatusTone(state.data.status)} label={actionStatusLabel(state.data.status)} />
          </div>
        </button>
      )}

      {state.status === 'success' && state.data === null && (
        <EmptyState
          title="No action has been raised for this event"
          description="Corrective or follow-up actions raised from this event will appear here."
          action={
            canCreate ? (
              <Button variant="secondary" size="sm" onClick={() => setCreateOpen(true)}>
                Create action
              </Button>
            ) : undefined
          }
        />
      )}

      <ActionFormDrawer
        isOpen={isCreateOpen}
        onClose={() => setCreateOpen(false)}
        mode="create"
        sourceEventId={sourceEventId}
        onSaved={() => setReloadToken((token) => token + 1)}
      />
    </Section>
  );
}
