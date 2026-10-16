/**
 * Sites service — thin typed wrapper around the real, pre-existing
 * `GET /organizations/{organization_id}/sites` endpoint
 * (`backend/app/api/v1/sites.py`). Used by `ApiEventRepository` to offer
 * real site names in the Events screen's site filter, instead of the
 * fixture repository's hardcoded example names.
 */
import { apiRequest } from './client';

export interface Site {
  id: string;
  name: string;
  location: string | null;
  country: string | null;
  status: string;
  organization_id: string;
}

/**
 * Fetch every site in the organization. The API caps a page at 500 and
 * returns a plain array, so continue until a short page indicates the end.
 * This keeps the scope selector and site-label resolution complete for
 * organizations larger than one page.
 */
export async function listSites(organizationId: string, signal?: AbortSignal): Promise<Site[]> {
  const pageSize = 500;
  const sites: Site[] = [];
  for (let skip = 0; ; skip += pageSize) {
    if (signal?.aborted) throw new DOMException('The request was aborted.', 'AbortError');
    const page = await apiRequest<Site[]>(`/organizations/${organizationId}/sites`, {
      query: { skip, limit: pageSize },
      signal,
    });
    sites.push(...page);
    if (page.length < pageSize) return sites;
  }
}
