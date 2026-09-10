/** Shared cross-feature types for the new SIE frontend. */

/** The restrained status vocabulary StatusBadge renders. Intentionally
 * small and generic — a feature (Events, later Actions) maps its own
 * domain status strings onto this at the data layer, not inside the
 * component. */
export type StatusTone = 'success' | 'warning' | 'critical' | 'informational' | 'neutral';

export interface StatusDescriptor {
  label: string;
  tone: StatusTone;
}

/** A generic page of results — used by any repository (fixture or, later,
 * real API) that returns a paginated list. */
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

/** The three states almost every data-driven view needs to render
 * explicitly (see LoadingState/EmptyState/ErrorState). Modeled as a
 * discriminated union so a component can never forget a case. */
export type AsyncState<T> =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'success'; data: T };
