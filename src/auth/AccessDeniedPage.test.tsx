import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { AccessDeniedPage } from './AccessDeniedPage';

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/administration']}>
      <Routes>
        <Route path="/administration" element={<AccessDeniedPage />} />
        <Route path="/" element={<div>Home content</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('AccessDeniedPage', () => {
  it('announces itself as an alert with a clear, plain-language title', () => {
    renderPage();
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('Access denied');
  });

  it('provides a safe navigation path back to Home', async () => {
    renderPage();
    await userEvent.click(screen.getByRole('button', { name: 'Return to Home' }));
    expect(screen.getByText('Home content')).toBeInTheDocument();
  });

  it('never exposes a raw error/stack-trace style message — this is an authorization state, not a server failure', () => {
    renderPage();
    expect(screen.queryByText(/stack|exception|traceback/i)).not.toBeInTheDocument();
  });
});
