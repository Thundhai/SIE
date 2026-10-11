/**
 * Learning Integration service — SIE Milestone 41/42. Thin typed
 * wrappers around `GET /intelligence/memory-context` and
 * `GET /intelligence/sites/{site_id}/memory-context`
 * (`backend/app/api/v1/intelligence.py`). Mirrors
 * `MemoryIntegrationContextRead`/`IntegratedMemoryRead`
 * (`backend/app/schemas/memory_integration.py`) field-for-field.
 *
 * The frontend never computes memory applicability itself — every field
 * here (`applicability_basis`, `governance_status`, `memory_created_at`,
 * provenance ids) is exactly what
 * `resolve_eligible_organizational_memories()` already determined
 * server-side (SIE Milestone 42 spec §11: "The frontend must not
 * independently perform its own memory applicability algorithm").
 */
import { apiRequest } from './client';

/** Mirrors `app/models/organizational_memory_enums.py::OrganizationalMemoryType`. */
export type OrganizationalMemoryType =
  | 'LESSON_LEARNED'
  | 'EFFECTIVE_PRACTICE'
  | 'FAILED_APPROACH'
  | 'EARLY_WARNING_PATTERN'
  | 'CONTROL_INSIGHT';

export type MemoryApplicabilityBasis =
  | 'ORGANIZATION_WIDE'
  | 'SITE_MATCH'
  | 'PROJECT_SITE_MATCH'
  | 'ORGANIZATION_SCOPE_ROLLUP';

export interface IntegratedMemory {
  memory_id: string;
  memory_type: OrganizationalMemoryType;
  title: string;
  memory_content: string;
  rationale: string;
  memory_created_at: string;
  learning_candidate_id: string;
  outcome_id: string;
  verification_id: string;
  outcome_site_id: string | null;
  applicability_basis: MemoryApplicabilityBasis;
  governance_status: string;
  governance_is_explicit: boolean;
  governance_decided_at: string | null;
}

export interface MemoryIntegrationContext {
  scope: string;
  organization_id: string;
  entity_id: string | null;
  project_id: string | null;
  as_of: string;
  generated_at: string;
  items: IntegratedMemory[];
  total: number;
  page: number;
  page_size: number;
  calculation_version: string;
}

export function getMemoryContext(
  params: { organizationId: string; asOf?: string; projectId?: string; page?: number; pageSize?: number },
  signal?: AbortSignal,
): Promise<MemoryIntegrationContext> {
  return apiRequest<MemoryIntegrationContext>('/intelligence/memory-context', {
    query: {
      organization_id: params.organizationId,
      as_of: params.asOf,
      project_id: params.projectId,
      page: params.page,
      page_size: params.pageSize,
    },
    signal,
  });
}

export function getSiteMemoryContext(
  params: { organizationId: string; siteId: string; asOf?: string; page?: number; pageSize?: number },
  signal?: AbortSignal,
): Promise<MemoryIntegrationContext> {
  return apiRequest<MemoryIntegrationContext>(`/intelligence/sites/${params.siteId}/memory-context`, {
    query: { organization_id: params.organizationId, as_of: params.asOf, page: params.page, page_size: params.pageSize },
    signal,
  });
}
