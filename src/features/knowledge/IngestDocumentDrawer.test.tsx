import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { IngestDocumentDrawer } from './IngestDocumentDrawer';
import { ApiError } from '../../services/api/errors';
import type { IngestionResult, KnowledgeSource } from '../../services/api/knowledge';

vi.mock('../../services/api/knowledge', () => ({
  ingestDocument: vi.fn(),
}));

import { ingestDocument } from '../../services/api/knowledge';

const ORG_SOURCE: KnowledgeSource = {
  id: 'src-org',
  publisher: 'Acme',
  name: 'Site procedures',
  source_type: 'Internal procedure',
  jurisdiction: null,
  industry_sector: null,
  authority_level: null,
  external_reference: null,
  publication_date: null,
  review_date: null,
  scope_type: 'ORGANIZATION',
  organization_id: 'org-1',
  verification_status: 'PENDING',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const RESULT: IngestionResult = {
  ingestion_job_id: 'job-1',
  file_id: 'file-1',
  detected_media_type: 'application/pdf',
  file_size: 2048,
  content_hash: 'abc123',
  ingestion_status: 'COMPLETED',
  extraction_status: 'SUCCEEDED',
  extraction_method: 'TEXT_EXTRACTION',
  document_id: 'doc-1',
  version_id: 'ver-1',
  chunk_count: 4,
  warnings: [],
};

function makeFile(name = 'procedure.pdf') {
  return new File(['%PDF-1.4 test content'], name, { type: 'application/pdf' });
}

describe('IngestDocumentDrawer', () => {
  it('requires a source, a file, and a title (for a new document)', async () => {
    render(<IngestDocumentDrawer isOpen onClose={() => {}} organizationId="org-1" sources={[ORG_SOURCE]} onIngested={() => {}} />);

    await userEvent.click(screen.getByRole('button', { name: 'Upload' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Choose a knowledge source.');
    expect(ingestDocument).not.toHaveBeenCalled();
  });

  it('uploads a new document and shows the extraction outcome', async () => {
    vi.mocked(ingestDocument).mockResolvedValue(RESULT);
    const onIngested = vi.fn();

    render(<IngestDocumentDrawer isOpen onClose={() => {}} organizationId="org-1" sources={[ORG_SOURCE]} onIngested={onIngested} />);

    await userEvent.selectOptions(screen.getByLabelText('Knowledge source'), 'src-org');
    await userEvent.upload(screen.getByLabelText('File'), makeFile());
    await userEvent.type(screen.getByLabelText('Title'), 'Confined space entry procedure');
    await userEvent.click(screen.getByRole('button', { name: 'Upload' }));

    await waitFor(() =>
      expect(ingestDocument).toHaveBeenCalledWith(
        expect.objectContaining({ sourceId: 'src-org', organizationId: 'org-1', title: 'Confined space entry procedure' }),
      ),
    );
    await waitFor(() => expect(onIngested).toHaveBeenCalledWith(RESULT));
    expect(screen.getByText(/4 chunks produced/)).toBeInTheDocument();
  });

  it('surfaces a permission error without fabricating success', async () => {
    vi.mocked(ingestDocument).mockRejectedValue(new ApiError('Forbidden', { status: 403 }));

    render(<IngestDocumentDrawer isOpen onClose={() => {}} organizationId="org-1" sources={[ORG_SOURCE]} onIngested={() => {}} />);

    await userEvent.selectOptions(screen.getByLabelText('Knowledge source'), 'src-org');
    await userEvent.upload(screen.getByLabelText('File'), makeFile());
    await userEvent.type(screen.getByLabelText('Title'), 'Confined space entry procedure');
    await userEvent.click(screen.getByRole('button', { name: 'Upload' }));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent("don't have permission to add knowledge"));
    expect(screen.queryByText(/chunks produced/)).not.toBeInTheDocument();
  });
});
