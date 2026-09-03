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

export function listSites(organizationId: string, signal?: AbortSignal): Promise<Site[]> {
  return apiRequest<Site[]>(`/organizations/${organizationId}/sites`, { signal });
}
