import { apiRequest } from './client';
import type { Organization, OrganizationMembership } from './organizations';

export interface Site {
  id: string;
  organization_id: string;
  name: string;
  location: string | null;
  country: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface GoverningStandard {
  id: string;
  name: string;
  short_description: string;
  issuing_organization: string;
  standard_type: string;
  version: string | null;
  verification_status: string;
  is_active: boolean;
}

export interface ActiveGoverningStandard {
  standard: GoverningStandard;
  selection: {
    id: string;
    status: string;
    effective_date: string | null;
    rationale: string | null;
    decided_at: string;
  };
}

export interface ApiClient {
  id: string;
  organization_id: string;
  name: string;
  client_id: string;
  secret_prefix: string;
  scopes: string[];
  status: string;
  created_at: string;
  last_used_at: string | null;
  rotated_at: string | null;
  revoked_at: string | null;
  expires_at: string | null;
}

export function listSites(organizationId: string, signal?: AbortSignal) {
  return apiRequest<Site[]>(\`/organizations/\${organizationId}/sites\`, { signal });
}

export function listMembers(organizationId: string, signal?: AbortSignal) {
  return apiRequest<OrganizationMembership[]>(\`/organizations/\${organizationId}/members\`, { signal });
}

export function listActiveGoverningStandards(organizationId: string, signal?: AbortSignal) {
  return apiRequest<{ items: ActiveGoverningStandard[]; total: number }>(
    '/organization-governing-standards',
    { query: { organization_id: organizationId }, signal },
  );
}

export function listApiClients(organizationId: string, signal?: AbortSignal) {
  return apiRequest<ApiClient[]>(\`/organizations/\${organizationId}/api-clients\`, { signal });
}
