import { ReactNode } from 'react';
import { Button } from './Button';

export interface FilterBarProps {
  children: ReactNode;
  onClear?: () => void;
  hasActiveFilters?: boolean;
}

/** A restrained horizontal layout for a row of filter controls
 * (SearchInput/Select), with an optional "Clear filters" action. Not a
 * filter-state-management framework — each screen owns its own filter
 * state and simply lays its controls out inside this wrapper (§8: "don't
 * over-engineer"). */
export function FilterBar({ children, onClear, hasActiveFilters }: FilterBarProps) {
  return (
    <div className="flex flex-wrap items-end gap-3 rounded-lg border border-border bg-surface p-4">
      {children}
      {onClear && (
        <Button variant="ghost" size="sm" onClick={onClear} disabled={!hasActiveFilters} className="mb-0.5">
          Clear filters
        </Button>
      )}
    </div>
  );
}
