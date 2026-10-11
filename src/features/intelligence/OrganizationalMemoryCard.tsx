import type { IntegratedMemory } from '../../services/api/memoryIntegration';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { memoryApplicabilityLabel, memoryGovernanceTone, memoryTypeLabel } from './intelligenceLabels';

export interface OrganizationalMemoryCardProps {
  memory: IntegratedMemory;
}

/**
 * One governed organizational memory, shown contextually (SIE Milestone
 * 42 spec §11) — never inside a standalone "AI memory" dashboard. Every
 * field rendered here is exactly what
 * `resolve_eligible_organizational_memories()` already determined
 * server-side: this component never re-derives or guesses applicability,
 * governance, or relevance on its own. Provenance (learning candidate ->
 * outcome -> verification) is shown as plain ids — a full drill-down
 * into that chain is out of M42's scope (no UI exists yet for those
 * intermediate records), but the ids themselves are never hidden.
 */
export function OrganizationalMemoryCard({ memory }: OrganizationalMemoryCardProps) {
  return (
    <div className="flex flex-col gap-1.5 rounded-lg border border-border bg-surface p-3.5">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-medium text-text-primary">{memory.title}</p>
        <StatusBadge tone={memoryGovernanceTone(memory.governance_status)} label={memory.governance_status} />
      </div>
      <p className="text-sm text-text-secondary">{memory.memory_content}</p>
      <p className="text-xs text-text-muted">{memoryTypeLabel(memory.memory_type)}</p>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-text-muted">
        <span>{memoryApplicabilityLabel(memory.applicability_basis)}</span>
        <span>·</span>
        <span>Recorded {new Date(memory.memory_created_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}</span>
      </div>
      <p className="mt-0.5 text-xs text-text-muted">
        Source: governed organizational memory · learning candidate {memory.learning_candidate_id.slice(0, 8)} · outcome{' '}
        {memory.outcome_id.slice(0, 8)}
      </p>
    </div>
  );
}
