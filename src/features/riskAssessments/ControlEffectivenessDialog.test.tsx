import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ControlEffectivenessDialog } from './ControlEffectivenessDialog';
import type { RiskControl } from '../../services/api/riskAssessments';

vi.mock('../../services/api/riskAssessments', () => ({
  assessControlEffectiveness: vi.fn(),
}));

import { assessControlEffectiveness } from '../../services/api/riskAssessments';

const CONTROL: RiskControl = {
  id: 'control-1',
  finding_id: 'finding-1',
  description: 'Reversing spotter procedure',
  control_type: 'ADMINISTRATIVE',
  status: 'IN_PLACE',
  owner_user_id: null,
  reference: null,
  effectiveness: 'NOT_ASSESSED',
  effectiveness_rationale: null,
  assessed_at: null,
  assessed_by_user_id: null,
  evidence: [],
  created_at: '2026-06-01T00:00:00Z',
  updated_at: '2026-06-01T00:00:00Z',
};

/**
 * SIE Milestone UI-02 Part 6: the control-effectiveness assessment
 * dialog always uses the dedicated `assess-effectiveness` mutation
 * (SIE Milestone 29A's own single authoritative path), requires a
 * rationale, and never fabricates success before the server confirms.
 */
describe('ControlEffectivenessDialog', () => {
  it('requires a rationale — the backend requires it too', async () => {
    render(
      <ControlEffectivenessDialog
        isOpen
        onClose={() => {}}
        organizationId="org-1"
        assessmentId="assessment-1"
        findingId="finding-1"
        control={CONTROL}
        onAssessed={() => {}}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: 'Record assessment' }));
    expect(screen.getByRole('alert')).toHaveTextContent('A rationale is required');
    expect(assessControlEffectiveness).not.toHaveBeenCalled();
  });

  it('calls the dedicated assess-effectiveness endpoint, never a generic finding update', async () => {
    vi.mocked(assessControlEffectiveness).mockResolvedValue({ ...CONTROL, effectiveness: 'EFFECTIVE', effectiveness_rationale: 'Spotter present on every shift.' });
    const onAssessed = vi.fn();
    const onClose = vi.fn();

    render(
      <ControlEffectivenessDialog
        isOpen
        onClose={onClose}
        organizationId="org-1"
        assessmentId="assessment-1"
        findingId="finding-1"
        control={CONTROL}
        onAssessed={onAssessed}
      />,
    );

    await userEvent.selectOptions(screen.getByLabelText('Effectiveness'), 'EFFECTIVE');
    await userEvent.type(screen.getByLabelText('Rationale'), 'Spotter present on every shift.');
    await userEvent.click(screen.getByRole('button', { name: 'Record assessment' }));

    await waitFor(() =>
      expect(assessControlEffectiveness).toHaveBeenCalledWith(
        'org-1',
        'assessment-1',
        'finding-1',
        'control-1',
        expect.objectContaining({ effectiveness_rating: 'EFFECTIVE', effectiveness_rationale: 'Spotter present on every shift.' }),
        expect.any(String),
      ),
    );
    await waitFor(() => expect(onAssessed).toHaveBeenCalledWith(expect.objectContaining({ effectiveness: 'EFFECTIVE' })));
    expect(onClose).toHaveBeenCalled();
  });

  it('never offers NOT_ASSESSED as a target — the backend rejects it as a conclusion', () => {
    render(
      <ControlEffectivenessDialog
        isOpen
        onClose={() => {}}
        organizationId="org-1"
        assessmentId="assessment-1"
        findingId="finding-1"
        control={CONTROL}
        onAssessed={() => {}}
      />,
    );
    const select = screen.getByLabelText('Effectiveness') as HTMLSelectElement;
    const values = Array.from(select.options).map((option) => option.value);
    expect(values).not.toContain('NOT_ASSESSED');
  });

  it('on failure, preserves the entered rationale and shows an actionable error — never fabricates success', async () => {
    vi.mocked(assessControlEffectiveness).mockRejectedValue(new Error('Assessment is not editable.'));
    const onAssessed = vi.fn();
    const onClose = vi.fn();

    render(
      <ControlEffectivenessDialog
        isOpen
        onClose={onClose}
        organizationId="org-1"
        assessmentId="assessment-1"
        findingId="finding-1"
        control={CONTROL}
        onAssessed={onAssessed}
      />,
    );

    await userEvent.type(screen.getByLabelText('Rationale'), 'Spotter present on every shift.');
    await userEvent.click(screen.getByRole('button', { name: 'Record assessment' }));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Assessment is not editable.'));
    expect(onAssessed).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Rationale')).toHaveValue('Spotter present on every shift.');
  });
});
