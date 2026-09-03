import { FileText } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { DocumentReferenceRecord } from '../../types/evidence';
import { StatusBadge } from '../ui/StatusBadge';

const STATUS_LABEL: Record<DocumentReferenceRecord['verificationStatus'], string> = {
  verified: 'Verified',
  pending: 'Pending review',
  flagged: 'Flagged',
  rejected: 'Rejected',
};

const STATUS_TONE: Record<DocumentReferenceRecord['verificationStatus'], 'success' | 'warning' | 'critical' | 'neutral'> = {
  verified: 'success',
  pending: 'neutral',
  flagged: 'warning',
  rejected: 'critical',
};

export interface DocumentReferenceProps {
  document: DocumentReferenceRecord;
}

/** A single row referencing a knowledge document — used inside Event
 * Detail's "relevant knowledge" section. The Knowledge screen itself is
 * out of scope for this milestone; this component only presents a
 * reference, it doesn't browse the knowledge base. */
export function DocumentReference({ document }: DocumentReferenceProps) {
  const inner = (
    <>
      <FileText className="h-4 w-4 shrink-0 text-text-muted" aria-hidden="true" />
      <span className="flex-1 text-sm text-text-primary">{document.title}</span>
      <span className="text-xs text-text-muted">{document.source}</span>
      <StatusBadge tone={STATUS_TONE[document.verificationStatus]} label={STATUS_LABEL[document.verificationStatus]} />
    </>
  );

  const className = 'flex items-center gap-2.5 rounded-md border border-border bg-surface px-3 py-2';

  if (document.href) {
    return (
      <Link to={document.href} className={`${className} hover:bg-surface-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600`}>
        {inner}
      </Link>
    );
  }

  return <div className={className}>{inner}</div>;
}
