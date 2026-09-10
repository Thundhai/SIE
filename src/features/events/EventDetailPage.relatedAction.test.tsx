import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { AuthProviderStub } from '../../test/authTestUtils';
import { EventDetailPage } from './EventDetailPage';

/**
 * Event Detail's "Related action" area (SIE Milestone 18, §8) — exercised
 * here entirely through the fixture repositories (`FixtureEventRepository`
 * + `FixtureActionRepository`), which is enough to prove the real
 * mechanism end-to-end: `RelatedActionSection` queries the real
 * `ActionRepository` interface by `sourceEventId`, exactly as
 * `ApiActionRepository` would against the live backend — see
 * `apiActionRepository.test.ts` for the API-specific mapping/filter
 * behavior, and `useActionRepository.ts` for why both repositories are
 * interchangeable here.
 */
function renderAt(eventId: string, canCreate = false) {
  return render(
    <AuthProviderStub value={canCreate ? { hasPermission: () => true } : undefined}>
      <MemoryRouter initialEntries={[`/events/${eventId}`]}>
        <Routes>
          <Route path="/events/:eventId" element={<EventDetailPage />} />
          <Route path="/actions/:actionId" element={<div>Action detail page</div>} />
        </Routes>
      </MemoryRouter>
    </AuthProviderStub>,
  );
}

describe('EventDetailPage — Related action', () => {
  it('shows the real related action when one exists for this event, never a fabricated one', async () => {
    // EVT-1001 has a real fixture action (ACT-2001) raised from it.
    renderAt('EVT-1001');
    await waitFor(() => expect(screen.getByRole('heading', { name: /Vehicle incident/ })).toBeInTheDocument());

    await waitFor(() =>
      expect(screen.getByText('Review reversing procedure at the Project North laydown area')).toBeInTheDocument(),
    );
    expect(screen.queryByText('No action has been raised for this event')).not.toBeInTheDocument();
  });

  it('navigates from Event Detail to the related Action', async () => {
    renderAt('EVT-1001');
    await waitFor(() =>
      expect(screen.getByText('Review reversing procedure at the Project North laydown area')).toBeInTheDocument(),
    );

    await userEvent.click(screen.getByText('Review reversing procedure at the Project North laydown area'));
    await waitFor(() => expect(screen.getByText('Action detail page')).toBeInTheDocument());
  });

  it('shows an honest empty state — never a fabricated action — when no action exists for this event', async () => {
    // EVT-1009 has no fixture action referencing it as a source event.
    renderAt('EVT-1009');
    await waitFor(() => expect(screen.getByRole('heading', { name: /Housekeeping deficiency/ })).toBeInTheDocument());

    await waitFor(() => expect(screen.getByText('No action has been raised for this event')).toBeInTheDocument());
  });

  it('offers "Create action" only when the caller has intervention:manage', async () => {
    renderAt('EVT-1009', false);
    await waitFor(() => expect(screen.getByText('No action has been raised for this event')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: 'Create action' })).not.toBeInTheDocument();
  });

  it('a permitted user can create an action from Event Detail, pre-linked to the source event', async () => {
    renderAt('EVT-1009', true);
    await waitFor(() => expect(screen.getByText('No action has been raised for this event')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('button', { name: 'Create action' }));
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveTextContent('This action will be linked to source event');
    expect(dialog).toHaveTextContent('EVT-1009');
  });
});
