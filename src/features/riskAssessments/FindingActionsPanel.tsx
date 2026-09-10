import { type FormEvent, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { Button } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { Input } from '../../components/ui/Input';
import { LoadingState } from '../../components/ui/LoadingState';
import { Select } from '../../components/ui/Select';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { Textarea } from '../../components/ui/Textarea';
import { useActionRepository } from '../actions/useActionRepository';
import { ACTION_PRIORITY_OPTIONS, ACTION_TYPE_OPTIONS, actionStatusLabel, actionStatusTone } from '../actions/actionStatus';
import type { ActionOption } from '../actions/actionRepository';
import type { ActionPriority, ActionStatus, ActionType } from '../../types/actions';
import {
  createFindingAction,
  linkFindingAction,
  listFindingActions,
  unlinkFindingAction,
  type RiskAssessmentLinkedAction,
} from '../../services/api/riskAssessments';
import type { AsyncState } from '../../types/common';

export interface FindingActionsPanelProps {
  organizationId: string;
  assessmentId: string;
  findingId: string;
  /** Whether the parent assessment is currently editable — mirrors the
   * backend's own `require_editable()` gate so mutation controls aren't
   * offered for an APPROVED/SUPERSEDED/ARCHIVED assessment even before
   * the backend rejects the attempt. */
  isEditable: boolean;
}

/**
 * A finding's linked actions (SIE Milestone 27 / UI-02 Part 8-9) — view,
 * create-from-finding, link an existing action, or unlink. Every
 * mutation is gated on the real effective permissions
 * (`risk_assessment:write`, `intervention:manage`/`intervention:assign`)
 * — never a fabricated frontend authorization; the backend remains the
 * sole authority either way.
 */
export function FindingActionsPanel({ organizationId, assessmentId, findingId, isEditable }: FindingActionsPanelProps) {
  const { hasPermission } = useAuth();
  const navigate = useNavigate();
  const canLinkOrUnlink = hasPermission('risk_assessment:write') && isEditable;
  const canCreateAction = canLinkOrUnlink && hasPermission('intervention:manage');

  const [state, setState] = useState<AsyncState<RiskAssessmentLinkedAction[]>>({ status: 'loading' });
  const [reloadToken, setReloadToken] = useState(0);
  const [mode, setMode] = useState<'none' | 'create' | 'link'>('none');
  const [unlinkingId, setUnlinkingId] = useState<string | null>(null);
  const [unlinkError, setUnlinkError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setState({ status: 'loading' });
    listFindingActions(organizationId, assessmentId, findingId, controller.signal)
      .then((result) => setState({ status: 'success', data: result.items }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load linked actions.' });
      });
    return () => controller.abort();
  }, [organizationId, assessmentId, findingId, reloadToken]);

  async function handleUnlink(actionId: string) {
    setUnlinkError(null);
    setUnlinkingId(actionId);
    try {
      await unlinkFindingAction(organizationId, assessmentId, findingId, actionId);
      setReloadToken((token) => token + 1);
    } catch (error) {
      setUnlinkError(error instanceof Error ? error.message : 'Could not unlink this action.');
    } finally {
      setUnlinkingId(null);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {state.status === 'loading' && <LoadingState label="Loading linked actions…" />}
      {state.status === 'error' && (
        <ErrorState description={state.message} onRetry={() => setReloadToken((token) => token + 1)} />
      )}

      {state.status === 'success' && state.data.length === 0 && mode === 'none' && (
        <EmptyState
          title="No actions linked to this finding"
          description="Corrective or follow-up actions raised from this finding will appear here."
        />
      )}

      {state.status === 'success' && state.data.length > 0 && (
        <ul className="flex flex-col gap-2">
          {state.data.map((linked) => (
            <li
              key={linked.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface p-3"
            >
              <button
                type="button"
                onClick={() => navigate(`/actions/${linked.action_id}`)}
                className="text-left text-sm font-medium text-text-primary hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600"
              >
                {linked.action_title}
              </button>
              <div className="flex items-center gap-2">
                <StatusBadge tone={actionStatusTone(linked.action_status as ActionStatus)} label={actionStatusLabel(linked.action_status as ActionStatus)} />
                {canLinkOrUnlink && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleUnlink(linked.action_id)}
                    disabled={unlinkingId === linked.action_id}
                  >
                    {unlinkingId === linked.action_id ? 'Unlinking…' : 'Unlink'}
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {unlinkError && (
        <p role="alert" className="text-sm text-critical">
          {unlinkError}
        </p>
      )}

      {canCreateAction && mode === 'none' && (
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={() => setMode('create')}>
            Create action
          </Button>
          <Button variant="secondary" size="sm" onClick={() => setMode('link')}>
            Link existing action
          </Button>
        </div>
      )}
      {!canCreateAction && canLinkOrUnlink && mode === 'none' && (
        <Button variant="secondary" size="sm" onClick={() => setMode('link')}>
          Link existing action
        </Button>
      )}

      {mode === 'create' && (
        <CreateFindingActionForm
          organizationId={organizationId}
          assessmentId={assessmentId}
          findingId={findingId}
          onCancel={() => setMode('none')}
          onCreated={() => {
            setMode('none');
            setReloadToken((token) => token + 1);
          }}
        />
      )}
      {mode === 'link' && (
        <LinkExistingActionForm
          organizationId={organizationId}
          assessmentId={assessmentId}
          findingId={findingId}
          onCancel={() => setMode('none')}
          onLinked={() => {
            setMode('none');
            setReloadToken((token) => token + 1);
          }}
        />
      )}
    </div>
  );
}

function CreateFindingActionForm({
  organizationId,
  assessmentId,
  findingId,
  onCancel,
  onCreated,
}: {
  organizationId: string;
  assessmentId: string;
  findingId: string;
  onCancel: () => void;
  onCreated: () => void;
}) {
  const { hasPermission } = useAuth();
  const canAssign = hasPermission('intervention:assign');
  const repository = useActionRepository();

  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [actionType, setActionType] = useState<ActionType | ''>('');
  const [priority, setPriority] = useState<ActionPriority>('MEDIUM');
  const [ownerUserId, setOwnerUserId] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [ownerOptions, setOwnerOptions] = useState<ActionOption[]>([]);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [idempotencyKey] = useState(() => crypto.randomUUID());

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

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!title.trim()) {
      setValidationError('Title is required.');
      return;
    }
    if (!actionType) {
      setValidationError('Action type is required.');
      return;
    }
    setValidationError(null);
    setSubmitError(null);
    setSubmitting(true);
    try {
      await createFindingAction(
        organizationId,
        assessmentId,
        findingId,
        {
          title: title.trim(),
          description: description.trim() || undefined,
          action_type: actionType,
          priority,
          owner_user_id: canAssign ? ownerUserId || undefined : undefined,
          due_date: dueDate || undefined,
        },
        idempotencyKey,
      );
      onCreated();
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : 'Could not create this action.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4" onSubmit={handleSubmit}>
      <Input label="Title" value={title} onChange={(event) => setTitle(event.target.value)} required maxLength={255} />
      <Textarea label="Description" value={description} onChange={(event) => setDescription(event.target.value)} maxLength={5000} />
      <div className="flex flex-wrap gap-3">
        <div className="w-44">
          <Select
            label="Action type"
            value={actionType}
            onChange={(event) => setActionType(event.target.value as ActionType)}
            options={[{ value: '', label: 'Select a type' }, ...ACTION_TYPE_OPTIONS]}
            required
          />
        </div>
        <div className="w-36">
          <Select
            label="Priority"
            value={priority}
            onChange={(event) => setPriority(event.target.value as ActionPriority)}
            options={ACTION_PRIORITY_OPTIONS}
          />
        </div>
        <div className="w-44">
          <Input label="Due date" type="date" value={dueDate} onChange={(event) => setDueDate(event.target.value)} />
        </div>
      </div>
      {canAssign && (
        <Select
          label="Owner"
          value={ownerUserId}
          onChange={(event) => setOwnerUserId(event.target.value)}
          options={[{ value: '', label: 'Unassigned' }, ...ownerOptions]}
        />
      )}
      {validationError && (
        <p role="alert" className="text-sm text-critical">
          {validationError}
        </p>
      )}
      {submitError && (
        <p role="alert" className="text-sm text-critical">
          {submitError}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="secondary" size="sm" onClick={onCancel} disabled={submitting}>
          Cancel
        </Button>
        <Button type="submit" size="sm" disabled={submitting}>
          {submitting ? 'Creating…' : 'Create action'}
        </Button>
      </div>
    </form>
  );
}

function LinkExistingActionForm({
  organizationId,
  assessmentId,
  findingId,
  onCancel,
  onLinked,
}: {
  organizationId: string;
  assessmentId: string;
  findingId: string;
  onCancel: () => void;
  onLinked: () => void;
}) {
  const repository = useActionRepository();
  const [search, setSearch] = useState('');
  const [results, setResults] = useState<{ id: string; title: string; status: string }[]>([]);
  const [searching, setSearching] = useState(false);
  const [linkingId, setLinkingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!search.trim()) {
      setResults([]);
      return;
    }
    let cancelled = false;
    setSearching(true);
    const timeout = setTimeout(() => {
      repository
        .list({ page: 1, pageSize: 10, search: search.trim() })
        .then((page) => {
          if (!cancelled) setResults(page.items.map((item) => ({ id: item.id, title: item.title, status: item.status })));
        })
        .catch(() => {
          if (!cancelled) setResults([]);
        })
        .finally(() => {
          if (!cancelled) setSearching(false);
        });
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(timeout);
    };
  }, [search, repository]);

  async function handleLink(actionId: string) {
    setError(null);
    setLinkingId(actionId);
    try {
      await linkFindingAction(organizationId, assessmentId, findingId, actionId);
      onLinked();
    } catch (linkError) {
      setError(linkError instanceof Error ? linkError.message : 'Could not link this action.');
    } finally {
      setLinkingId(null);
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4">
      <Input
        label="Search actions"
        placeholder="Search by title"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />
      {searching && <p className="text-xs text-text-muted">Searching…</p>}
      {!searching && search.trim() && results.length === 0 && (
        <p className="text-xs text-text-muted">No actions match this search.</p>
      )}
      {results.length > 0 && (
        <ul className="flex flex-col gap-1.5">
          {results.map((result) => (
            <li key={result.id} className="flex items-center justify-between gap-2 rounded-md border border-border px-3 py-2">
              <span className="text-sm text-text-primary">{result.title}</span>
              <Button variant="secondary" size="sm" onClick={() => handleLink(result.id)} disabled={linkingId === result.id}>
                {linkingId === result.id ? 'Linking…' : 'Link'}
              </Button>
            </li>
          ))}
        </ul>
      )}
      {error && (
        <p role="alert" className="text-sm text-critical">
          {error}
        </p>
      )}
      <div className="flex justify-end">
        <Button type="button" variant="secondary" size="sm" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
