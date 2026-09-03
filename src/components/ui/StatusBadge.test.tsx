import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { StatusBadge } from './StatusBadge';
import { PriorityBadge } from './PriorityBadge';

describe('StatusBadge', () => {
  it('renders the label as visible text, not only a color', () => {
    render(<StatusBadge tone="critical" label="Quarantined" />);
    expect(screen.getByText('Quarantined')).toBeInTheDocument();
  });

  it('renders an icon alongside the label (status is never color-only, §18)', () => {
    const { container } = render(<StatusBadge tone="success" label="Closed" />);
    expect(container.querySelector('svg')).toBeInTheDocument();
  });
});

describe('PriorityBadge', () => {
  it.each([
    ['low', 'Low'],
    ['medium', 'Medium'],
    ['high', 'High'],
    ['critical', 'Critical'],
  ] as const)('renders the correct label for priority=%s', (priority, expectedLabel) => {
    render(<PriorityBadge priority={priority} />);
    expect(screen.getByText(expectedLabel)).toBeInTheDocument();
  });
});
