import { Info } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { Breadcrumb } from '../../components/layout/Breadcrumb';
import { PageContainer } from '../../components/layout/PageContainer';
import { Section } from '../../components/layout/Section';
import { Button } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { Input } from '../../components/ui/Input';
import { LoadingState } from '../../components/ui/LoadingState';
import { PriorityBadge } from '../../components/ui/PriorityBadge';
import { Select } from '../../components/ui/Select';
import { StatusBadge } from '../../components/ui/StatusBadge';
import type { AsyncState } from '../../types/common';
import type { ActionStatus, SafetyAction } from '../../types/actions';
import { ActionFormDrawer } from './ActionFormDrawer';
import {
  ACTION_TERMINAL_STATUSES,
  actionStatusLabel,
  actionStatusTone,
  actionTypeLabel,
  suggestedNextStatuses,
  toPriorityLevel,
} from './actionStatus';
import type { ActionOption } from './actionRepository';
import { useActionRepository } from './useActionRepository';

function formatDateTime(value: string | null): string {
  if (!value) return '—';
  return new Date(value).toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function formatDate(value: string | null): string {
  if (!value) return '—';
  return new Date(value).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
}

/**
 * Action Detail — the single action's full record, its current status,
 * and the two explicit, separately-permissioned mutation workflows the
 * backend actually offers on top of it (a status change, and — where
 * permitted — reassignment). Same repository as Actions (§15) — see
 * `useActionRepository.ts`.
 */
export function ActionDetailPage() {
  const { actionId } = useParams<{ actionId: string }>();
  const repository = useActionRepository();
  const navigate = useNavigate();
  const [state, setState] = useState<AsyncState<SafetyAction | null>>({ status: 'loading' });
  const [reloadToken, setReloadToken] = useState(0);
  const [isEditOpen, setEditOpen] = useState(false);

  useEffect(() => {
    if (!actionId) return;
    let cancelled = false;
    setState({ status: 'loading' });
    repository
      .getById(actionId)
      .then((detail) => {
        if (!cancelled) setState({ status: 'success', data: detail });
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load this action.' });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [repository, actionId, reloadToken]);

  return (
    <PageContainer>
      <Breadcrumb
        items={[
          { label: 'Actions', href: '/actions' },
          // The real action title once it's loaded (already fetched for
          // this page — no extra API call) — never the raw actionId UUID
          // (SIE Milestone 18 corrective patch, §2C). "Action detail" is
          // an honest, neutral fallback while loading, on error, or if
          // the id doesn't resolve to a real action; the URL itself is
          // unchanged either way.
          { label: state.status === 'success' && state.data ? state.data.title : 'Action detail' },
        ]}
      />

      {repository.isFixtureBacked && (
        <div className="flex items-start gap-2 rounded-md border border-informational/30 bg-informational-surface px-3 py-2.5 text-sm text-informational">
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <p>Showing example action data — see the Actions page for details on this limitation.</p>
        </div>
      )}

      {state.status === 'loading' && <LoadingState label="Loading action…" />}

      {state.status === 'error' && (
        <ErrorState description={state.message} onRetry={() => setReloadToken((token) => token + 1)} />
      )}

      {state.status === 'success' && state.data === null && (
        <EmptyState
          title="Action not found"
          description="This action may have been removed, or the link may be incorrect."
          action={
            <Button variant="secondary" size="sm" onClick={() => navigate('/actions')}>
              Back to Actions
            </Button>
          }
        />
      )}

      {state.status === 'success' && state.data && (
        <ActionDetailContent
          action={state.data}
          onEdit={() => setEditOpen(true)}
          onChanged={(updated) => setState({ status: 'success', data: updated })}
        />
      )}

      {state.status === 'success' && state.data && (
        <ActionFormDrawer
          isOpen={isEditOpen}
          onClose={() => setEditOpen(false)}
          mode="edit"
          action={state.data}
          onSaved={(updated) => setState({ status: 'success', data: updated })}
        />
      )}
    </PageContainer>
  );
}

function ActionDetailContent({
  action,
  onEdit,
  onChanged,
}: {
  action: SafetyAction;
  onEdit: () => void;
  onChanged: (updated: SafetyAction) => void;
}) {
  const { hasPermission } = useAuth();
  const canManage = hasPermission('intervention:manage');
  const canAssign = hasPermission('intervention:assign');
  const canClose = hasPermission('intervention:close');

  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-text-primary">{action.title}</h1>
          <p className="mt-1 text-sm text-text-secondary">
            {actionTypeLabel(action.actionType)}
            {action.siteName ? ` · ${action.siteName}` : ''}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <PriorityBadge priority={toPriorityLevel(action.priority)} />
          <StatusBadge tone={actionStatusTone(action.status)} label={actionStatusLabel(action.status)} />
          {canManage && (
            <Button variant="secondary" size="sm" onClick={onEdit}>
              Edit
            </Button>
          )}
        </div>
      </div>

      <Section title="Details">
        <dl className="grid grid-cols-2 gap-4 rounded-lg border border-border bg-surface p-4 sm:grid-cols-4">
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-text-muted">Owner</dt>
            <dd className="mt-0.5 text-sm text-text-primary">{action.ownerName ?? 'Unassigned'}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-text-muted">Due date</dt>
            <dd className="mt-0.5 text-sm text-text-primary">{formatDate(action.dueDate)}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-text-muted">Created</dt>
            <dd className="mt-0.5 text-sm text-text-primary">{formatDateTime(action.createdAt)}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-text-muted">Updated</dt>
            <dd className="mt-0.5 text-sm text-text-primary">{formatDateTime(action.updatedAt)}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-text-muted">External reference</dt>
            <dd className="mt-0.5 text-sm text-text-primary">{action.externalReference ?? '—'}</dd>
          </div>
          {action.sourceEventId && (
            <div>
              <dt className="text-xs font-medium uppercase tracking-wide text-text-muted">Source event</dt>
              <dd className="mt-0.5 text-sm text-text-primary">
                {/* "View source event" — never the raw sourceEventId UUID
                 * as the visible label (SIE Milestone 18 corrective patch,
                 * §2B). The link itself still navigates by the real id;
                 * no event title exists in this API response to show
                 * instead, and one is not fabricated here. */}
                <Link to={`/events/${action.sourceEventId}`} className="text-teal-700 hover:underline">
                  View source event
                </Link>
              </dd>
            </div>
          )}
          {action.completedAt && (
            <div>
              <dt className="text-xs font-medium uppercase tracking-wide text-text-muted">Completed</dt>
              <dd className="mt-0.5 text-sm text-text-primary">{formatDateTime(action.completedAt)}</dd>
            </div>
          )}
          {action.cancelledAt && (
            <div>
              <dt className="text-xs font-medium uppercase tracking-wide text-text-muted">Cancelled</dt>
              <dd className="mt-0.5 text-sm text-text-primary">{formatDateTime(action.cancelledAt)}</dd>
            </div>
          )}
        </dl>
      </Section>

      <Section title="Description">
        <p className="rounded-lg border border-border bg-surface p-4 text-sm leading-relaxed text-text-primary">
          {action.description ?? 'No description was recorded for this action.'}
        </p>
      </Section>

      <Section title="Status">
        <StatusChangeControl action={action} canManage={canManage} canClose={canClose} onChanged={onChanged} />
      </Section>

      <Section title="Assignment">
        <AssignmentControl action={action} canAssign={canAssign} onChanged={onChanged} />
      </Section>
    </>
  );
}

/**
 * The "Change status" workflow (milestone §6). Presents only the target
 * statuses `suggestedNextStatuses()` names AND the caller is permitted
 * to attempt (terminal targets need `intervention:close`, everything
 * else needs `intervention:manage`) — a UI convenience only. The
 * backend's own response to `POST /actions/{id}/status` is the sole
 * authority on whether the transition actually succeeds: this control
 * never marks the action changed until that call resolves, and on
 * failure the previously displayed status is left exactly as it was
 * (never an optimistic update).
 */
function StatusChangeControl({
  action,
  canManage,
  canClose,
  onChanged,
}: {
  action: SafetyAction;
  canManage: boolean;
  canClose: boolean;
  onChanged: (updated: SafetyAction) => void;
}) {
  const repository = useActionRepository();
  const [target, setTarget] = useState<ActionStatus | ''>('');
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isTerminal = ACTION_TERMINAL_STATUSES.includes(action.status);
  const permittedTargets = suggestedNextStatuses(action.status).filter((candidate) =>
    ACTION_TERMINAL_STATUSES.includes(candidate) ? canClose : canManage,
  );

  if (isTerminal) {
    return (
      <p className="text-sm text-text-secondary">
        This action is {actionStatusLabel(action.status).toLowerCase()} and cannot be reopened.
      </p>
    );
  }

  if (permittedTargets.length === 0) {
    return <p className="text-sm text-text-secondary">You do not have permission to change this action's status.</p>;
  }

  async function handleSubmit() {
    if (!target) {
      setError('Choose a status to change to.');
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const updated = await repository.updateStatus(action.id, target, comment.trim() || undefined);
      onChanged(updated);
      setTarget('');
      setComment('');
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Could not update the status.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-48">
          <Select
            label="Change status to"
            value={target}
            onChange={(event) => setTarget(event.target.value as ActionStatus | '')}
            options={[
              { value: '', label: 'Select a status' },
              ...permittedTargets.map((value) => ({ value, label: actionStatusLabel(value) })),
            ]}
          />
        </div>
        <div className="min-w-64 flex-1">
          <Input
            label="Comment (optional)"
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            maxLength={2000}
          />
        </div>
        <Button onClick={handleSubmit} disabled={submitting}>
          {submitting ? 'Updating…' : 'Update status'}
        </Button>
      </div>
      {error && (
        <p role="alert" className="text-sm text-critical">
          {error}
        </p>
      )}
    </div>
  );
}

/**
 * The reassignment workflow (milestone §7) — a separate control from
 * general edit, gated on `intervention:assign` specifically. When the
 * caller lacks that permission, no editable control is rendered at all
 * (the current owner is already shown, read-only, in the Details
 * section above) — never a control that looks editable but silently
 * fails.
 */
function AssignmentControl({
  action,
  canAssign,
  onChanged,
}: {
  action: SafetyAction;
  canAssign: boolean;
  onChanged: (updated: SafetyAction) => void;
}) {
  const repository = useActionRepository();
  const [ownerOptions, setOwnerOptions] = useState<ActionOption[]>([]);
  const [ownerUserId, setOwnerUserId] = useState(action.ownerUserId ?? '');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setOwnerUserId(action.ownerUserId ?? '');
  }, [action.ownerUserId]);

  useEffect(() => {
    if (!canAssign) return;
    let cancelled = false;
    repository.listOwnerOptions().then((options) => {
      if (!cancelled) setOwnerOptions(options);
    });
    return () => {
      cancelled = true;
    };
  }, [canAssign, repository]);

  if (!canAssign) {
    return <p className="text-sm text-text-secondary">You do not have permission to reassign this action.</p>;
  }

  const knownOwnerOptions =
    action.ownerUserId && !ownerOptions.some((option) => option.value === action.ownerUserId)
      ? [{ value: action.ownerUserId, label: action.ownerName ?? action.ownerUserId }, ...ownerOptions]
      : ownerOptions;

  async function handleSubmit() {
    setError(null);
    setSubmitting(true);
    try {
      const updated = await repository.reassign(action.id, ownerUserId || null);
      onChanged(updated);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Could not reassign this action.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex w-64 flex-col gap-1">
          <Select
            label="Owner"
            value={ownerUserId}
            onChange={(event) => setOwnerUserId(event.target.value)}
            options={[{ value: '', label: 'Unassigned' }, ...knownOwnerOptions]}
          />
          <p className="text-xs text-text-muted">Candidates are labeled by role — see the Actions documentation for why.</p>
        </div>
        <Button onClick={handleSubmit} disabled={submitting || ownerUserId === (action.ownerUserId ?? '')}>
          {submitting ? 'Saving…' : 'Save assignment'}
        </Button>
      </div>
      {error && (
        <p role="alert" className="text-sm text-critical">
          {error}
        </p>
      )}
    </div>
  );
}
