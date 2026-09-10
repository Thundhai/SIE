import { Link } from 'react-router-dom';
import type { EvidenceRecord } from '../../types/evidence';

export interface EvidenceItemProps {
  evidence: EvidenceRecord;
}

/** One supporting-evidence row: a short reference code, a title, and
 * optional context — restrained, text-first, no icon theatre. */
export function EvidenceItem({ evidence }: EvidenceItemProps) {
  const content = (
    <>
      <span className="w-8 shrink-0 font-mono text-xs text-text-muted">{evidence.reference}</span>
      <span className="text-sm text-text-primary">{evidence.title}</span>
      {evidence.context && <span className="text-sm text-text-muted">— {evidence.context}</span>}
    </>
  );

  if (evidence.href) {
    return (
      <Link
        to={evidence.href}
        className="flex items-baseline gap-2 rounded px-1 py-0.5 hover:bg-surface-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600"
      >
        {content}
      </Link>
    );
  }

  return <div className="flex items-baseline gap-2 px-1 py-0.5">{content}</div>;
}
