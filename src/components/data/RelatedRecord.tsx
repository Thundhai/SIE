import { ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { RelatedRecordItem } from '../../types/evidence';

export interface RelatedRecordProps {
  record: RelatedRecordItem;
}

/** A single "related X" reference row (e.g. a related action or a
 * sibling event) — generic across record types, distinguished only by
 * its `type` label. */
export function RelatedRecord({ record }: RelatedRecordProps) {
  const inner = (
    <>
      <div>
        <p className="text-sm font-medium text-text-primary">{record.title}</p>
        <p className="text-xs text-text-muted">{record.type}</p>
      </div>
      {record.href && <ArrowRight className="h-4 w-4 text-text-muted" aria-hidden="true" />}
    </>
  );

  const className = 'flex items-center justify-between gap-3 rounded-md border border-border bg-surface px-3 py-2.5';

  if (record.href) {
    return (
      <Link to={record.href} className={`${className} hover:bg-surface-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600`}>
        {inner}
      </Link>
    );
  }

  return <div className={className}>{inner}</div>;
}
