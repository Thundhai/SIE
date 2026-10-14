/** Backend's own max `page_size` for `/intelligence/decisions` and
 * `/intelligence/outcomes` (`Query(..., le=200)`). */
export const ANNOTATION_LOOKUP_PAGE_SIZE = 200;
/** Safety cap, not a real-world expectation — 25 * 200 = 5,000 records
 * is already far beyond what an "already decided" / "has an outcome"
 * annotation lookup needs; this just bounds worst-case request count
 * rather than looping forever against a runaway `total`. */
export const ANNOTATION_LOOKUP_MAX_PAGES = 25;

/** Fetches every page of a paginated list endpoint and concatenates the
 * items, so a correlation lookup (by `attention_reference` or
 * `decision_id`) built from the result is never silently missing
 * anything past the first page — the bug this exists to prevent: an
 * attention item's most recent decision/outcome being older than the
 * newest `page_size` records org-wide, so its annotation is dropped.
 * Shared by `IntelligencePage.tsx` and `HomePage.tsx`, which both build
 * this same kind of correlation lookup from `listDecisions`/
 * `listOutcomes`. */
export async function fetchAllPages<T>(
  fetchPage: (page: number, pageSize: number, signal?: AbortSignal) => Promise<{ items: T[]; total: number }>,
  signal?: AbortSignal,
): Promise<T[]> {
  const items: T[] = [];
  let page = 1;
  while (page <= ANNOTATION_LOOKUP_MAX_PAGES) {
    if (signal?.aborted) break;
    const result = await fetchPage(page, ANNOTATION_LOOKUP_PAGE_SIZE, signal);
    items.push(...result.items);
    if (result.items.length === 0 || items.length >= result.total) break;
    page += 1;
  }
  return items;
}
