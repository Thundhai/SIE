import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { EmptyState } from './EmptyState';
import { ErrorState } from './ErrorState';
import { LoadingState } from './LoadingState';

describe('LoadingState', () => {
  it('announces itself via role=status so it is exercised even without visual inspection', () => {
    render(<LoadingState label="Loading events…" />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading events…');
  });
});

describe('EmptyState', () => {
  it('renders the title and description for a legitimate zero-result state', () => {
    render(<EmptyState title="No events match your filters" description="Try adjusting or clearing your filters." />);
    expect(screen.getByText('No events match your filters')).toBeInTheDocument();
    expect(screen.getByText('Try adjusting or clearing your filters.')).toBeInTheDocument();
  });
});

describe('ErrorState', () => {
  it('renders as an alert and calls onRetry when the retry button is activated', async () => {
    const onRetry = vi.fn();
    render(<ErrorState description="Could not reach the SIE API." onRetry={onRetry} />);

    expect(screen.getByRole('alert')).toHaveTextContent('Could not reach the SIE API.');
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('omits the retry button when no onRetry is given', () => {
    render(<ErrorState description="Could not reach the SIE API." />);
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument();
  });
});
