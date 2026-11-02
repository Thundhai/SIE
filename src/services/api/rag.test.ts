import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiRequest } from './client';
import { ApiError } from './errors';
import { askKnowledgeQuestion, classifyRagFailure, parseRagAnswer, RagMalformedResponseError } from './rag';

vi.mock('./client', () => ({
  apiRequest: vi.fn(),
}));

const ORG = 'org-1';
const QUERY = 'What PPE is required?';

function answer(overrides: Record<string, unknown> = {}) {
  return {
    organization_id: ORG,
    query: 'What PPE is required?',
    outcome: 'ANSWERED',
    answer: 'A supplied-air respirator [E1].',
    explanation: null,
    citations: [
      { citation_id: 'E1', document_id: 'doc-1', source: '29 CFR 1910', document: 'Confined spaces', version: '2024', location: '1910.146' },
    ],
    as_of: '2026-10-21T00:00:00Z',
    generated_at: '2026-10-21T00:00:01Z',
    ...overrides,
  };
}

describe('askKnowledgeQuestion', () => {
  beforeEach(() => vi.clearAllMocks());

  it('sends only the question and the organization filter', async () => {
    vi.mocked(apiRequest).mockResolvedValueOnce(answer());
    const result = await askKnowledgeQuestion(ORG, 'What PPE is required?');
    expect(result.outcome).toBe('ANSWERED');
    expect(apiRequest).toHaveBeenCalledWith('/knowledge/rag/query', {
      method: 'POST',
      body: { query: 'What PPE is required?', filters: { organization_id: ORG } },
      signal: undefined,
    });
  });

  it('treats a non-JSON success body as malformed', async () => {
    vi.mocked(apiRequest).mockRejectedValueOnce(new SyntaxError('Unexpected token'));
    await expect(askKnowledgeQuestion(ORG, 'q')).rejects.toBeInstanceOf(RagMalformedResponseError);
  });

  it('passes API errors through unchanged', async () => {
    const error = new ApiError('x', { status: 501 });
    vi.mocked(apiRequest).mockRejectedValueOnce(error);
    await expect(askKnowledgeQuestion(ORG, 'q')).rejects.toBe(error);
  });
});

describe('parseRagAnswer', () => {
  it('keeps only citation identity fields', () => {
    const raw = answer({
      citations: [
        { citation_id: 'E1', document_id: 'd', source: 's', document: 'doc', version: 'v', location: null, similarity: 0.91, source_authority_level: 'HIGH' },
      ],
      model_metadata: { provider: 'acme' },
    });
    const result = parseRagAnswer(raw, ORG, QUERY);
    expect(result.citations[0]).toEqual({ citation_id: 'E1', document_id: 'd', source: 's', document: 'doc', version: 'v', location: null });
    expect(result).not.toHaveProperty('model_metadata');
  });

  it('accepts a source conflict that describes the disagreement', () => {
    const result = parseRagAnswer(answer({ outcome: 'SOURCE_CONFLICT', answer: 'E1 and E2 disagree.', explanation: 'Sources disagree.' }), ORG, QUERY);
    expect(result.outcome).toBe('SOURCE_CONFLICT');
  });

  it('accepts an abstention with an explanation and no answer', () => {
    const result = parseRagAnswer(answer({ outcome: 'INSUFFICIENT_EVIDENCE', answer: null, explanation: 'Not enough evidence.', citations: [] }), ORG, QUERY);
    expect(result.answer).toBeNull();
  });

  it.each([
    ['ANSWERED with no answer', answer({ answer: null })],
    ['ANSWERED with blank answer', answer({ answer: '   ' })],
    ['abstention with no explanation', answer({ outcome: 'INSUFFICIENT_EVIDENCE', answer: null, explanation: null })],
    ['abstention carrying answer text', answer({ outcome: 'PRIVACY_BLOCKED', answer: 'Made up.', explanation: 'Blocked.' })],
    ['unknown outcome', answer({ outcome: 'MAYBE' })],
    ['another organization', answer({ organization_id: 'org-2' })],
    ['citations not an array', answer({ citations: null })],
    ['citation missing identity', answer({ citations: [{ citation_id: 'E1' }] })],
    ['ANSWERED citing nothing', answer({ citations: [] })],
    ['an answer to a different question', answer({ query: 'Something else?' })],
    ['not an object', ['a']],
    ['null', null],
  ])('rejects %s', (_label, raw) => {
    expect(() => parseRagAnswer(raw, ORG, QUERY)).toThrow(RagMalformedResponseError);
  });
});

describe('classifyRagFailure', () => {
  it.each([
    [new ApiError('x', { status: 501 }), 'not-available'],
    [new ApiError('x', { status: 503, details: { reason: 'RAG_NOT_ENABLED', retryable: false } }), 'not-enabled'],
    [new ApiError('x', { status: 503, details: { retryable: true } }), 'temporarily-unavailable'],
    [new ApiError('x', { status: 503 }), 'temporarily-unavailable'],
    [new ApiError('x', { status: 403 }), 'permission-denied'],
    [new ApiError('x', { status: 422 }), 'invalid-question'],
    [new ApiError('x', { status: 0 }), 'network'],
    [new ApiError('x', { status: 500 }), 'failed'],
    [new RagMalformedResponseError(), 'malformed'],
    [new Error('boom'), 'failed'],
  ])('classifies %o as %s', (error, kind) => {
    expect(classifyRagFailure(error)).toBe(kind);
  });
});
