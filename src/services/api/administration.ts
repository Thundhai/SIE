/**
 * Administration API service — Organization, Sites, Users & Membership,
 * Governing Standards, and API Clients. Thin typed wrappers around the
 * real, already-built backend endpoints in
 * `backend/app/api/v1/{organizations,sites,memberships,governing_standards,api_clients}.py`
 * — every field mirrors the backend's own Pydantic schemas field-for-field.
 * Nothing here is invented: an operation only exists in this file if the
 * corresponding backend route already exists.
 *
 * Two distinct authorization/tenant-resolution styles are reused verbatim
 * from the backend, not redesigned:
 *  - Sites: `organization_id` in the URL path, no explicit permission gate.
 *  - Members / API Clients: `organization_id` in the URL path, gated by
 *    `users:read`/`users:manage`.
 *  - Governing Standards: `organization_id` as a query parameter (M43A's
 *    own `resolve_authorized_organization_id()` pattern), gated by
 *    `standards:read`/`standards:manage`.
 */
import { apiRequest } from './client';
import type { OrganizationMembership } from './organizations';

// Sites: `Site`/`listSites`/`createSite` already exist as
// `services/api/sites.ts` (pre-existing, used by `ApiEventRepository`'s
// site filter) — reused there rather than duplicated here. Administration
// consumers import directly from `./sites`.

// --- Users & Membership --------------------------------------------------------------------------

/** Mirrors `app/services/permissions.py::OrganizationRole` verbatim. */
export type OrganizationRole = 'ORG_ADMIN' | 'HSE_MANAGER' | 'HSE_ANALYST' | 'HSE_USER' | 'VIEWER';

/** Mirrors `app/models/enums.py::MembershipStatus` verbatim. */
export type MembershipStatus = 'ACTIVE' | 'SUSPENDED' | 'INVITED' | 'REVOKED';

export interface AddMemberInput {
  /** Identifies an *existing* User by id — the backend has no
   * self-registration/invitation flow and no `GET /users` endpoint to
   * resolve a name from, so this is deliberately a raw id, never a
   * fabricated user-profile lookup. */
  userId: string;
  role: OrganizationRole;
  status?: MembershipStatus;
}

/** Listing members already exists as `services/api/organizations.ts::listMembers()` —
 * reused there rather than duplicated here. */
export function addMember(organizationId: string, input: AddMemberInput, signal?: AbortSignal) {
  return apiRequest<OrganizationMembership>(`/organizations/${organizationId}/members`, {
    method: 'POST',
    body: {
      user_id: input.userId,
      role: input.role,
      status: input.status || undefined,
    },
    signal,
  });
}

// --- Governing Standards (SIE Milestone 43A) ------------------------------------------------------

/** Mirrors `app/models/governing_standard_enums.py::GoverningStandardType`. */
export type GoverningStandardType =
  | 'REGULATORY'
  | 'INTERNATIONAL_STANDARD'
  | 'INDUSTRY_GUIDANCE'
  | 'MANAGEMENT_FRAMEWORK'
  | 'CLIENT_STANDARD'
  | 'ORGANIZATION_SPECIFIC'
  | 'OTHER';

/** Mirrors `app/models/enums.py::VerificationStatus` (reused verbatim by
 * GoverningStandard — never a parallel vocabulary). */
export type StandardVerificationStatus = 'PENDING' | 'UNDER_REVIEW' | 'VERIFIED' | 'REJECTED' | 'EXPIRED' | 'SUPERSEDED';

/** Mirrors `app/models/governing_standard_enums.py::OrganizationGoverningStandardStatus`. */
export type OrganizationGoverningStandardStatus = 'SELECTED' | 'RETIRED';

export interface GoverningStandard {
  id: string;
  scope_type: 'GLOBAL' | 'ORGANIZATION';
  organization_id: string | null;
  name: string;
  short_description: string;
  issuing_organization: string;
  standard_type: GoverningStandardType;
  regions: string[];
  industry_sectors: string[];
  version: string | null;
  publication_date: string | null;
  effective_date: string | null;
  verification_status: StandardVerificationStatus;
  is_active: boolean;
}

export interface OrganizationGoverningStandardEntry {
  id: string;
  organization_id: string;
  standard_id: string;
  status: OrganizationGoverningStandardStatus;
  effective_date: string | null;
  retirement_date: string | null;
  rationale: string | null;
  decided_at: string;
  configured_by_user_id: string | null;
  configured_by_api_client_id: string | null;
}

export interface ActiveGoverningStandard {
  standard: GoverningStandard;
  selection: OrganizationGoverningStandardEntry;
}

export interface SelectGoverningStandardInput {
  standardId: string;
  effectiveDate?: string;
  rationale?: string;
}

export interface RetireGoverningStandardInput {
  retirementDate?: string;
  rationale?: string;
}

/** AVAILABLE — the full catalogue (GLOBAL entries + this organization's
 * own ORGANIZATION-scoped entries). Never implies selection. */
export function listAvailableGoverningStandards(organizationId: string, signal?: AbortSignal) {
  return apiRequest<{ items: GoverningStandard[]; total: number }>('/governing-standards', {
    query: { organization_id: organizationId },
    signal,
  });
}

/** SELECTED — the organization's current Active Governing Set. */
export function listActiveGoverningStandards(organizationId: string, signal?: AbortSignal) {
  return apiRequest<{ items: ActiveGoverningStandard[]; total: number }>(
    '/organization-governing-standards',
    { query: { organization_id: organizationId }, signal },
  );
}

export function selectGoverningStandard(
  organizationId: string,
  input: SelectGoverningStandardInput,
  idempotencyKey: string,
  signal?: AbortSignal,
) {
  return apiRequest<OrganizationGoverningStandardEntry>('/organization-governing-standards', {
    method: 'POST',
    query: { organization_id: organizationId },
    headers: { 'Idempotency-Key': idempotencyKey },
    body: {
      standard_id: input.standardId,
      effective_date: input.effectiveDate || null,
      rationale: input.rationale || null,
    },
    signal,
  });
}

export function retireGoverningStandard(
  organizationId: string,
  standardId: string,
  input: RetireGoverningStandardInput,
  idempotencyKey: string,
  signal?: AbortSignal,
) {
  return apiRequest<OrganizationGoverningStandardEntry>(
    `/organization-governing-standards/${standardId}/retire`,
    {
      method: 'POST',
      query: { organization_id: organizationId },
      headers: { 'Idempotency-Key': idempotencyKey },
      body: {
        retirement_date: input.retirementDate || null,
        rationale: input.rationale || null,
      },
      signal,
    },
  );
}

/** The raw, append-only selection/retirement event log — the audit trail. */
export function listGoverningStandardHistory(
  organizationId: string,
  params: { page?: number; pageSize?: number } = {},
  signal?: AbortSignal,
) {
  return apiRequest<{ items: OrganizationGoverningStandardEntry[]; total: number; page: number; page_size: number }>(
    '/organization-governing-standards/history',
    { query: { organization_id: organizationId, page: params.page, page_size: params.pageSize }, signal },
  );
}

// --- API Clients -----------------------------------------------------------------------------

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

/** Only ever returned from create/rotate — the one response shape that
 * includes the raw secret, exactly once (backend's own
 * `ApiClientCreatedRead` — never persisted or re-shown afterward). */
export interface ApiClientCreated extends ApiClient {
  secret: string;
}

export interface CreateApiClientInput {
  name: string;
  /** Each value must be a real `Permission` enum value — the backend
   * rejects the whole request (422) otherwise. No client-invented scope
   * exists here; see `administrationLabels.ts` for the exact vocabulary. */
  scopes: string[];
  expiresAt?: string;
}

export function listApiClients(organizationId: string, signal?: AbortSignal) {
  return apiRequest<ApiClient[]>(`/organizations/${organizationId}/api-clients`, { signal });
}

export function createApiClient(organizationId: string, input: CreateApiClientInput, signal?: AbortSignal) {
  return apiRequest<ApiClientCreated>(`/organizations/${organizationId}/api-clients`, {
    method: 'POST',
    body: {
      name: input.name,
      scopes: input.scopes,
      expires_at: input.expiresAt || null,
    },
    signal,
  });
}

export function rotateApiClientSecret(organizationId: string, clientId: string, signal?: AbortSignal) {
  return apiRequest<ApiClientCreated>(`/organizations/${organizationId}/api-clients/${clientId}/rotate`, {
    method: 'POST',
    signal,
  });
}

export function revokeApiClient(organizationId: string, clientId: string, signal?: AbortSignal) {
  return apiRequest<ApiClient>(`/organizations/${organizationId}/api-clients/${clientId}/revoke`, {
    method: 'POST',
    signal,
  });
}
