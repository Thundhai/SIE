import { type FormEvent, useEffect, useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { Button } from '../../components/ui/Button';
import { Drawer } from '../../components/ui/Drawer';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Textarea } from '../../components/ui/Textarea';
import type { ActionPriority, ActionType, SafetyAction } from '../../types/actions';
import { ACTION_PRIORITY_OPTIONS, ACTION_TYPE_OPTIONS } from './actionStatus';
import type { ActionOption } from './actionRepository';
import { useActionRepository } from './useActionRepository';

/** `datetime` -> the `yyyy-MM-dd` shape `<input type="date">` needs. */
function toDateInputValue(value: string | null): string {
  if (!value) return '';
  return value.slice(0, 10);
}

export interface ActionFormDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  /** `'create'` opens a blank form (optionally pre-filled with
   * `sourceEventId` from Event Detail's "Create action" flow — milestone
   * §8). `'edit'` opens pre-filled from `action`, and never offers
   * `owner`/`source_event_id`: reassignment is its own, separately
   * permissioned control (`ReassignControl.tsx`), and `source_event_id`
   * is immutable once set (milestone §5). */
  mode: 'create' | 'edit';
  action?: SafetyAction;
  sourceEventId?: string;
  onSaved: (action: SafetyAction) => void;
}

/**
 * The Create/Edit Action workflow (milestone §4/§5) — one drawer for
 * both modes, since the fields and validation largely overlap. Every
 * field here corresponds to a real field the backend's
 * `SafetyActionCreate`/`SafetyActionUpdate` schema actually accepts
 * (`backend/app/schemas/actions.py`) — nothing is invented, and
 * `organization_id`/`status`/audit fields are never presented as
 * editable. Client-side validation here only catches the obvious case
 * (an empty title) for a fast, friendly error — the backend's own
 * validation is authoritative either way, and its message is surfaced
 * verbatim on failure rather than re-implemented here.
 */
export function ActionFormDrawer({ isOpen, onClose, mode, action, sourceEventId, onSaved }: ActionFormDrawerProps) {
  const repository = useActionRepository();
  const { hasPermission } = useAuth();
  const canAssign = hasPermission('intervention:assign');

  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [actionType, setActionType] = useState<ActionType | ''>('');
  const [priority, setPriority] = useState<ActionPriority>('MEDIUM');
  const [siteId, setSiteId] = useState('');
  const [ownerUserId, setOwnerUserId] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [externalReference, setExternalReference] = useState('');

  const [siteOptions, setSiteOptions] = useState<ActionOption[]>([]);
  const [ownerOptions, setOwnerOptions] = useState<ActionOption[]>([]);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [idempotencyKey, setIdempotencyKey] = useState('');

  useEffect(() => {
    if (!isOpen) return;

    if (mode === 'edit' && action) {
      setTitle(action.title);
      setDescription(action.description ?? '');
      setActionType(action.actionType);
      setPriority(action.priority);
      setSiteId(action.siteId ?? '');
      setDueDate(toDateInputValue(action.dueDate));
      setExternalReference(action.externalReference ?? '');
    } else {
      setTitle('');
      setDescription('');
      setActionType('');
      setPriority('MEDIUM');
      setSiteId('');
      setOwnerUserId('');
      setDueDate('');
      setExternalReference('');
      // One idempotency key per open "create" attempt, reused across
      // retries of that same attempt — never regenerated on a retry
      // (milestone §4 / services/api/actions.ts::createAction's own
      // docstring).
      setIdempotencyKey(crypto.randomUUID());
    }
    setValidationError(null);
    setSubmitError(null);
  }, [isOpen, mode, action]);

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    repository.listSiteOptions().then((options) => {
      if (!cancelled) setSiteOptions(options);
    });
    if (mode === 'create' && canAssign) {
      repository.listOwnerOptions().then((options) => {
        if (!cancelled) setOwnerOptions(options);
      });
    }
    return () => {
      cancelled = true;
    };
  }, [isOpen, mode, canAssign, repository]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitError(null);

    if (!title.trim()) {
      setValidationError('Title is required.');
      return;
    }
    if (!actionType) {
      setValidationError('Action type is required.');
      return;
    }
    setValidationError(null);
    setSubmitting(true);

    try {
      let saved: SafetyAction;
      if (mode === 'create') {
        saved = await repository.create(
          {
            title: title.trim(),
            description: description.trim() || undefined,
            actionType,
            priority,
            siteId: siteId || undefined,
            ownerUserId: canAssign ? ownerUserId || undefined : undefined,
            dueDate: dueDate || undefined,
            sourceEventId,
            externalReference: externalReference.trim() || undefined,
          },
          idempotencyKey,
        );
      } else {
        if (!action) throw new Error('No action to update.');
        saved = await repository.update(action.id, {
          title: title.trim(),
          description: description.trim() ? description.trim() : null,
          actionType,
          priority,
          siteId: siteId || null,
          dueDate: dueDate || null,
          externalReference: externalReference.trim() ? externalReference.trim() : null,
        });
      }
      onSaved(saved);
      onClose();
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : 'Could not save this action.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Drawer isOpen={isOpen} onClose={onClose} title={mode === 'create' ? 'Create action' : 'Edit action'}>
      <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
        {sourceEventId && (
          <p className="rounded-md border border-border bg-surface-muted px-3 py-2 text-xs text-text-secondary">
            This action will be linked to source event <span className="font-mono">{sourceEventId}</span>.
          </p>
        )}

        <Input label="Title" value={title} onChange={(event) => setTitle(event.target.value)} required maxLength={255} />

        <Textarea
          label="Description"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          maxLength={5000}
        />

        <Select
          label="Action type"
          value={actionType}
          onChange={(event) => setActionType(event.target.value as ActionType)}
          options={[{ value: '', label: 'Select a type' }, ...ACTION_TYPE_OPTIONS]}
          required
        />

        <Select
          label="Priority"
          value={priority}
          onChange={(event) => setPriority(event.target.value as ActionPriority)}
          options={ACTION_PRIORITY_OPTIONS}
        />

        <Select
          label="Site"
          value={siteId}
          onChange={(event) => setSiteId(event.target.value)}
          options={[{ value: '', label: 'No site' }, ...siteOptions]}
        />

        {mode === 'create' && canAssign && (
          <div className="flex flex-col gap-1">
            <Select
              label="Owner"
              value={ownerUserId}
              onChange={(event) => setOwnerUserId(event.target.value)}
              options={[{ value: '', label: 'Unassigned' }, ...ownerOptions]}
            />
            <p className="text-xs text-text-muted">Candidates are labeled by role — see the Actions documentation for why.</p>
          </div>
        )}

        <Input label="Due date" type="date" value={dueDate} onChange={(event) => setDueDate(event.target.value)} />

        <Input
          label="External reference"
          value={externalReference}
          onChange={(event) => setExternalReference(event.target.value)}
          maxLength={255}
          helperText="Optional — e.g. a CAPA or permit reference."
        />

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

        <div className="flex justify-end gap-2 border-t border-border pt-4">
          <Button type="button" variant="secondary" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? 'Saving…' : mode === 'create' ? 'Create action' : 'Save changes'}
          </Button>
        </div>
      </form>
    </Drawer>
  );
}
