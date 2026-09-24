import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { CreateSiteDrawer } from './CreateSiteDrawer';
import { ApiError } from '../../services/api/errors';
import type { Site } from '../../services/api/sites';

vi.mock('../../services/api/sites', () => ({
  createSite: vi.fn(),
}));

import { createSite } from '../../services/api/sites';

/**
 * Sites has create-only backend support (`POST /organizations/{id}/sites`)
 * — no edit/delete route exists, so this drawer is the only mutation
 * surface for sites anywhere in the app.
 */
describe('CreateSiteDrawer', () => {
  it('requires a non-blank site name', async () => {
    render(<CreateSiteDrawer isOpen onClose={() => {}} organizationId="org-1" onCreated={() => {}} />);

    // The name field is HTML5-`required`, so the browser's own constraint
    // validation blocks the submit event before this drawer's onSubmit
    // handler ever runs — the important guarantee is that no API call
    // results from an empty submission.
    await userEvent.click(screen.getByRole('button', { name: 'Create site' }));
    expect(createSite).not.toHaveBeenCalled();
  });

  it('creates a site and refreshes with the authoritative result', async () => {
    const created = { id: 'site-1', organization_id: 'org-1', name: 'Riverside Yard', location: null, country: null, status: 'active', created_at: '', updated_at: '' } satisfies Site;
    vi.mocked(createSite).mockResolvedValue(created);
    const onCreated = vi.fn();
    const onClose = vi.fn();

    render(<CreateSiteDrawer isOpen onClose={onClose} organizationId="org-1" onCreated={onCreated} />);

    await userEvent.type(screen.getByLabelText('Site name'), 'Riverside Yard');
    await userEvent.click(screen.getByRole('button', { name: 'Create site' }));

    await waitFor(() => expect(createSite).toHaveBeenCalledWith('org-1', { name: 'Riverside Yard', location: undefined, country: undefined }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(created));
    expect(onClose).toHaveBeenCalled();
  });

  it('on a 403, shows a permission message and never fabricates success', async () => {
    vi.mocked(createSite).mockRejectedValue(new ApiError('Forbidden', { status: 403 }));
    const onCreated = vi.fn();

    render(<CreateSiteDrawer isOpen onClose={() => {}} organizationId="org-1" onCreated={onCreated} />);

    await userEvent.type(screen.getByLabelText('Site name'), 'Riverside Yard');
    await userEvent.click(screen.getByRole('button', { name: 'Create site' }));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent("You don't have permission to create sites in this organization."));
    expect(onCreated).not.toHaveBeenCalled();
  });
});
