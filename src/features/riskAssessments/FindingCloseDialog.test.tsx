import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { FindingCloseDialog } from './FindingCloseDialog';
import type { RiskAssessmentFinding } from '../../services/api/riskAssessments';

vi.mock('../../services/api/riskAssessments', () => ({
  closeFinding: vi.fn(),
}));

import { closeFinding } from '../../services/api/riskAssessments';

const FINDING = {
  id: 'finding-1',
  assessment_id: 'assessment-1',
  title: 'Reversing near miss at loading dock',
  status: 'OPEN',
  likelihood: 3,
} as unknown as RiskAssessmentFinding;

/**
 * SIE Milestone UI-02 Part 11: finding closure always goes through the
 * dedicated `POST .../findings/{finding_id}/close` route with a
 * required, non-blank closure reason — never a generic status PATCH.
 */
describe('FindingCloseDialog', () => {
  it('requires a non-blank closure reason', async () => {
    render(
      <FindingCloseDialog isOpen onClose={() => {}} organizationId="org-1" assessmentId="assessment-1" finding={FINDING} onClosed={() => {}} />,
    );

    await userEvent.click(screen.getByRole('button', { name: 'Close finding' }));
    expect(screen.getByRole('alert')).toHaveTextContent('A closure reason is required.');
    expect(closeFinding).not.toHaveBeenCalled();
  });

  it('calls the dedicated close endpoint and refreshes with the authoritative result', async () => {
    const closed = { ...FINDING, status: 'CLOSED' };
    vi.mocked(closeFinding).mockResolvedValue(closed as RiskAssessmentFinding);
    const onClosed = vi.fn();
    const onClose = vi.fn();

    render(
      <FindingCloseDialog isOpen onClose={onClose} organizationId="org-1" assessmentId="assessment-1" finding={FINDING} onClosed={onClosed} />,
    );

    await userEvent.type(screen.getByLabelText('Closure reason'), 'Spotter procedure implemented and verified.');
    await userEvent.click(screen.getByRole('button', { name: 'Close finding' }));

    await waitFor(() =>
      expect(closeFinding).toHaveBeenCalledWith('org-1', 'assessment-1', 'finding-1', 'Spotter procedure implemented and verified.'),
    );
    await waitFor(() => expect(onClosed).toHaveBeenCalledWith(expect.objectContaining({ status: 'CLOSED' })));
    expect(onClose).toHaveBeenCalled();
  });

  it('on failure, shows an actionable error and never fabricates closure', async () => {
    vi.mocked(closeFinding).mockRejectedValue(new Error('A finding must be rated before it can be closed.'));
    const onClosed = vi.fn();

    render(
      <FindingCloseDialog isOpen onClose={() => {}} organizationId="org-1" assessmentId="assessment-1" finding={FINDING} onClosed={onClosed} />,
    );

    await userEvent.type(screen.getByLabelText('Closure reason'), 'Attempting closure.');
    await userEvent.click(screen.getByRole('button', { name: 'Close finding' }));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('A finding must be rated before it can be closed.'));
    expect(onClosed).not.toHaveBeenCalled();
  });
});
