import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { GoverningStandardsSection } from './GoverningStandardsSection';
import { ApiError } from '../../services/api/errors';
import type {
  ActiveGoverningStandard,
  GoverningStandard,
  OrganizationGoverningStandardEntry,
} from '../../services/api/administration';

vi.mock('../../services/api/administration', () => ({
  listAvailableGoverningStandards: vi.fn(),
  listActiveGoverningStandards: vi.fn(),
  listGoverningStandardHistory: vi.fn(),
  selectGoverningStandard: vi.fn(),
  retireGoverningStandard: vi.fn(),
}));

import {
  listActiveGoverningStandards,
  listAvailableGoverningStandards,
  listGoverningStandardHistory,
  retireGoverningStandard,
  selectGoverningStandard,
} from '../../services/api/administration';

const AVAILABLE_STANDARD: GoverningStandard = {
  id: 'std-1',
  scope_type: 'GLOBAL',
  organization_id: null,
  name: 'ISO 45001',
  short_description: 'Occupational health and safety management systems.',
  issuing_organization: 'ISO',
  standard_type: 'INTERNATIONAL_STANDARD',
  regions: [],
  industry_sectors: [],
  version: '2018',
  publication_date: null,
  effective_date: null,
  verification_status: 'VERIFIED',
  is_active: true,
};

const RETIRED_STANDARD: GoverningStandard = { ...AVAILABLE_STANDARD, id: 'std-2', name: 'OHSAS 18001' };

const ACTIVE_ENTRY: ActiveGoverningStandard = {
  standard: AVAILABLE_STANDARD,
  selection: {
    id: 'sel-1',
    organization_id: 'org-1',
    standard_id: 'std-1',
    status: 'SELECTED',
    effective_date: null,
    retirement_date: null,
    rationale: 'Adopted org-wide.',
    decided_at: '2026-01-01T00:00:00Z',
    configured_by_user_id: 'user-1',
    configured_by_api_client_id: null,
  },
};

const HISTORY_RECORD: OrganizationGoverningStandardEntry = {
  id: 'sel-2',
  organization_id: 'org-1',
  standard_id: 'std-2',
  status: 'RETIRED',
  effective_date: null,
  retirement_date: '2026-02-01T00:00:00Z',
  rationale: 'Superseded by ISO 45001.',
  decided_at: '2026-02-01T00:00:00Z',
  configured_by_user_id: 'user-1',
  configured_by_api_client_id: null,
};

/**
 * M43A's own core principle: AVAILABLE (catalogue) and SELECTED (Active
 * Governing Set) are two structurally separate lists here — this suite
 * asserts they never get merged or conflated.
 */
describe('GoverningStandardsSection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders available and selected standards as two separate lists', async () => {
    vi.mocked(listAvailableGoverningStandards).mockResolvedValue({ items: [AVAILABLE_STANDARD], total: 1 });
    vi.mocked(listActiveGoverningStandards).mockResolvedValue({ items: [ACTIVE_ENTRY], total: 1 });

    render(<GoverningStandardsSection organizationId="org-1" />);

    await waitFor(() => expect(screen.getByText('Governing standards — available')).toBeInTheDocument());
    expect(screen.getByText('Governing standards — selected')).toBeInTheDocument();
    expect(screen.getAllByText('ISO 45001')).toHaveLength(2);
  });

  it('shows empty states independently for available and selected', async () => {
    vi.mocked(listAvailableGoverningStandards).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(listActiveGoverningStandards).mockResolvedValue({ items: [], total: 0 });

    render(<GoverningStandardsSection organizationId="org-1" />);

    await waitFor(() => expect(screen.getByText('No standards available')).toBeInTheDocument());
    expect(screen.getByText('No governing standards selected')).toBeInTheDocument();
  });

  it('selecting a standard calls the select endpoint and refreshes both lists', async () => {
    vi.mocked(listAvailableGoverningStandards).mockResolvedValue({ items: [AVAILABLE_STANDARD], total: 1 });
    vi.mocked(listActiveGoverningStandards).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(selectGoverningStandard).mockResolvedValue(ACTIVE_ENTRY.selection);

    render(<GoverningStandardsSection organizationId="org-1" />);
    await waitFor(() => expect(screen.getByText('No governing standards selected')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('button', { name: 'Select' }));
    const dialog = within(screen.getByRole('dialog'));
    expect(dialog.getByText('ISO 45001')).toBeInTheDocument();
    await userEvent.click(dialog.getByRole('button', { name: 'Select standard' }));

    await waitFor(() =>
      expect(selectGoverningStandard).toHaveBeenCalledWith(
        'org-1',
        { standardId: 'std-1', effectiveDate: undefined, rationale: undefined },
        expect.any(String),
      ),
    );
    await waitFor(() => expect(listAvailableGoverningStandards).toHaveBeenCalledTimes(2));
    expect(listActiveGoverningStandards).toHaveBeenCalledTimes(2);
  });

  it('retiring a standard calls the retire endpoint and refreshes both lists', async () => {
    vi.mocked(listAvailableGoverningStandards).mockResolvedValue({ items: [AVAILABLE_STANDARD], total: 1 });
    vi.mocked(listActiveGoverningStandards).mockResolvedValue({ items: [ACTIVE_ENTRY], total: 1 });
    vi.mocked(retireGoverningStandard).mockResolvedValue({ ...ACTIVE_ENTRY.selection, status: 'RETIRED' });

    render(<GoverningStandardsSection organizationId="org-1" />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Retire' })).toBeInTheDocument());

    await userEvent.click(screen.getByRole('button', { name: 'Retire' }));
    const dialog = within(screen.getByRole('dialog'));
    await userEvent.click(dialog.getByRole('button', { name: 'Retire standard' }));

    await waitFor(() =>
      expect(retireGoverningStandard).toHaveBeenCalledWith(
        'org-1',
        'std-1',
        { retirementDate: undefined, rationale: undefined },
        expect.any(String),
      ),
    );
    await waitFor(() => expect(listActiveGoverningStandards).toHaveBeenCalledTimes(2));
  });

  it('resolves a retired standard name in history from the available catalogue, not just active selections', async () => {
    vi.mocked(listAvailableGoverningStandards).mockResolvedValue({ items: [AVAILABLE_STANDARD, RETIRED_STANDARD], total: 2 });
    vi.mocked(listActiveGoverningStandards).mockResolvedValue({ items: [ACTIVE_ENTRY], total: 1 });
    vi.mocked(listGoverningStandardHistory).mockResolvedValue({ items: [HISTORY_RECORD], total: 1, page: 1, page_size: 50 });

    render(<GoverningStandardsSection organizationId="org-1" />);
    await waitFor(() => expect(screen.getByText('Governing standards — available')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('button', { name: 'View history' }));

    const historyTable = await screen.findByRole('table');
    await waitFor(() => expect(within(historyTable).getByText('OHSAS 18001')).toBeInTheDocument());
    expect(within(historyTable).queryByText('std-2')).not.toBeInTheDocument();
  });
});
