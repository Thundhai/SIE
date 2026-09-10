import { ReactNode } from 'react';
import { cn } from '../../lib/cn';

export interface TableColumn<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  /** Right-aligns numeric/short columns (e.g. a count or a date). */
  align?: 'left' | 'right';
  className?: string;
}

export interface TableProps<T> {
  columns: TableColumn<T>[];
  rows: T[];
  getRowKey: (row: T) => string;
  /** Optional row click handler — when provided, each row becomes a real
   * button-role element (keyboard-activatable, not just a `div` with an
   * onClick), per §18's "appropriate button semantics"/"accessible
   * tables". */
  onRowClick?: (row: T) => void;
  caption?: string;
}

/** A plain, semantic `<table>` — real `<thead>`/`<tbody>`/`<th
 * scope="col">`, not a div-grid pretending to be one (the legacy
 * prototype's own pattern). Loading/empty/error states are the caller's
 * responsibility (LoadingState/EmptyState/ErrorState) — Table only ever
 * renders rows it's given. */
export function Table<T>({ columns, rows, getRowKey, onRowClick, caption }: TableProps<T>) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full border-collapse text-sm">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr className="bg-surface-muted text-left">
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={cn(
                  'px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-text-secondary',
                  column.align === 'right' && 'text-right',
                )}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const key = getRowKey(row);
            return (
              <tr
                key={key}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                tabIndex={onRowClick ? 0 : undefined}
                role={onRowClick ? 'button' : undefined}
                onKeyDown={
                  onRowClick
                    ? (event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault();
                          onRowClick(row);
                        }
                      }
                    : undefined
                }
                className={cn(
                  'border-t border-border bg-surface',
                  onRowClick && 'cursor-pointer hover:bg-surface-muted focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-teal-600',
                )}
              >
                {columns.map((column) => (
                  <td key={column.key} className={cn('px-4 py-3 text-text-primary', column.align === 'right' && 'text-right', column.className)}>
                    {column.render(row)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
