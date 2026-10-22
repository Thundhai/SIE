import { MessageSquareText } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Section } from '../../components/layout/Section';
import { Button } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { LoadingState } from '../../components/ui/LoadingState';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { Textarea } from '../../components/ui/Textarea';
import {
  askKnowledgeQuestion,
  classifyRagFailure,
  type RagAnswer,
  type RagCitation,
  type RagFailureKind,
  type RagOutcome,
} from '../../services/api/rag';
import type { StatusTone } from '../../types/common';

const MAX_QUESTION_LENGTH = 2000;

type PanelState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'answered'; result: RagAnswer }
  | { status: 'failed'; kind: RagFailureKind };

const OUTCOME_PRESENTATION: Record<RagOutcome, { badge: string; tone: StatusTone; title: string }> = {
  ANSWERED: { badge: 'Answered with citations', tone: 'informational', title: 'Answer' },
  SOURCE_CONFLICT: { badge: 'Sources disagree', tone: 'warning', title: 'The sources disagree' },
  INSUFFICIENT_EVIDENCE: { badge: 'Not enough evidence', tone: 'neutral', title: 'Not enough evidence to answer' },
  UNSUPPORTED_CLAIM_REJECTED: { badge: 'Answer withheld', tone: 'warning', title: 'Answer withheld' },
  PROVIDER_FAILURE: { badge: 'No answer produced', tone: 'critical', title: 'No answer was produced' },
  PRIVACY_BLOCKED: { badge: 'Blocked by privacy settings', tone: 'neutral', title: 'Blocked by privacy settings' },
};

// Fixed wording per failure. The backend's own error message is never
// shown here, so nothing it might say about its dependencies reaches the
// page.
const FAILURE_PRESENTATION: Record<RagFailureKind, { title: string; description: string; retry: boolean; calm: boolean }> = {
  'not-available': {
    title: 'Question answering is not available',
    description: 'Evidence-grounded question answering is not available on this deployment. Knowledge search below still works.',
    retry: false,
    calm: true,
  },
  'not-enabled': {
    title: 'Question answering is not switched on',
    description: 'Question answering has not been enabled for this deployment yet. An administrator needs to turn it on.',
    retry: false,
    calm: true,
  },
  'temporarily-unavailable': {
    title: 'Question answering is temporarily unavailable',
    description: 'SIE could not reach its answer service. No answer was produced. Please try again shortly.',
    retry: true,
    calm: false,
  },
  'permission-denied': {
    title: "You don't have permission to ask questions here",
    description: 'Ask an administrator for knowledge:read access in this organization.',
    retry: false,
    calm: true,
  },
  'invalid-question': {
    title: 'This question could not be accepted',
    description: `Check that the question is between 1 and ${MAX_QUESTION_LENGTH.toLocaleString()} characters, then try rephrasing it.`,
    retry: false,
    calm: false,
  },
  network: {
    title: 'Could not reach SIE',
    description: 'Check your connection and try again.',
    retry: true,
    calm: false,
  },
  malformed: {
    title: 'The response could not be read',
    description: 'SIE received a response it could not read, so no answer is shown. Please try again.',
    retry: true,
    calm: false,
  },
  failed: {
    title: 'The question could not be answered',
    description: 'Something went wrong while asking this question. No answer was produced. Please try again.',
    retry: true,
    calm: false,
  },
};

function CitationList({ citations, label }: { citations: RagCitation[]; label: string }) {
  if (citations.length === 0) return null;
  return (
    <div className="mt-4">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-text-muted">{label}</h4>
      <ol className="mt-2 flex flex-col gap-2" aria-label={label}>
        {citations.map((citation) => (
          <li key={`${citation.citation_id}-${citation.document_id}`} className="flex gap-3 rounded-md border border-border bg-surface p-3">
            <span className="shrink-0 rounded bg-neutral-status-surface px-1.5 py-0.5 font-mono text-xs text-text-secondary">
              {citation.citation_id}
            </span>
            <div className="min-w-0">
              <p className="break-words text-sm font-medium text-text-primary">{citation.document}</p>
              <p className="mt-0.5 break-words text-xs text-text-muted">
                {citation.source} · Version {citation.version}
                {citation.location ? ` · ${citation.location}` : ''}
              </p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

function RagResult({ result, onRetry }: { result: RagAnswer; onRetry: () => void }) {
  const presentation = OUTCOME_PRESENTATION[result.outcome];
  const isAnswer = result.outcome === 'ANSWERED';
  const isConflict = result.outcome === 'SOURCE_CONFLICT';

  return (
    <article className="rounded-lg border border-border bg-surface p-4" aria-labelledby="rag-result-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="rag-result-title" className="text-sm font-semibold text-text-primary">
          {presentation.title}
        </h3>
        <StatusBadge tone={presentation.tone} label={presentation.badge} />
      </div>
      <p className="mt-1 break-words text-xs text-text-muted">Question: {result.query}</p>

      {isAnswer && result.answer && (
        <p className="mt-3 whitespace-pre-line break-words text-sm leading-relaxed text-text-primary">{result.answer}</p>
      )}

      {!isAnswer && result.explanation && (
        <p className="mt-3 text-sm leading-relaxed text-text-secondary">{result.explanation}</p>
      )}

      {isConflict && result.answer && (
        <div className="mt-3 rounded-md border border-warning/30 bg-warning-surface p-3">
          <h4 className="text-xs font-semibold text-text-primary">What the sources say</h4>
          <p className="mt-1 whitespace-pre-line break-words text-sm leading-relaxed text-text-primary">{result.answer}</p>
        </div>
      )}
      {isConflict && (
        <p className="mt-3 text-xs text-text-secondary">SIE has not chosen between these sources. Review them and decide which applies.</p>
      )}

      {/* Citations are shown only where they support (ANSWERED) or
          identify (SOURCE_CONFLICT) what is displayed. For a withheld or
          abstained answer they would read as support for an answer that
          was never given. */}
      {isAnswer && <CitationList citations={result.citations} label="Cited sources" />}
      {isConflict && <CitationList citations={result.citations} label="Conflicting sources" />}

      {result.outcome === 'PROVIDER_FAILURE' && (
        <Button variant="secondary" size="sm" onClick={onRetry} className="mt-3">
          Try again
        </Button>
      )}

      {isAnswer && (
        <p className="mt-4 text-xs text-text-muted">
          Generated from the cited sources only. Check them before acting on this answer.
        </p>
      )}
    </article>
  );
}

/**
 * "Ask a question" — evidence-grounded question answering over this
 * organization's knowledge (`POST /knowledge/rag/query`, Roadmap
 * Phase 2, item 4). Every outcome the backend can return has its own
 * explicit state: an answer is only ever shown for `ANSWERED`, a source
 * conflict is shown as a conflict, and every abstention says why.
 */
export function KnowledgeQuestionPanel({ organizationId }: { organizationId: string }) {
  const [question, setQuestion] = useState('');
  const [state, setState] = useState<PanelState>({ status: 'idle' });
  const controllerRef = useRef<AbortController | null>(null);

  // A different organization, or leaving the page, cancels any request
  // in flight and clears the previous organization's answer.
  useEffect(() => {
    setState({ status: 'idle' });
    return () => controllerRef.current?.abort();
  }, [organizationId]);

  async function ask(text: string) {
    const trimmed = text.trim();
    if (!trimmed) return;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setState({ status: 'loading' });
    try {
      const result = await askKnowledgeQuestion(organizationId, trimmed, controller.signal);
      if (controller.signal.aborted) return;
      setState({ status: 'answered', result });
    } catch (error) {
      if (controller.signal.aborted) return;
      setState({ status: 'failed', kind: classifyRagFailure(error) });
    }
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    void ask(question);
  }

  const loading = state.status === 'loading';

  return (
    <Section
      title="Ask a question"
      description="SIE answers from your organization's knowledge and cites its sources. When the evidence is missing or the sources disagree, it says so instead of guessing."
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-3" aria-busy={loading}>
        <Textarea
          label="Your question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="For example: what PPE is required for confined-space entry?"
          maxLength={MAX_QUESTION_LENGTH}
          rows={3}
        />
        <div className="flex justify-end">
          <Button type="submit" disabled={loading || !question.trim()}>
            <MessageSquareText className="h-4 w-4" aria-hidden="true" />
            {loading ? 'Asking…' : 'Ask'}
          </Button>
        </div>
      </form>

      <div aria-live="polite">
        {loading && <LoadingState label="Finding evidence and preparing an answer…" />}
        {state.status === 'answered' && <RagResult result={state.result} onRetry={() => void ask(state.result.query)} />}
        {state.status === 'failed' &&
          (FAILURE_PRESENTATION[state.kind].calm ? (
            <EmptyState title={FAILURE_PRESENTATION[state.kind].title} description={FAILURE_PRESENTATION[state.kind].description} />
          ) : (
            <ErrorState
              title={FAILURE_PRESENTATION[state.kind].title}
              description={FAILURE_PRESENTATION[state.kind].description}
              onRetry={FAILURE_PRESENTATION[state.kind].retry ? () => void ask(question) : undefined}
            />
          ))}
      </div>
    </Section>
  );
}
