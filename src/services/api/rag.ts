import { apiRequest } from './client';
import { ApiError } from './errors';

/**
 * Evidence-grounded question answering — `POST /knowledge/rag/query`
 * (Roadmap Phase 2, item 4).
 *
 * The response mirrors `sie_contract.RAGAnswerDTO` (contract 0.8.0,
 * Commercial Core PR #19), flattened by `backend/app/schemas/rag.py`.
 *
 * Deliberately absent: similarity scores, source-authority and
 * extraction-quality signals, evidence counts, provider/model names,
 * prompt or retrieval metadata. The backend never sends them and this
 * type gives a caller nowhere to put them.
 */
export const RAG_OUTCOMES = [
  'ANSWERED',
  'INSUFFICIENT_EVIDENCE',
  'SOURCE_CONFLICT',
  'UNSUPPORTED_CLAIM_REJECTED',
  'PROVIDER_FAILURE',
  'PRIVACY_BLOCKED',
] as const;

export type RagOutcome = (typeof RAG_OUTCOMES)[number];

export interface RagCitation {
  citation_id: string;
  document_id: string;
  source: string;
  document: string;
  version: string;
  location: string | null;
}

export interface RagAnswer {
  organization_id: string;
  query: string;
  outcome: RagOutcome;
  answer: string | null;
  explanation: string | null;
  citations: RagCitation[];
  as_of: string;
  generated_at: string;
}

/** The backend answered 200 but the body does not have the RAG answer
 * shape, or breaks its outcome rules (an ANSWERED with no text, an
 * abstention carrying answer text). Never shown as an answer. */
export class RagMalformedResponseError extends Error {
  constructor() {
    super('The answer service returned a response SIE could not read.');
    this.name = 'RagMalformedResponseError';
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

function isNullableString(value: unknown): value is string | null {
  return value === null || value === undefined || typeof value === 'string';
}

function parseCitation(value: unknown): RagCitation {
  if (
    !isObject(value) ||
    !isNonEmptyString(value.citation_id) ||
    !isNonEmptyString(value.document_id) ||
    typeof value.source !== 'string' ||
    typeof value.document !== 'string' ||
    typeof value.version !== 'string' ||
    !isNullableString(value.location)
  ) {
    throw new RagMalformedResponseError();
  }
  // Only the identity fields are copied: anything else the response
  // might carry is dropped here rather than passed on to the UI.
  return {
    citation_id: value.citation_id,
    document_id: value.document_id,
    source: value.source,
    document: value.document,
    version: value.version,
    location: value.location ?? null,
  };
}

/** Validates a raw response against the RAG answer rules — the same
 * rules `RAGAnswerDTO`'s own validator enforces server-side, checked
 * again here so a malformed body is never rendered as an answer. */
export function parseRagAnswer(raw: unknown, expectedOrganizationId: string): RagAnswer {
  if (!isObject(raw)) throw new RagMalformedResponseError();
  const outcome = raw.outcome;
  if (typeof outcome !== 'string' || !(RAG_OUTCOMES as readonly string[]).includes(outcome)) {
    throw new RagMalformedResponseError();
  }
  if (raw.organization_id !== expectedOrganizationId) throw new RagMalformedResponseError();
  if (typeof raw.query !== 'string' || typeof raw.as_of !== 'string' || typeof raw.generated_at !== 'string') {
    throw new RagMalformedResponseError();
  }
  if (!isNullableString(raw.answer) || !isNullableString(raw.explanation) || !Array.isArray(raw.citations)) {
    throw new RagMalformedResponseError();
  }
  const answer = raw.answer ?? null;
  const explanation = raw.explanation ?? null;

  if (outcome === 'ANSWERED') {
    if (!isNonEmptyString(answer)) throw new RagMalformedResponseError();
  } else {
    if (!isNonEmptyString(explanation)) throw new RagMalformedResponseError();
    if (outcome !== 'SOURCE_CONFLICT' && answer !== null) throw new RagMalformedResponseError();
  }

  return {
    organization_id: raw.organization_id,
    query: raw.query,
    outcome: outcome as RagOutcome,
    answer,
    explanation,
    citations: raw.citations.map(parseCitation),
    as_of: raw.as_of,
    generated_at: raw.generated_at,
  };
}

export async function askKnowledgeQuestion(
  organizationId: string,
  query: string,
  signal?: AbortSignal,
): Promise<RagAnswer> {
  let raw: unknown;
  try {
    raw = await apiRequest<unknown>('/knowledge/rag/query', {
      method: 'POST',
      body: { query, filters: { organization_id: organizationId } },
      signal,
    });
  } catch (error) {
    // `apiRequest` parses a 2xx body with JSON.parse; a non-JSON body
    // surfaces as a SyntaxError, which is a malformed response too.
    if (error instanceof SyntaxError) throw new RagMalformedResponseError();
    throw error;
  }
  return parseRagAnswer(raw, organizationId);
}

/** Why a question could not be answered at all — distinct from an
 * abstention, which is a successful response with its own `outcome`. */
export type RagFailureKind =
  | 'not-available'
  | 'not-enabled'
  | 'temporarily-unavailable'
  | 'permission-denied'
  | 'invalid-question'
  | 'network'
  | 'malformed'
  | 'failed';

export function classifyRagFailure(error: unknown): RagFailureKind {
  if (error instanceof RagMalformedResponseError) return 'malformed';
  if (!(error instanceof ApiError)) return 'failed';
  if (error.isNetworkError) return 'network';
  if (error.status === 501) return 'not-available';
  if (error.status === 403) return 'permission-denied';
  if (error.status === 422) return 'invalid-question';
  if (error.status === 503) return error.details?.reason === 'RAG_NOT_ENABLED' ? 'not-enabled' : 'temporarily-unavailable';
  return 'failed';
}
