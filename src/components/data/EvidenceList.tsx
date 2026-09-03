import type { EvidenceRecord } from '../../types/evidence';
import { EvidenceItem } from './EvidenceItem';

export interface EvidenceListProps {
  evidence: EvidenceRecord[];
  label?: string;
}

export function EvidenceList({ evidence, label = 'Supporting evidence' }: EvidenceListProps) {
  if (evidence.length === 0) return null;
  return (
    <div>
      <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-text-secondary">{label}</p>
      <ul className="flex flex-col gap-0.5">
        {evidence.map((item) => (
          <li key={item.reference}>
            <EvidenceItem evidence={item} />
          </li>
        ))}
      </ul>
    </div>
  );
}
