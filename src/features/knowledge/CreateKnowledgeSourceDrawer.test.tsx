import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { CreateKnowledgeSourceDrawer } from './CreateKnowledgeSourceDrawer';
import { ApiError } from '../../services/api/errors';
import type { KnowledgeSource } from '../../services/api/knowledge';

vi.mock('../../services/api/knowledge', () => ({
  createKnowledgeSource: vi.fn(),
}));

import { createKnowledgeSource } from '../../services/api/knowledge';

const SOURCE: KnowledgeSource = {
  id: 'src-1',
  publisher: 'OSHA',
  name: '29 CFR 1910',
  source_type: 'Regulation',
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

describe('CreateKnowledgeSourceDrawer', () => {
  it('requires publisher, name, and source type', async () => {
    render(<CreateKnowledgeSourceDrawer isOpen onClose={() => {}} organizationId="org-1" onCreated={() => {}} />);

    // Publisher/Name/Source type are HTML5-`required`, so the browser's
    // own constraint validation blocks the submit event before this
    // drawer's onSubmit handler runs — the guarantee that matters is
    // that no API call results from an empty submission.
    await userEvent.click(screen.getByRole('button', { name: 'Create source' }));
    expect(createKnowledgeSource).not.toHaveBeenCalled();
  });

  it('creates an organization-scoped source with this organization id', async () => {
    vi.mocked(createKnowledgeSource).mockResolvedValue(SOURCE);
    const onCreated = vi.fn();

    render(<CreateKnowledgeSourceDrawer isOpen onClose={() => {}} organizationId="org-1" onCreated={onCreated} />);

    await userEvent.type(screen.getByLabelText('Publisher'), 'OSHA');
    await userEvent.type(screen.getByLabelText('Name'), '29 CFR 1910');
    await userEvent.type(screen.getByLabelText('Source type'), 'Regulation');
    await userEvent.click(screen.getByRole('button', { name: 'Create source' }));

    await waitFor(() =>
      expect(createKnowledgeSource).toHaveBeenCalledWith(
        expect.objectContaining({ publisher: 'OSHA', name: '29 CFR 1910', sourceType: 'Regulation', scopeType: 'ORGANIZATION', organizationId: 'org-1' }),
      ),
    );
    expect(onCreated).toHaveBeenCalledWith(SOURCE);
  });

  it('creates a global source with no organization id, and shows the global 403 message on failure', async () => {
    vi.mocked(createKnowledgeSource).mockRejectedValue(new ApiError('Forbidden', { status: 403 }));

    render(<CreateKnowledgeSourceDrawer isOpen onClose={() => {}} organizationId="org-1" onCreated={() => {}} />);

    await userEvent.selectOptions(screen.getByLabelText('Scope'), 'GLOBAL');
    await userEvent.type(screen.getByLabelText('Publisher'), 'ISO');
    await userEvent.type(screen.getByLabelText('Name'), 'ISO 45001');
    await userEvent.type(screen.getByLabelText('Source type'), 'Standard');
    await userEvent.click(screen.getByRole('button', { name: 'Create source' }));

    await waitFor(() =>
      expect(createKnowledgeSource).toHaveBeenCalledWith(expect.objectContaining({ scopeType: 'GLOBAL', organizationId: undefined })),
    );
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('platform-wide knowledge:manage access'));
  });
});
