/**
 * Sites service — thin typed wrapper around the real, pre-existing
 * `GET`/`POST /organizations/{organization_id}/sites` endpoints
 * (`backend/app/api/v1/sites.py`). Used by `ApiEventRepository` to offer
 * real site names in the Events screen's site filter, and by the
 * Administration screen's Sites section — the one canonical definition
 * of `Site`/`listSites`, reused rather than duplicated (the backend has
 * no `PATCH`/`DELETE` for sites, so create is the only mutation offered
 * anywhere).
 */
import { apiRequest } from './client';

export interface Site {
  id: string;
  name: string;
  location: string | null;
  country: string | null;
  status: string;
  organization_id: string;
  created_at: string;
  updated_at: string;
}

export interface CreateSiteInput {
  name: string;
  location?: string;
  country?: string;
  /** Free text on the backend (`SiteBase.status`, default `"active"`) —
   * no enum exists server-side, so this is never constrained to an
   * invented fixed vocabulary. */
  status?: string;
}

export function listSites(organizationId: string, signal?: AbortSignal): Promise<Site[]> {
  return apiRequest<Site[]>(`/organizations/${organizationId}/sites`, { signal });
}

export function createSite(organizationId: string, input: CreateSiteInput, signal?: AbortSignal): Promise<Site> {
  return apiRequest<Site>(`/organizations/${organizationId}/sites`, {
    method: 'POST',
    body: {
      name: input.name,
      location: input.location || null,
      country: input.country || null,
      status: input.status || undefined,
    },
    signal,
  });
}
