import { Search } from 'lucide-react';
import { type FormEvent, useEffect, useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { PageContainer } from '../../components/layout/PageContainer';
import { Section } from '../../components/layout/Section';
import { Button } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { Input } from '../../components/ui/Input';
import { LoadingState } from '../../components/ui/LoadingState';
import { Select } from '../../components/ui/Select';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { ApiError } from '../../services/api/errors';
import {
  listKnowledgeSources,
  searchKnowledge,
  type KnowledgeRetrievalResult,
  type KnowledgeSource,
  type VerificationStatus,
} from '../../services/api/knowledge';
import type { AsyncState } from '../../types/common';
import { CreateKnowledgeSourceDrawer } from './CreateKnowledgeSourceDrawer';
import { DocumentDetailDrawer } from './DocumentDetailDrawer';
import { IngestDocumentDrawer } from './IngestDocumentDrawer';
import { relevanceLabel, relevanceTone, scopeLabel, scopeTone, verificationStatusLabel, verificationStatusTone } from './knowledgeLabels';

/**
 * Knowledge — search (evidence retrieval), source catalogue, and document
 * upload, all against the real `backend/app/api/v1/{knowledge,retrieval,
 * ingestion}.py` routes. Deliberately stops at "Retrieval -> Evidence":
 * the backend also has an evidence-grounded RAG answer endpoint
 * (`/knowledge/rag/query`), not wired in here, because this page's job is
 * showing evidence, not synthesizing an answer from it — see this file's
 * own search-results section for the "not a confidence score" framing
 * the backend's own schema documents.
 */
export function KnowledgePage() {
  const auth = useAuth();
  const organizationId = auth.organization?.id ?? null;

  const [orgSourcesState, setOrgSourcesState] = useState<AsyncState<KnowledgeSource[]>>({ status: 'loading' });
  const [globalSourcesState, setGlobalSourcesState] = useState<AsyncState<KnowledgeSource[]>>({ status: 'loading' });
  const [sourcesRefreshToken, setSourcesRefreshToken] = useState(0);
  const [createSourceOpen, setCreateSourceOpen] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);

  const [query, setQuery] = useState('');
  const [verificationStatus, setVerificationStatus] = useState<VerificationStatus | 'ALL'>('ALL');
  const [results, setResults] = useState<KnowledgeRetrievalResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  const [viewingDocument, setViewingDocument] = useState<{ documentId: string; organizationId: string | null } | null>(null);

  useEffect(() => {
    if (!organizationId) return;
    const controller = new AbortController();
    setOrgSourcesState({ status: 'loading' });
    listKnowledgeSources({ organizationId }, controller.signal)
      .then((sources) => setOrgSourcesState({ status: 'success', data: sources }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.status === 403) {
          setOrgSourcesState({ status: 'error', message: "You don't have permission to view this organization's knowledge sources." });
        } else {
          setOrgSourcesState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load knowledge sources.' });
        }
      });
    return () => controller.abort();
  }, [organizationId, sourcesRefreshToken]);

  useEffect(() => {
    const controller = new AbortController();
    setGlobalSourcesState({ status: 'loading' });
    listKnowledgeSources({}, controller.signal)
      .then((sources) => setGlobalSourcesState({ status: 'success', data: sources }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setGlobalSourcesState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load global knowledge sources.' });
      });
    return () => controller.abort();
  }, [sourcesRefreshToken]);

  async function handleSearch(event: FormEvent) {
    event.preventDefault();
    if (!organizationId || !query.trim()) return;
    setSearching(true);
    setSearchError(null);
    setHasSearched(true);
    try {
      const response = await searchKnowledge(organizationId, query.trim(), {
        verificationStatus: verificationStatus === 'ALL' ? undefined : verificationStatus,
      });
      setResults(response.results);
      if (response.outcome === 'NO_RELEVANT_EVIDENCE') {
        setSearchError('No relevant evidence was returned for this query.');
      }
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        setSearchError("You don't have permission to search knowledge in this organization.");
      } else {
        setSearchError(error instanceof Error ? error.message : 'Knowledge search failed.');
      }
      setResults([]);
    } finally {
      setSearching(false);
    }
  }

  if (!organizationId) {
    return (
      <PageContainer>
        <h1 className="text-xl font-semibold text-navy-900">Knowledge</h1>
        <EmptyState title="No organization context available" description="A development identity is not configured, or it could not be resolved against the backend." />
      </PageContainer>
    );
  }

  const combinedSources = [
    ...(orgSourcesState.status === 'success' ? orgSourcesState.data : []),
    ...(globalSourcesState.status === 'success' ? globalSourcesState.data : []),
  ];

  return (
    <PageContainer>
      <div>
        <h1 className="text-xl font-semibold text-navy-900">Knowledge</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Search and review safety knowledge available to your organization. Retrieval returns evidence with its source and
          verification context — similarity is a measure of relevance, never a confidence or truth score.
        </p>
      </div>

      <Section
        title="Knowledge search"
        description="Searches this organization's knowledge plus all global knowledge in one call. Each result is a citable piece of evidence, not a generated answer."
      >
        <form onSubmit={handleSearch} className="grid gap-3 sm:grid-cols-[1fr_220px_auto]">
          <Input
            label="Search knowledge"
            hideLabel
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search standards, procedures, lessons, or safety topics…"
            maxLength={2000}
          />
          <Select
            label="Verification status"
            hideLabel
            value={verificationStatus}
            onChange={(event) => setVerificationStatus(event.target.value as VerificationStatus | 'ALL')}
            options={[
              { value: 'ALL', label: 'All verification statuses' },
              { value: 'VERIFIED', label: 'Verified' },
              { value: 'UNDER_REVIEW', label: 'Under review' },
              { value: 'PENDING', label: 'Pending' },
              { value: 'REJECTED', label: 'Rejected' },
              { value: 'EXPIRED', label: 'Expired' },
              { value: 'SUPERSEDED', label: 'Superseded' },
            ]}
          />
          <Button type="submit" disabled={searching || !query.trim()}>
            <Search className="h-4 w-4" aria-hidden="true" />
            {searching ? 'Searching…' : 'Search'}
          </Button>
        </form>

        {searching && <LoadingState label="Searching knowledge…" />}

        {!searching && searchError && <p className="mt-3 text-sm text-text-secondary">{searchError}</p>}

        {!searching && hasSearched && !searchError && results.length === 0 && (
          <EmptyState title="No results" description="No evidence matched this query." />
        )}

        {!searching && results.length > 0 && (
          <ul className="mt-4 flex flex-col gap-2">
            {results.map((result) => (
              <li key={result.chunk_id} className="rounded-lg border border-border bg-surface p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold text-text-primary">{result.document}</p>
                    <p className="mt-0.5 text-xs text-text-muted">
                      {result.source} · {result.version}
                      {result.location ? ' · ' + result.location : ''}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <StatusBadge tone={scopeTone(result.scope)} label={scopeLabel(result.scope)} />
                    <StatusBadge tone={verificationStatusTone(result.verification_status)} label={verificationStatusLabel(result.verification_status)} />
                  </div>
                </div>

                <p className="mt-3 text-sm leading-relaxed text-text-primary">{result.content}</p>

                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <StatusBadge tone={relevanceTone(result.relevance)} label={`${relevanceLabel(result.relevance)} relevance`} />
                  <span className="text-xs text-text-muted">similarity {result.similarity.toFixed(3)} (evidence match, not confidence)</span>
                </div>

                <p className="mt-2 text-xs text-text-muted">
                  {result.extraction_quality} extraction
                  {result.extraction_method ? ` · ${result.extraction_method}` : ''}
                  {result.source_authority_level ? ` · ${result.source_authority_level}` : ''}
                  {result.jurisdiction ? ` · ${result.jurisdiction}` : ''}
                  {result.industry_sector ? ` · ${result.industry_sector}` : ''}
                </p>
                {(result.publication_date || result.effective_date) && (
                  <p className="mt-1 text-xs text-text-muted">
                    {result.publication_date ? `Published ${result.publication_date}` : ''}
                    {result.publication_date && result.effective_date ? ' · ' : ''}
                    {result.effective_date ? `Effective ${result.effective_date}` : ''}
                  </p>
                )}

                <div className="mt-3">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setViewingDocument({ documentId: result.document_id, organizationId: result.organization_id })}
                  >
                    View document
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section
        title="Knowledge sources"
        description="The catalogue this organization can search against: its own sources plus global sources visible to every organization."
        action={
          <div className="flex gap-2">
            <Button size="sm" variant="secondary" onClick={() => setUploadOpen(true)}>
              Upload document
            </Button>
            <Button size="sm" onClick={() => setCreateSourceOpen(true)}>
              Create source
            </Button>
          </div>
        }
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <h3 className="text-sm font-semibold text-text-primary">Organization sources</h3>
            {orgSourcesState.status === 'loading' && <LoadingState label="Loading organization sources…" />}
            {orgSourcesState.status === 'error' && <ErrorState description={orgSourcesState.message} />}
            {orgSourcesState.status === 'success' && orgSourcesState.data.length === 0 && (
              <EmptyState title="No organization knowledge sources" description="No organization-scoped knowledge sources are currently available." />
            )}
            {orgSourcesState.status === 'success' && orgSourcesState.data.length > 0 && (
              <ul className="mt-2 flex flex-col gap-2">
                {orgSourcesState.data.map((source) => (
                  <SourceCard key={source.id} source={source} />
                ))}
              </ul>
            )}
          </div>

          <div>
            <h3 className="text-sm font-semibold text-text-primary">Global sources</h3>
            {globalSourcesState.status === 'loading' && <LoadingState label="Loading global sources…" />}
            {globalSourcesState.status === 'error' && <ErrorState description={globalSourcesState.message} />}
            {globalSourcesState.status === 'success' && globalSourcesState.data.length === 0 && (
              <EmptyState title="No global knowledge sources" description="No global knowledge sources are currently available." />
            )}
            {globalSourcesState.status === 'success' && globalSourcesState.data.length > 0 && (
              <ul className="mt-2 flex flex-col gap-2">
                {globalSourcesState.data.map((source) => (
                  <SourceCard key={source.id} source={source} />
                ))}
              </ul>
            )}
          </div>
        </div>
      </Section>

      <CreateKnowledgeSourceDrawer
        isOpen={createSourceOpen}
        onClose={() => setCreateSourceOpen(false)}
        organizationId={organizationId}
        onCreated={() => setSourcesRefreshToken((token) => token + 1)}
      />
      <IngestDocumentDrawer
        isOpen={uploadOpen}
        onClose={() => setUploadOpen(false)}
        organizationId={organizationId}
        sources={combinedSources}
        onIngested={() => setSourcesRefreshToken((token) => token + 1)}
      />
      <DocumentDetailDrawer
        isOpen={viewingDocument !== null}
        onClose={() => setViewingDocument(null)}
        documentId={viewingDocument?.documentId ?? null}
        organizationId={viewingDocument?.organizationId ?? null}
      />
    </PageContainer>
  );
}

function SourceCard({ source }: { source: KnowledgeSource }) {
  return (
    <li className="rounded-lg border border-border bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-text-primary">{source.name}</p>
          <p className="mt-1 text-xs text-text-secondary">
            {source.publisher} · {source.source_type}
          </p>
        </div>
        <StatusBadge tone={verificationStatusTone(source.verification_status)} label={verificationStatusLabel(source.verification_status)} />
      </div>
      <p className="mt-2 text-xs text-text-muted">
        {source.jurisdiction ?? 'Jurisdiction not specified'}
        {source.industry_sector ? ' · ' + source.industry_sector : ''}
      </p>
    </li>
  );
}
