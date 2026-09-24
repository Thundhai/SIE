import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ApiClientsSection } from './ApiClientsSection';
import { ApiError } from '../../services/api/errors';
import type { ApiClient, ApiClientCreated } from '../../services/api/administration';

vi.mock('../../services/api/administration', () => ({
  listApiClients: vi.fn(),
  createApiClient: vi.fn(),
  rotateApiClientSecret: vi.fn(),
  revokeApiClient: vi.fn(),
}));

import { createApiClient, listApiClients, revokeApiClient, rotateApiClientSecret } from '../../services/api/administration';

const CLIENT: ApiClient = {
  id: 'client-1',
  organization_id: 'org-1',
  name: 'Safelytic integration',
  client_id: 'client_abc123',
  secret_prefix: 'sk_live_ab',
  scopes: ['intelligence:read'],
  status: 'ACTIVE',
  created_at: '2026-01-01T00:00:00Z',
  last_used_at: null,
  rotated_at: null,
  revoked_at: null,
  expires_at: null,
};

/**
 * The backend returns a raw secret only from create/rotate, never from
 * list — this section must never show a secret sourced from anywhere
 * else, and must never retain one past the reveal panel being dismissed.
 */
describe('ApiClientsSection', () => {
  it('shows an empty state when no clients exist', async () => {
    vi.mocked(listApiClients).mockResolvedValue([]);
    render(<ApiClientsSection organizationId="org-1" />);

    await waitFor(() => expect(screen.getByText('No API clients yet')).toBeInTheDocument());
  });

  it('lists clients without ever displaying a secret', async () => {
    vi.mocked(listApiClients).mockResolvedValue([CLIENT]);
    render(<ApiClientsSection organizationId="org-1" />);

    await waitFor(() => expect(screen.getByText('Safelytic integration')).toBeInTheDocument());
    expect(screen.getByText('sk_live_ab…')).toBeInTheDocument();
    expect(screen.queryByText(/secret_/)).not.toBeInTheDocument();
  });

  it('shows a permission message on a 403 when listing clients', async () => {
    vi.mocked(listApiClients).mockRejectedValue(new ApiError('Forbidden', { status: 403 }));
    render(<ApiClientsSection organizationId="org-1" />);

    await waitFor(() => expect(screen.getByText(/don't have permission to view API clients/)).toBeInTheDocument());
  });

  it('reveals a newly created client secret exactly once', async () => {
    vi.mocked(listApiClients).mockResolvedValue([]);
    const created: ApiClientCreated = { ...CLIENT, secret: 'sk_live_ab_the_full_secret_value' };
    vi.mocked(createApiClient).mockResolvedValue(created);

    render(<ApiClientsSection organizationId="org-1" />);
    await waitFor(() => expect(screen.getByText('No API clients yet')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('button', { name: 'Create API client' }));
    const dialog = within(screen.getByRole('dialog'));
    await userEvent.type(dialog.getByLabelText('Name'), 'Safelytic integration');
    await userEvent.click(dialog.getByLabelText('Intelligence — read'));
    await userEvent.click(dialog.getByRole('button', { name: 'Create API client' }));

    await waitFor(() => expect(screen.getByText('sk_live_ab_the_full_secret_value')).toBeInTheDocument());
    expect(screen.getByText(/shown once and cannot be retrieved again/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: "I've stored this secret" }));
    expect(screen.queryByText('sk_live_ab_the_full_secret_value')).not.toBeInTheDocument();
  });

  it('rotates a secret only after confirmation, then reveals the new one once', async () => {
    vi.mocked(listApiClients).mockResolvedValue([CLIENT]);
    const rotated: ApiClientCreated = { ...CLIENT, secret: 'sk_live_ab_rotated_secret_value' };
    vi.mocked(rotateApiClientSecret).mockResolvedValue(rotated);

    render(<ApiClientsSection organizationId="org-1" />);
    await waitFor(() => expect(screen.getByText('Safelytic integration')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('button', { name: 'Rotate' }));
    expect(rotateApiClientSecret).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole('button', { name: 'Rotate secret' }));

    await waitFor(() => expect(rotateApiClientSecret).toHaveBeenCalledWith('org-1', 'client-1'));
    await waitFor(() => expect(screen.getByText('sk_live_ab_rotated_secret_value')).toBeInTheDocument());
  });

  it('revokes a client only after confirmation and never fabricates success on failure', async () => {
    vi.mocked(listApiClients).mockResolvedValue([CLIENT]);
    vi.mocked(revokeApiClient).mockRejectedValue(new ApiError('Forbidden', { status: 403 }));

    render(<ApiClientsSection organizationId="org-1" />);
    await waitFor(() => expect(screen.getByText('Safelytic integration')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('button', { name: 'Revoke' }));
    await userEvent.click(screen.getByRole('button', { name: 'Revoke client' }));

    await waitFor(() => expect(screen.getByText(/don't have permission to revoke this API client/)).toBeInTheDocument());
  });
});
