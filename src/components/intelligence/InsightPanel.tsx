import { Info } from 'lucide-react';
import type { EvidenceRecord } from '../../types/evidence';
import { EvidenceList } from '../data/EvidenceList';

export interface InsightPanelProps {
  /** e.g. "What SIE found" — kept as a prop rather than a hardcoded
   * string so this component can be reused for a differently-worded
   * finding elsewhere. */
  heading: string;
  /** The finding, in plain language. `null` means there isn't enough
   * evidence to state one — see this component's own "insufficient
   * evidence" fallback. Never fabricate a finding to fill the space. */
  finding: string | null;
  evidence: EvidenceRecord[];
  /** Optional short qualifier shown under the finding (e.g. "Based on
   * the last 90 days"). Only rendered when a real basis is given —
   * never invented confidence language. */
  context?: string;
}

/**
 * The restrained evidence-grounded finding pattern (§16): Finding →
 * Evidence → Context. No glow, no "AI brain" iconography, no confidence
 * percentage invented from nowhere — a finding is only ever shown
 * alongside the records that support it, and when there isn't enough
 * evidence, the panel says so plainly instead of guessing.
 */
export function InsightPanel({ heading, finding, evidence, context }: InsightPanelProps) {
  const hasFinding = finding !== null && evidence.length > 0;

  return (
    <section className="rounded-lg border border-border bg-surface p-4">
      <h3 className="text-sm font-semibold text-text-primary">{heading}</h3>

      {hasFinding ? (
        <>
          <p className="mt-1.5 text-sm text-text-primary">{finding}</p>
          {context && <p className="mt-0.5 text-xs text-text-muted">{context}</p>}
          <div className="mt-3">
            <EvidenceList evidence={evidence} />
          </div>
        </>
      ) : (
        <p className="mt-1.5 flex items-center gap-1.5 text-sm text-text-secondary">
          <Info className="h-4 w-4 shrink-0 text-text-muted" aria-hidden="true" />
          Insufficient evidence to state a finding here.
        </p>
      )}
    </section>
  );
}
