import { apiRequest } from './client';

export type KnowledgeScope = 'GLOBAL' | 'ORGANIZATION';
export type VerificationStatus = 'PENDING' | 'VERIFIED' | 'REJECTED';

export interface KnowledgeSource {
  id: string;
  publisher: string;
  name: string;
  source_type: string;
  jurisdiction: string | null;
  industry_sector: string | null;
  authority_level: string | null;
  external_reference: string | null;
  publication_date: string | null;
  review_date: string | null;
  scope_type: KnowledgeScope;
  organization_id: string | null;
  verification_status: VerificationStatus;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeRetrievalResult {
  rank: number;
  chunk_id: string;
  similarity: number;
  relevance: 'HIGH' | 'MODERATE' | 'LOW' | string;
  content: string;
  content_type: string;
  source_id: string;
  document_id: string;
  document_version_id: string;
  source: string;
  document: string;
  version: string;
  location: string | null;
  page_number: number | null;
  section_title: string | null;
  section_path: string[] | null;
  extraction_quality: string;
  extraction_method: string | null;
  source_authority_level: string | null;
  verification_status: VerificationStatus;
  scope: string;
  organization_id: string | null;
  jurisdiction: string | null;
  industry_sector: string | null;
  publication_date: string | null;
  effective_date: string | null;
}

export interface KnowledgeSearchResponse {
  query: string;
  outcome: string;
  embedding_model: {
    provider: string;
    model_name: string;
    model_version: string;
  };
  results: KnowledgeRetrievalResult[];
  result_count: number;
  filters_applied: Record<string, unknown>;
  search_metadata: Record<string, unknown>;
}

export function listKnowledgeSources(
  params: {
    organizationId?: string;
    skip?: number;
    limit?: number;
  },
  signal?: AbortSignal,
): Promise<KnowledgeSource[]> {
  return apiRequest<KnowledgeSource[]>('/knowledge/sources', {
    query: {
      organization_id: params.organizationId,
      skip: params.skip ?? 0,
      limit: params.limit ?? 100,
    },
    signal,
  });
}

export function searchKnowledge(
  organizationId: string,
  query: string,
  params?: {
    topK?: number;
    minSimilarity?: number;
    verificationStatus?: VerificationStatus;
  },
  signal?: AbortSignal,
): Promise<KnowledgeSearchResponse> {
  return apiRequest<KnowledgeSearchResponse>('/knowledge/retrieval/search', {
    method: 'POST',
    body: {
      query,
      top_k: params?.topK ?? 8,
      min_similarity: params?.minSimilarity,
      filters: {
        organization_id: organizationId,
        verification_status: params?.verificationStatus,
      },
    },
    signal,
  });
}
