/**
 * Organizations/membership service — thin typed wrappers around the real
 * backend endpoints (`backend/app/api/v1/organizations.py`,
 * `backend/app/api/v1/memberships.py`). Response shapes mirror
 * `OrganizationRead`/`OrganizationMembershipRead` field-for-field —
 * nothing here is invented.
 */
import { apiRequest } from './client';

export interface Organization {
  id: string;
  name: string;
  industry: string | null;
  country: string | null;
  status: string;
}

export interface OrganizationMembership {
  id: string;
  user_id: string;
  organization_id: string;
  role: string;
  status: string;
}

export function getOrganization(organizationId: string, signal?: AbortSignal): Promise<Organization> {
  return apiRequest<Organization>(`/organizations/${organizationId}`, { signal });
}

export function getMembership(
  organizationId: string,
  userId: string,
  signal?: AbortSignal,
): Promise<OrganizationMembership> {
  return apiRequest<OrganizationMembership>(`/organizations/${organizationId}/members/${userId}`, { signal });
}
