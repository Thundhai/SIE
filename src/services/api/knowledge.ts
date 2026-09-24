import { apiRequest } from './client';

export type KnowledgeScope = 'GLOBAL' | 'ORGANIZATION';
export type VerificationStatus = 'PENDING' | 'UNDER_REVIEW' | 'VERIFIED' | 'REJECTED' | 'EXPIRED' | 'SUPERSEDED';

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

export interface CreateKnowledgeSourceInput {
  publisher: string;
  name: string;
  sourceType: string;
  jurisdiction?: string;
  industrySector?: string;
  authorityLevel?: string;
  externalReference?: string;
  publicationDate?: string;
  reviewDate?: string;
  /** GLOBAL requires platform-wide `knowledge:manage` (human callers
   * only) — `organizationId` must be omitted for it. ORGANIZATION
   * requires `knowledge:manage` in that organization. */
  scopeType: KnowledgeScope;
  organizationId?: string;
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

export function createKnowledgeSource(input: CreateKnowledgeSourceInput, signal?: AbortSignal): Promise<KnowledgeSource> {
  return apiRequest<KnowledgeSource>('/knowledge/sources', {
    method: 'POST',
    body: {
      publisher: input.publisher,
      name: input.name,
      source_type: input.sourceType,
      jurisdiction: input.jurisdiction || null,
      industry_sector: input.industrySector || null,
      authority_level: input.authorityLevel || null,
      external_reference: input.externalReference || null,
      publication_date: input.publicationDate || null,
      review_date: input.reviewDate || null,
      scope_type: input.scopeType,
      organization_id: input.scopeType === 'ORGANIZATION' ? input.organizationId : undefined,
    },
    signal,
  });
}

// --- Documents / versions / chunks (read side) ----------------------------------------------
// No `GET /knowledge/documents?source_id=...` list endpoint exists on the
// backend (`backend/app/api/v1/knowledge.py` only exposes a single-document
// GET by id) — a document is reached by an id already known, e.g. from a
// search result's `document_id`, never browsed from a source directly.

export interface KnowledgeDocument {
  id: string;
  source_id: string;
  organization_id: string | null;
  title: string;
  document_type: string;
  description: string | null;
  language: string | null;
  external_document_id: string | null;
  current_version_id: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export type IngestionStatus = 'RECEIVED' | 'PROCESSING' | 'PROCESSED' | 'FAILED' | 'ARCHIVED';

export interface KnowledgeDocumentVersion {
  id: string;
  document_id: string;
  version_label: string;
  content_hash: string;
  storage_reference: string;
  extracted_text: string | null;
  publication_date: string | null;
  effective_date: string | null;
  superseded_at: string | null;
  ingestion_status: IngestionStatus;
  created_at: string;
}

export type ContentType = 'text' | 'table' | 'image' | 'structured_record';
export type ExtractionMethod = 'TEXT_EXTRACTION' | 'STRUCTURED_PARSE' | 'OCR' | 'NONE';
export type QualityStatus = 'HIGH' | 'MEDIUM' | 'LOW' | 'INSUFFICIENT';

export interface KnowledgeChunk {
  id: string;
  document_version_id: string;
  document_id: string | null;
  source_id: string | null;
  organization_id: string | null;
  chunk_index: number;
  content: string;
  character_count: number;
  content_type: ContentType;
  page_number: number | null;
  sheet_name: string | null;
  row_number: number | null;
  slide_number: number | null;
  section_title: string | null;
  section_path: string[] | null;
  source_reference: string | null;
  extraction_method: ExtractionMethod | null;
  quality_status: QualityStatus;
  chunk_metadata: Record<string, unknown> | null;
  created_at: string;
}

/** `organizationId` must be supplied (and match the document's own) to
 * reach an ORGANIZATION-scoped document; omit it only for a GLOBAL one —
 * exactly the same contract the backend route documents. */
export function getKnowledgeDocument(documentId: string, organizationId: string | null, signal?: AbortSignal): Promise<KnowledgeDocument> {
  return apiRequest<KnowledgeDocument>(`/knowledge/documents/${documentId}`, {
    query: { organization_id: organizationId ?? undefined },
    signal,
  });
}

export function listKnowledgeDocumentVersions(
  documentId: string,
  organizationId: string | null,
  params: { skip?: number; limit?: number } = {},
  signal?: AbortSignal,
): Promise<KnowledgeDocumentVersion[]> {
  return apiRequest<KnowledgeDocumentVersion[]>(`/knowledge/documents/${documentId}/versions`, {
    query: { organization_id: organizationId ?? undefined, skip: params.skip ?? 0, limit: params.limit ?? 100 },
    signal,
  });
}

export function listKnowledgeChunks(
  documentId: string,
  versionId: string,
  organizationId: string | null,
  params: { skip?: number; limit?: number } = {},
  signal?: AbortSignal,
): Promise<KnowledgeChunk[]> {
  return apiRequest<KnowledgeChunk[]>(`/knowledge/documents/${documentId}/versions/${versionId}/chunks`, {
    query: { organization_id: organizationId ?? undefined, skip: params.skip ?? 0, limit: params.limit ?? 200 },
    signal,
  });
}

// --- Ingestion (document upload) -------------------------------------------------------------

export interface IngestDocumentInput {
  file: File;
  sourceId: string;
  /** Omit for a GLOBAL source, matching the source's own scope. */
  organizationId?: string;
  /** Attach this upload as a new version of an existing document instead
   * of creating one — must belong to `sourceId`. */
  documentId?: string;
  /** Required when `documentId` is omitted (a new document is created
   * and needs a name) — mirrors `IngestionService._resolve_document`'s
   * own validation, checked here too so the error surfaces before an
   * upload is attempted, not just after. */
  title?: string;
  documentType?: string;
}

export type ExtractionStatus = 'PENDING' | 'SUCCEEDED' | 'PARTIAL' | 'FAILED';
export type IngestionJobStatus = 'RECEIVED' | 'VALIDATING' | 'PROCESSING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';

export interface IngestionResult {
  ingestion_job_id: string;
  file_id: string;
  detected_media_type: string;
  file_size: number;
  content_hash: string;
  ingestion_status: IngestionJobStatus;
  extraction_status: ExtractionStatus;
  extraction_method: ExtractionMethod | null;
  document_id: string | null;
  version_id: string | null;
  chunk_count: number;
  warnings: string[];
}

export function ingestDocument(input: IngestDocumentInput, signal?: AbortSignal): Promise<IngestionResult> {
  const formData = new FormData();
  formData.set('file', input.file);
  formData.set('source_id', input.sourceId);
  if (input.organizationId) formData.set('organization_id', input.organizationId);
  if (input.documentId) formData.set('document_id', input.documentId);
  if (input.title) formData.set('title', input.title);
  if (input.documentType) formData.set('document_type', input.documentType);

  return apiRequest<IngestionResult>('/knowledge/ingestion', {
    method: 'POST',
    body: formData,
    signal,
  });
}

// --- Retrieval (evidence search) -----------------------------------------------------------

export interface KnowledgeRetrievalResult {
  rank: number;
  chunk_id: string;
  /** Cosine similarity to the query, in [-1, 1] — a vector-closeness
   * measure of evidence relevance, never a confidence or truth score. */
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
  sheet_name: string | null;
  row_number: number | null;
  slide_number: number | null;
  section_title: string | null;
  section_path: string[] | null;
  extraction_quality: string;
  extraction_method: string | null;
  source_authority_level: string | null;
  verification_status: VerificationStatus;
  scope: KnowledgeScope | string;
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
