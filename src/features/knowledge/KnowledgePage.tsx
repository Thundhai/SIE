import { Search } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { PageContainer } from '../../components/layout/PageContainer';
import { Section } from '../../components/layout/Section';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { LoadingState } from '../../components/ui/LoadingState';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import {
  listKnowledgeSources,
  searchKnowledge,
  type KnowledgeRetrievalResult,
  type KnowledgeSource,
  type VerificationStatus,
} from '../../services/api/knowledge';

export function KnowledgePage() {
  const auth = useAuth();
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [results, setResults] = useState<KnowledgeRetrievalResult[]>([]);
  const [query, setQuery] = useState('');
  const [verificationStatus, setVerificationStatus] = useState<VerificationStatus | 'ALL'>('ALL');
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);

  useEffect(() => {
    if (!auth.organization) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    listKnowledgeSources({ organizationId: auth.organization.id }, controller.signal)
      .then(setSources)
      .catch((requestError: unknown) => {
        if (controller.signal.aborted) return;
        setError(requestError instanceof Error ? requestError.message : 'Could not load knowledge sources.');
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [auth.organization]);

  async function handleSearch(event: React.FormEvent) {
    event.preventDefault();
    if (!auth.organization || !query.trim()) return;
    setSearching(true);
    setSearchError(null);
    try {
      const response = await searchKnowledge(
        auth.organization.id,
        query.trim(),
        verificationStatus === 'ALL' ? undefined : { verificationStatus },
      );
      setResults(response.results);
      if (response.outcome === 'NO_RELEVANT_EVIDENCE') {
        setSearchError('No relevant evidence was returned for this query.');
      }
    } catch (requestError) {
      setSearchError(requestError instanceof Error ? requestError.message : 'Knowledge search failed.');
      setResults([]);
    } finally {
      setSearching(false);
    }
  }

  if (!auth.organization) {
    return (
      <PageContainer>
        <h1 className="text-xl font-semibold text-navy-900">Knowledge</h1>
        <EmptyState title="No organization context available" description="A development identity is not configured, or it could not be resolved against the backend." />
      </PageContainer>
    );
  }

  const permissionDenied = error?.toLowerCase().includes('permission') || searchError?.toLowerCase().includes('permission');

  return (
    <PageContainer>
      <div>
        <h1 className="text-xl font-semibold text-navy-900">Knowledge</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Search and review safety knowledge available to your organization. Retrieval returns evidence with its source and verification context.
        </p>
      </div>

      {permissionDenied && (
        <EmptyState
          title="You don't have permission to view knowledge"
          description="Ask an administrator for knowledge:read access in this organization."
        />
      )}

      {!permissionDenied && loading && <LoadingState label="Loading knowledge sources…" />}

      {!permissionDenied && error && !loading && (
        <ErrorState title="Could not load knowledge" description={error} onRetry={() => window.location.reload()} />
      )}

      {!permissionDenied && !loading && !error && (
        <>
          <Section title="Knowledge search" description="Search the organization and global knowledge corpus through the backend retrieval service. Similarity is evidence retrieval, not a confidence or truth score.">
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
                  { value: 'PENDING', label: 'Pending' },
                  { value: 'REJECTED', label: 'Rejected' },
                ]}
              />
              <Button type="submit" disabled={searching || !query.trim()}>
                <Search className="h-4 w-4" aria-hidden="true" />
                {searching ? 'Searching…' : 'Search'}
              </Button>
            </form>

            {searchError && <p className="mt-3 text-sm text-text-secondary">{searchError}</p>}

            {results.length > 0 && (
              <ul className="mt-4 flex flex-col gap-2">
                {results.map((result) => (
                  <li key={result.chunk_id} className="rounded-lg border border-border bg-surface p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <p className="text-sm font-semibold text-text-primary">{result.document}</p>
                        <p className="mt-0.5 text-xs text-text-muted">
                          {result.source} · {result.version}{result.location ? ' · ' + result.location : ''}
                        </p>
                      </div>
                      <StatusBadge
                        tone={result.verification_status === 'VERIFIED' ? 'success' : result.verification_status === 'REJECTED' ? 'critical' : 'neutral'}
                        label={result.verification_status.replaceAll('_', ' ')}
                      />
                    </div>
                    <p className="mt-3 text-sm leading-relaxed text-text-primary">{result.content}</p>
                    <p className="mt-2 text-xs text-text-muted">
                      {result.relevance} relevance · similarity {result.similarity.toFixed(3)}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title="Organization knowledge sources" description="Sources are organization-scoped and returned directly from the SIE knowledge API.">
            {sources.length === 0 ? (
              <EmptyState
                title="No organization knowledge sources"
                description="No organization-scoped knowledge sources are currently available. Global knowledge may still be searchable."
              />
            ) : (
              <ul className="grid gap-2 sm:grid-cols-2">
                {sources.map((source) => (
                  <li key={source.id} className="rounded-lg border border-border bg-surface p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-text-primary">{source.name}</p>
                        <p className="mt-1 text-xs text-text-secondary">{source.publisher} · {source.source_type}</p>
                      </div>
                      <StatusBadge
                        tone={source.verification_status === 'VERIFIED' ? 'success' : source.verification_status === 'REJECTED' ? 'critical' : 'neutral'}
                        label={source.verification_status}
                      />
                    </div>
                    <p className="mt-2 text-xs text-text-muted">
                      {source.jurisdiction ?? 'Jurisdiction not specified'}
                      {source.industry_sector ? ' · ' + source.industry_sector : ''}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </>
      )}
    </PageContainer>
  );
}
