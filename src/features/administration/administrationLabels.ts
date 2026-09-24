import type { StatusTone } from '../../types/common';
import { formatCanonicalLabel } from '../events/eventStatus';

/**
 * Plain-language presentation for Administration's governed backend
 * vocabularies — following `intelligenceLabels.ts`'s own precedent: map
 * known values, fall back to `formatCanonicalLabel()` for anything
 * unmapped, never hide or coerce a value.
 */

// --- Governing standard type (GoverningStandardType) -------------------------------------------

const STANDARD_TYPE_LABEL: Record<string, string> = {
  REGULATORY: 'Regulatory',
  INTERNATIONAL_STANDARD: 'International standard',
  INDUSTRY_GUIDANCE: 'Industry guidance',
  MANAGEMENT_FRAMEWORK: 'Management framework',
  CLIENT_STANDARD: 'Client standard',
  ORGANIZATION_SPECIFIC: 'Organization-specific',
  OTHER: 'Other',
};

export function standardTypeLabel(value: string): string {
  return STANDARD_TYPE_LABEL[value] ?? formatCanonicalLabel(value);
}

// --- Standard verification status (VerificationStatus, reused from KnowledgeSource) -------------

const VERIFICATION_STATUS_LABEL: Record<string, string> = {
  PENDING: 'Pending',
  UNDER_REVIEW: 'Under review',
  VERIFIED: 'Verified',
  REJECTED: 'Rejected',
  EXPIRED: 'Expired',
  SUPERSEDED: 'Superseded',
};

const VERIFICATION_STATUS_TONE: Record<string, StatusTone> = {
  PENDING: 'neutral',
  UNDER_REVIEW: 'informational',
  VERIFIED: 'success',
  REJECTED: 'critical',
  EXPIRED: 'warning',
  SUPERSEDED: 'warning',
};

export function standardVerificationStatusLabel(value: string): string {
  return VERIFICATION_STATUS_LABEL[value] ?? formatCanonicalLabel(value);
}

export function standardVerificationStatusTone(value: string): StatusTone {
  return VERIFICATION_STATUS_TONE[value] ?? 'neutral';
}

// --- Organization governing standard status (SELECTED / RETIRED) -------------------------------

const SELECTION_STATUS_LABEL: Record<string, string> = {
  SELECTED: 'Selected',
  RETIRED: 'Retired',
};

const SELECTION_STATUS_TONE: Record<string, StatusTone> = {
  SELECTED: 'success',
  RETIRED: 'neutral',
};

export function selectionStatusLabel(value: string): string {
  return SELECTION_STATUS_LABEL[value] ?? formatCanonicalLabel(value);
}

export function selectionStatusTone(value: string): StatusTone {
  return SELECTION_STATUS_TONE[value] ?? 'neutral';
}

// --- Organization role (OrganizationRole) -------------------------------------------------------

const ROLE_LABEL: Record<string, string> = {
  ORG_ADMIN: 'Organization admin',
  HSE_MANAGER: 'HSE manager',
  HSE_ANALYST: 'HSE analyst',
  HSE_USER: 'HSE user',
  VIEWER: 'Viewer',
};

export function organizationRoleLabel(value: string): string {
  return ROLE_LABEL[value] ?? formatCanonicalLabel(value);
}

export const ORGANIZATION_ROLE_OPTIONS: { value: string; label: string }[] = [
  { value: 'ORG_ADMIN', label: ROLE_LABEL.ORG_ADMIN },
  { value: 'HSE_MANAGER', label: ROLE_LABEL.HSE_MANAGER },
  { value: 'HSE_ANALYST', label: ROLE_LABEL.HSE_ANALYST },
  { value: 'HSE_USER', label: ROLE_LABEL.HSE_USER },
  { value: 'VIEWER', label: ROLE_LABEL.VIEWER },
];

// --- Membership status (MembershipStatus) --------------------------------------------------------

const MEMBERSHIP_STATUS_LABEL: Record<string, string> = {
  ACTIVE: 'Active',
  SUSPENDED: 'Suspended',
  INVITED: 'Invited',
  REVOKED: 'Revoked',
};

const MEMBERSHIP_STATUS_TONE: Record<string, StatusTone> = {
  ACTIVE: 'success',
  SUSPENDED: 'warning',
  INVITED: 'informational',
  REVOKED: 'critical',
};

export function membershipStatusLabel(value: string): string {
  return MEMBERSHIP_STATUS_LABEL[value] ?? formatCanonicalLabel(value);
}

export function membershipStatusTone(value: string): StatusTone {
  return MEMBERSHIP_STATUS_TONE[value] ?? 'neutral';
}

export const MEMBERSHIP_STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: 'ACTIVE', label: MEMBERSHIP_STATUS_LABEL.ACTIVE },
  { value: 'SUSPENDED', label: MEMBERSHIP_STATUS_LABEL.SUSPENDED },
  { value: 'INVITED', label: MEMBERSHIP_STATUS_LABEL.INVITED },
  { value: 'REVOKED', label: MEMBERSHIP_STATUS_LABEL.REVOKED },
];

// --- API client status ---------------------------------------------------------------------------

const API_CLIENT_STATUS_TONE: Record<string, StatusTone> = {
  ACTIVE: 'success',
  REVOKED: 'critical',
  EXPIRED: 'warning',
};

export function apiClientStatusTone(value: string): StatusTone {
  return API_CLIENT_STATUS_TONE[value] ?? 'neutral';
}

// --- Permission scope vocabulary (app/services/permissions.py::Permission) -----------------------
// The exact, real, closed set of scopes an API client can be granted —
// never an invented vocabulary. Grouped only for readability; the value
// sent to the backend is always the raw permission string.

export const PERMISSION_SCOPE_OPTIONS: { value: string; label: string }[] = [
  { value: 'organization:read', label: 'Organization — read' },
  { value: 'organization:manage', label: 'Organization — manage' },
  { value: 'site:read', label: 'Sites — read' },
  { value: 'site:manage', label: 'Sites — manage' },
  { value: 'knowledge:read', label: 'Knowledge — read' },
  { value: 'knowledge:manage', label: 'Knowledge — manage' },
  { value: 'knowledge:verify', label: 'Knowledge — verify' },
  { value: 'safety_data:read', label: 'Safety data — read' },
  { value: 'safety_data:write', label: 'Safety data — write' },
  { value: 'intelligence:read', label: 'Intelligence — read' },
  { value: 'prediction:read', label: 'Predictions — read' },
  { value: 'intervention:read', label: 'Actions — read' },
  { value: 'intervention:manage', label: 'Actions — manage' },
  { value: 'intervention:assign', label: 'Actions — assign' },
  { value: 'intervention:close', label: 'Actions — close' },
  { value: 'governance:read', label: 'Model governance — read' },
  { value: 'governance:manage', label: 'Model governance — manage' },
  { value: 'users:read', label: 'Users & administration — read' },
  { value: 'users:manage', label: 'Users & administration — manage' },
  { value: 'risk_assessment:read', label: 'Risk assessments — read' },
  { value: 'risk_assessment:write', label: 'Risk assessments — write' },
  { value: 'risk_assessment:approve', label: 'Risk assessments — approve' },
  { value: 'intelligence:decision_write', label: 'Intelligence decisions — write' },
  { value: 'project:read', label: 'Projects — read' },
  { value: 'project:manage', label: 'Projects — manage' },
  { value: 'standards:read', label: 'Governing standards — read' },
  { value: 'standards:manage', label: 'Governing standards — manage' },
];
