import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../services/api/errors';
import { KnowledgeQuestionPanel } from './KnowledgeQuestionPanel';

vi.mock('../../services/api/rag', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../services/api/rag')>();
  return { ...actual, askKnowledgeQuestion: vi.fn() };
});

import { askKnowledgeQuestion, RagMalformedResponseError, type RagAnswer } from '../../services/api/rag';

const ORG = 'org-1';

function result(overrides: Partial<RagAnswer> = {}): RagAnswer {
  return {
    organization_id: ORG,
    query: 'What PPE is required?',
    outcome: 'ANSWERED',
    answer: 'A supplied-air respirator is required [E1].',
    explanation: null,
    citations: [
      { citation_id: 'E1', document_id: 'doc-1', source: '29 CFR 1910', document: 'Permit-required confined spaces', version: '2024', location: '1910.146(d)' },
    ],
    as_of: '2026-10-21T00:00:00Z',
    generated_at: '2026-10-21T00:00:01Z',
    ...overrides,
  };
}

async function ask(text = 'What PPE is required?') {
  const user = userEvent.setup();
  render(<KnowledgeQuestionPanel organizationId={ORG} />);
  await user.type(screen.getByLabelText('Your question'), text);
  await user.click(screen.getByRole('button', { name: 'Ask' }));
  return user;
}

describe('KnowledgeQuestionPanel', () => {
  beforeEach(() => vi.clearAllMocks());

  it('does not submit an empty question', () => {
    render(<KnowledgeQuestionPanel organizationId={ORG} />);
    expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled();
  });

  it('shows a loading state while the question is in flight', async () => {
    vi.mocked(askKnowledgeQuestion).mockReturnValueOnce(new Promise(() => {}));
    await ask();
    expect(screen.getByRole('status')).toHaveTextContent('Finding evidence and preparing an answer…');
    expect(screen.getByRole('button', { name: 'Asking…' })).toBeDisabled();
  });

  it('sends the trimmed question for the current organization', async () => {
    vi.mocked(askKnowledgeQuestion).mockResolvedValueOnce(result());
    await ask('  What PPE is required?  ');
    expect(askKnowledgeQuestion).toHaveBeenCalledWith(ORG, 'What PPE is required?', expect.any(AbortSignal));
  });

  it('shows an answer with its cited sources and no confidence claim', async () => {
    vi.mocked(askKnowledgeQuestion).mockResolvedValueOnce(result());
    await ask();
    expect(await screen.findByText('A supplied-air respirator is required [E1].')).toBeInTheDocument();
    const citations = screen.getByRole('list', { name: 'Cited sources' });
    expect(within(citations).getByText('Permit-required confined spaces')).toBeInTheDocument();
    expect(within(citations).getByText('29 CFR 1910 · Version 2024 · 1910.146(d)')).toBeInTheDocument();
    expect(screen.queryByText(/confidence|similarity|%/i)).not.toBeInTheDocument();
  });

  it('shows insufficient evidence explicitly and no answer', async () => {
    vi.mocked(askKnowledgeQuestion).mockResolvedValueOnce(
      result({ outcome: 'INSUFFICIENT_EVIDENCE', answer: null, explanation: 'SIE did not find enough supporting evidence.', citations: [] }),
    );
    await ask();
    expect(await screen.findByRole('heading', { name: 'Not enough evidence to answer' })).toBeInTheDocument();
    expect(screen.getByText('SIE did not find enough supporting evidence.')).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: 'Cited sources' })).not.toBeInTheDocument();
  });

  it('shows a source conflict without choosing a side', async () => {
    vi.mocked(askKnowledgeQuestion).mockResolvedValueOnce(
      result({
        outcome: 'SOURCE_CONFLICT',
        answer: 'E1 requires a supplied-air respirator; E2 allows an air-purifying one.',
        explanation: 'The available sources disagree, so SIE will not pick one.',
        citations: [
          { citation_id: 'E1', document_id: 'd1', source: '29 CFR 1910', document: 'Confined spaces', version: '2024', location: null },
          { citation_id: 'E2', document_id: 'd2', source: 'Company SOP 12', document: 'Respirators', version: '3', location: null },
        ],
      }),
    );
    await ask();
    expect(await screen.findByRole('heading', { name: 'The sources disagree' })).toBeInTheDocument();
    expect(screen.getByText('What the sources say')).toBeInTheDocument();
    expect(screen.getByText(/SIE has not chosen between these sources/)).toBeInTheDocument();
    expect(within(screen.getByRole('list', { name: 'Conflicting sources' })).getAllByRole('listitem')).toHaveLength(2);
    expect(screen.queryByRole('heading', { name: 'Answer' })).not.toBeInTheDocument();
  });

  it.each([
    ['UNSUPPORTED_CLAIM_REJECTED', 'Answer withheld'],
    ['PROVIDER_FAILURE', 'No answer was produced'],
    ['PRIVACY_BLOCKED', 'Blocked by privacy settings'],
  ] as const)('shows %s as its own state, with no citations', async (outcome, heading) => {
    vi.mocked(askKnowledgeQuestion).mockResolvedValueOnce(result({ outcome, answer: null, explanation: 'Why.' }));
    await ask();
    expect(await screen.findByRole('heading', { name: heading })).toBeInTheDocument();
    expect(screen.getByText('Why.')).toBeInTheDocument();
    expect(screen.queryByText('Permit-required confined spaces')).not.toBeInTheDocument();
  });

  it.each([
    [new ApiError('Evidence-grounded RAG query is not available in Public SIE: … M43-IP-03 …', { status: 501 }), 'Question answering is not available'],
    [new ApiError('x', { status: 503, details: { reason: 'RAG_NOT_ENABLED', retryable: false } }), 'Question answering is not switched on'],
    [new ApiError('Commercial Core did not respond in time.', { status: 503, details: { retryable: true } }), 'Question answering is temporarily unavailable'],
    [new ApiError('x', { status: 403 }), "You don't have permission to ask questions here"],
    [new ApiError('x', { status: 0 }), 'Could not reach SIE'],
    [new RagMalformedResponseError(), 'The response could not be read'],
    [new Error('provider=acme key=sk-live'), 'The question could not be answered'],
  ])('shows a fixed message for %o and never the server text', async (error, title) => {
    vi.mocked(askKnowledgeQuestion).mockRejectedValueOnce(error);
    await ask();
    expect(await screen.findByText(title)).toBeInTheDocument();
    expect(screen.queryByText(/Commercial Core|M43-IP-03|sk-live|acme/)).not.toBeInTheDocument();
  });

  it('retries a temporary failure', async () => {
    vi.mocked(askKnowledgeQuestion)
      .mockRejectedValueOnce(new ApiError('x', { status: 503 }))
      .mockResolvedValueOnce(result());
    const user = await ask();
    await user.click(await screen.findByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('A supplied-air respirator is required [E1].')).toBeInTheDocument();
    expect(askKnowledgeQuestion).toHaveBeenCalledTimes(2);
  });

  it('clears a previous organization’s answer when the organization changes', async () => {
    vi.mocked(askKnowledgeQuestion).mockResolvedValueOnce(result());
    const user = userEvent.setup();
    const { rerender } = render(<KnowledgeQuestionPanel organizationId={ORG} />);
    await user.type(screen.getByLabelText('Your question'), 'q');
    await user.click(screen.getByRole('button', { name: 'Ask' }));
    expect(await screen.findByText('A supplied-air respirator is required [E1].')).toBeInTheDocument();
    rerender(<KnowledgeQuestionPanel organizationId="org-2" />);
    await waitFor(() => expect(screen.queryByText('A supplied-air respirator is required [E1].')).not.toBeInTheDocument());
  });
});
