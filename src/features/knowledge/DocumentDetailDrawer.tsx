import { useEffect, useState } from 'react';
import { Drawer } from '../../components/ui/Drawer';
import { Button } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { LoadingState } from '../../components/ui/LoadingState';
import { StatusBadge } from '../../components/ui/StatusBadge';
import {
  getKnowledgeDocument,
  listKnowledgeChunks,
  listKnowledgeDocumentVersions,
  type KnowledgeChunk,
  type KnowledgeDocument,
  type KnowledgeDocumentVersion,
} from '../../services/api/knowledge';
import type { AsyncState } from '../../types/common';
import { ingestionStatusLabel, ingestionStatusTone } from './knowledgeLabels';

export interface DocumentDetailDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  documentId: string | null;
  /** The document's own scope — null for GLOBAL, a real id for
   * ORGANIZATION — taken from the search result or source that led here,
   * never assumed to be the viewer's current organization. */
  organizationId: string | null;
}

/**
 * Read-only drill-down: Document -> Versions -> Chunks, the remaining
 * two links in the "Knowledge Sources -> Documents -> Versions -> Chunks"
 * chain that a search result doesn't already show inline. Reached only
 * from a document id already in hand (a search result, or a just-created
 * upload) — there is no `GET` list-by-source endpoint to browse from
 * (see `services/api/knowledge.ts`'s own note on this backend gap).
 */
export function DocumentDetailDrawer({ isOpen, onClose, documentId, organizationId }: DocumentDetailDrawerProps) {
  const [documentState, setDocumentState] = useState<AsyncState<KnowledgeDocument>>({ status: 'loading' });
  const [versionsState, setVersionsState] = useState<AsyncState<KnowledgeDocumentVersion[]>>({ status: 'loading' });
  const [expandedVersionId, setExpandedVersionId] = useState<string | null>(null);
  const [chunksState, setChunksState] = useState<AsyncState<KnowledgeChunk[]>>({ status: 'loading' });

  useEffect(() => {
    if (!isOpen || !documentId) return;
    const controller = new AbortController();
    setDocumentState({ status: 'loading' });
    getKnowledgeDocument(documentId, organizationId, controller.signal)
      .then((document) => setDocumentState({ status: 'success', data: document }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setDocumentState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load this document.' });
      });
    return () => controller.abort();
  }, [isOpen, documentId, organizationId]);

  useEffect(() => {
    if (!isOpen || !documentId) return;
    const controller = new AbortController();
    setVersionsState({ status: 'loading' });
    setExpandedVersionId(null);
    listKnowledgeDocumentVersions(documentId, organizationId, {}, controller.signal)
      .then((versions) => setVersionsState({ status: 'success', data: versions }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setVersionsState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load this document’s versions.' });
      });
    return () => controller.abort();
  }, [isOpen, documentId, organizationId]);

  useEffect(() => {
    if (!expandedVersionId || !documentId) return;
    const controller = new AbortController();
    setChunksState({ status: 'loading' });
    listKnowledgeChunks(documentId, expandedVersionId, organizationId, { limit: 50 }, controller.signal)
      .then((chunks) => setChunksState({ status: 'success', data: chunks }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setChunksState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load chunks for this version.' });
      });
    return () => controller.abort();
  }, [expandedVersionId, documentId, organizationId]);

  return (
    <Drawer isOpen={isOpen} onClose={onClose} title="Document detail">
      <div className="flex flex-col gap-4">
        {documentState.status === 'loading' && <LoadingState label="Loading document…" />}
        {documentState.status === 'error' && <ErrorState description={documentState.message} />}
        {documentState.status === 'success' && (
          <div className="rounded-lg border border-border bg-surface p-4">
            <p className="text-sm font-semibold text-text-primary">{documentState.data.title}</p>
            <p className="mt-1 text-xs text-text-secondary">
              {documentState.data.document_type}
              {documentState.data.language ? ` · ${documentState.data.language}` : ''} · {documentState.data.status}
            </p>
            {documentState.data.description && <p className="mt-2 text-sm text-text-secondary">{documentState.data.description}</p>}
            <p className="mt-2 text-xs text-text-muted">
              {organizationId ? 'Organization-scoped' : 'Global'} · Source id: <span className="font-mono">{documentState.data.source_id}</span>
            </p>
          </div>
        )}

        <div>
          <h3 className="text-sm font-semibold text-text-primary">Versions</h3>
          {versionsState.status === 'loading' && <LoadingState label="Loading versions…" />}
          {versionsState.status === 'error' && <ErrorState description={versionsState.message} />}
          {versionsState.status === 'success' && versionsState.data.length === 0 && (
            <EmptyState title="No versions" description="This document has no recorded versions." />
          )}
          {versionsState.status === 'success' && versionsState.data.length > 0 && (
            <ul className="mt-2 flex flex-col gap-2">
              {versionsState.data.map((version) => {
                const isCurrent = documentState.status === 'success' && documentState.data.current_version_id === version.id;
                const isExpanded = expandedVersionId === version.id;
                return (
                  <li key={version.id} className="rounded-lg border border-border bg-surface p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium text-text-primary">{version.version_label}</p>
                        {isCurrent && <StatusBadge tone="success" label="Current" />}
                        <StatusBadge tone={ingestionStatusTone(version.ingestion_status)} label={ingestionStatusLabel(version.ingestion_status)} />
                      </div>
                      <Button size="sm" variant="ghost" onClick={() => setExpandedVersionId(isExpanded ? null : version.id)}>
                        {isExpanded ? 'Hide chunks' : 'View chunks'}
                      </Button>
                    </div>
                    <p className="mt-1 text-xs text-text-muted">
                      {version.publication_date ? `Published ${version.publication_date}` : 'No publication date'}
                      {version.effective_date ? ` · Effective ${version.effective_date}` : ''}
                      {version.superseded_at ? ` · Superseded ${new Date(version.superseded_at).toLocaleDateString()}` : ''}
                    </p>

                    {isExpanded && (
                      <div className="mt-3 border-t border-border pt-3">
                        {chunksState.status === 'loading' && <LoadingState label="Loading chunks…" />}
                        {chunksState.status === 'error' && <ErrorState description={chunksState.message} />}
                        {chunksState.status === 'success' && chunksState.data.length === 0 && (
                          <EmptyState title="No chunks" description="This version has no extracted chunks." />
                        )}
                        {chunksState.status === 'success' && chunksState.data.length > 0 && (
                          <ul className="flex flex-col gap-2">
                            {chunksState.data.map((chunk) => (
                              <li key={chunk.id} className="rounded-md bg-surface-muted p-2">
                                <p className="text-xs text-text-muted">
                                  Chunk {chunk.chunk_index} · {chunk.quality_status}
                                  {chunk.page_number != null ? ` · Page ${chunk.page_number}` : ''}
                                  {chunk.section_title ? ` · ${chunk.section_title}` : ''}
                                </p>
                                <p className="mt-1 text-sm text-text-secondary line-clamp-3">{chunk.content || '(no extracted content)'}</p>
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </Drawer>
  );
}
