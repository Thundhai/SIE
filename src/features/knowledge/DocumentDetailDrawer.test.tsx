import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { DocumentDetailDrawer } from './DocumentDetailDrawer';
import type { KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentVersion } from '../../services/api/knowledge';

vi.mock('../../services/api/knowledge', () => ({
  getKnowledgeDocument: vi.fn(),
  listKnowledgeDocumentVersions: vi.fn(),
  listKnowledgeChunks: vi.fn(),
}));

import { getKnowledgeDocument, listKnowledgeChunks, listKnowledgeDocumentVersions } from '../../services/api/knowledge';

const DOCUMENT: KnowledgeDocument = {
  id: 'doc-1',
  source_id: 'src-1',
  organization_id: 'org-1',
  title: 'Confined space entry procedure',
  document_type: 'Internal procedure',
  description: 'Site-specific entry procedure.',
  language: 'en',
  external_document_id: null,
  current_version_id: 'ver-1',
  status: 'active',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const VERSION: KnowledgeDocumentVersion = {
  id: 'ver-1',
  document_id: 'doc-1',
  version_label: 'v1',
  content_hash: 'abc',
  storage_reference: 'ref',
  extracted_text: null,
  publication_date: '2026-01-01',
  effective_date: null,
  superseded_at: null,
  ingestion_status: 'PROCESSED',
  created_at: '2026-01-01T00:00:00Z',
};

const CHUNK: KnowledgeChunk = {
  id: 'chunk-1',
  document_version_id: 'ver-1',
  document_id: 'doc-1',
  source_id: 'src-1',
  organization_id: 'org-1',
  chunk_index: 0,
  content: 'Verify atmosphere before entry.',
  character_count: 32,
  content_type: 'text',
  page_number: 1,
  sheet_name: null,
  row_number: null,
  slide_number: null,
  section_title: 'Entry checklist',
  section_path: null,
  source_reference: null,
  extraction_method: 'TEXT_EXTRACTION',
  quality_status: 'HIGH',
  chunk_metadata: null,
  created_at: '2026-01-01T00:00:00Z',
};

describe('DocumentDetailDrawer', () => {
  it('loads document detail and its versions, marking the current version', async () => {
    vi.mocked(getKnowledgeDocument).mockResolvedValue(DOCUMENT);
    vi.mocked(listKnowledgeDocumentVersions).mockResolvedValue([VERSION]);

    render(<DocumentDetailDrawer isOpen onClose={() => {}} documentId="doc-1" organizationId="org-1" />);

    await waitFor(() => expect(screen.getByText('Confined space entry procedure')).toBeInTheDocument());
    expect(getKnowledgeDocument).toHaveBeenCalledWith('doc-1', 'org-1', expect.anything());
    expect(screen.getByText('v1')).toBeInTheDocument();
    expect(screen.getByText('Current')).toBeInTheDocument();
  });

  it('loads a version’s chunks on demand, not eagerly', async () => {
    vi.mocked(getKnowledgeDocument).mockResolvedValue(DOCUMENT);
    vi.mocked(listKnowledgeDocumentVersions).mockResolvedValue([VERSION]);
    vi.mocked(listKnowledgeChunks).mockResolvedValue([CHUNK]);

    render(<DocumentDetailDrawer isOpen onClose={() => {}} documentId="doc-1" organizationId="org-1" />);

    await waitFor(() => expect(screen.getByText('v1')).toBeInTheDocument());
    expect(listKnowledgeChunks).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole('button', { name: 'View chunks' }));

    await waitFor(() => expect(listKnowledgeChunks).toHaveBeenCalledWith('doc-1', 'ver-1', 'org-1', expect.anything(), expect.anything()));
    await waitFor(() => expect(screen.getByText('Verify atmosphere before entry.')).toBeInTheDocument());
  });
});
