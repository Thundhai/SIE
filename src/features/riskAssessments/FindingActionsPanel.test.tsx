import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthProviderStub } from '../../test/authTestUtils';
import { FindingActionsPanel } from './FindingActionsPanel';

vi.mock('../../services/api/riskAssessments', () => ({
  listFindingActions: vi.fn(),
  createFindingAction: vi.fn(),
  linkFindingAction: vi.fn(),
  unlinkFindingAction: vi.fn(),
}));
vi.mock('../actions/useActionRepository', () => ({
  useActionRepository: vi.fn(),
}));

import {
  createFindingAction,
  linkFindingAction,
  listFindingActions,
  unlinkFindingAction,
} from '../../services/api/riskAssessments';
import { useActionRepository } from '../actions/useActionRepository';

const FAKE_REPOSITORY = {
  list: vi.fn(async () => ({ items: [], total: 0, page: 1, pageSize: 10 })),
  getById: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  reassign: vi.fn(),
  updateStatus: vi.fn(),
  listSiteOptions: vi.fn(async () => []),
  listOwnerOptions: vi.fn(async () => []),
  isFixtureBacked: false,
};

function renderPanel(isEditable = true, hasPermission: (permission: string) => boolean = () => true) {
  return render(
    <AuthProviderStub value={{ hasPermission }}>
      <MemoryRouter>
        <FindingActionsPanel organizationId="org-1" assessmentId="assessment-1" findingId="finding-1" isEditable={isEditable} />
      </MemoryRouter>
    </AuthProviderStub>,
  );
}

/**
 * SIE Milestone UI-02 Part 8-9: a finding's linked actions — real data,
 * create-from-finding, link/unlink, all permission-gated on the real
 * effective permissions, never a raw action-id UUID as a label.
 */
describe('FindingActionsPanel', () => {
  beforeEach(() => {
    vi.mocked(useActionRepository).mockReturnValue(FAKE_REPOSITORY as unknown as ReturnType<typeof useActionRepository>);
  });

  it('renders real linked actions without a raw action-id UUID label', async () => {
    vi.mocked(listFindingActions).mockResolvedValue({
      items: [
        {
          id: 'link-1',
          finding_id: 'finding-1',
          action_id: 'action-uuid-1',
          action_title: 'Install edge protection',
          action_status: 'OPEN',
          created_at: '2026-06-01T00:00:00Z',
          created_by_user_id: null,
          created_by_api_client_id: null,
        },
      ],
      total: 1,
    });

    renderPanel();
    await waitFor(() => expect(screen.getByText('Install edge protection')).toBeInTheDocument());
    expect(screen.queryByText('action-uuid-1')).not.toBeInTheDocument();
  });

  it('shows an honest empty state with no linked actions', async () => {
    vi.mocked(listFindingActions).mockResolvedValue({ items: [], total: 0 });

    renderPanel();
    await waitFor(() => expect(screen.getByText('No actions linked to this finding')).toBeInTheDocument());
  });

  it('hides create/link controls without permission', async () => {
    vi.mocked(listFindingActions).mockResolvedValue({ items: [], total: 0 });

    renderPanel(true, () => false);
    await waitFor(() => expect(screen.getByText('No actions linked to this finding')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: 'Create action' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Link existing action' })).not.toBeInTheDocument();
  });

  it('creates an action from the finding and refreshes the list', async () => {
    vi.mocked(listFindingActions).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(createFindingAction).mockResolvedValue({
      id: 'link-2',
      finding_id: 'finding-1',
      action_id: 'action-uuid-2',
      action_title: 'Install edge protection',
      action_status: 'OPEN',
      created_at: '2026-06-01T00:00:00Z',
      created_by_user_id: null,
      created_by_api_client_id: null,
    });

    renderPanel();
    await waitFor(() => expect(screen.getByText('No actions linked to this finding')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('button', { name: 'Create action' }));
    await userEvent.type(screen.getByLabelText('Title'), 'Install edge protection');
    await userEvent.selectOptions(screen.getByLabelText('Action type'), 'PREVENTIVE');

    vi.mocked(listFindingActions).mockResolvedValue({
      items: [
        {
          id: 'link-2',
          finding_id: 'finding-1',
          action_id: 'action-uuid-2',
          action_title: 'Install edge protection',
          action_status: 'OPEN',
          created_at: '2026-06-01T00:00:00Z',
          created_by_user_id: null,
          created_by_api_client_id: null,
        },
      ],
      total: 1,
    });

    await userEvent.click(screen.getByRole('button', { name: 'Create action' }));

    await waitFor(() => expect(createFindingAction).toHaveBeenCalled());
    await waitFor(() => expect(screen.getAllByText('Install edge protection').length).toBeGreaterThan(0));
  });

  it('unlinks a linked action', async () => {
    vi.mocked(listFindingActions).mockResolvedValue({
      items: [
        {
          id: 'link-1',
          finding_id: 'finding-1',
          action_id: 'action-uuid-1',
          action_title: 'Install edge protection',
          action_status: 'OPEN',
          created_at: '2026-06-01T00:00:00Z',
          created_by_user_id: null,
          created_by_api_client_id: null,
        },
      ],
      total: 1,
    });
    vi.mocked(unlinkFindingAction).mockResolvedValue(undefined);

    renderPanel();
    await waitFor(() => expect(screen.getByText('Install edge protection')).toBeInTheDocument());

    vi.mocked(listFindingActions).mockResolvedValue({ items: [], total: 0 });
    await userEvent.click(screen.getByRole('button', { name: 'Unlink' }));

    await waitFor(() => expect(unlinkFindingAction).toHaveBeenCalledWith('org-1', 'assessment-1', 'finding-1', 'action-uuid-1'));
    await waitFor(() => expect(screen.getByText('No actions linked to this finding')).toBeInTheDocument());
  });

  it('links an existing action found via search', async () => {
    vi.mocked(listFindingActions).mockResolvedValue({ items: [], total: 0 });
    FAKE_REPOSITORY.list.mockResolvedValue({
      items: [{ id: 'action-uuid-3', title: 'Repair loading dock light', status: 'OPEN' }],
      total: 1,
      page: 1,
      pageSize: 10,
    });
    vi.mocked(linkFindingAction).mockResolvedValue({
      id: 'link-3',
      finding_id: 'finding-1',
      action_id: 'action-uuid-3',
      action_title: 'Repair loading dock light',
      action_status: 'OPEN',
      created_at: '2026-06-01T00:00:00Z',
      created_by_user_id: null,
      created_by_api_client_id: null,
    });

    renderPanel();
    await waitFor(() => expect(screen.getByText('No actions linked to this finding')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('button', { name: 'Link existing action' }));
    await userEvent.type(screen.getByLabelText('Search actions'), 'loading dock');

    await waitFor(() => expect(screen.getByText('Repair loading dock light')).toBeInTheDocument());
    await userEvent.click(screen.getByRole('button', { name: 'Link' }));

    await waitFor(() => expect(linkFindingAction).toHaveBeenCalledWith('org-1', 'assessment-1', 'finding-1', 'action-uuid-3'));
  });
});
