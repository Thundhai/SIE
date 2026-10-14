import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { AttentionItem } from '../../services/api/attention';
import { AttentionList } from './AttentionList';

function makeAttentionItem(overrides: Partial<AttentionItem> = {}): AttentionItem {
  return {
    category: 'SIGNIFICANT_ANOMALY',
    priority: 'HIGH',
    title: 'Vehicle incidents above baseline',
    explanation: 'Vehicle incidents this period are above the recent baseline.',
    scope: 'organization',
    site_id: null,
    site_label: null,
    as_of: '2026-06-01T00:00:00Z',
    window_days: 90,
    evidence: { source: 'enterprise_anomaly', calculation_version: 'v1', entity_ids: [], event_ids: ['evt-1'] },
    limitation: null,
    reference: 'ref-anomaly-vehicle-incidents',
    ...overrides,
  };
}

describe('AttentionList', () => {
  it('shows an honest empty state when there are no items', () => {
    render(<AttentionList items={[]} />);
    expect(screen.getByText('Nothing needs attention right now')).toBeInTheDocument();
    expect(screen.getByText('No signal in the current window met the threshold for attention.')).toBeInTheDocument();
  });

  it('accepts custom empty-state copy', () => {
    render(<AttentionList items={[]} emptyTitle="Custom title" emptyDescription="Custom description" />);
    expect(screen.getByText('Custom title')).toBeInTheDocument();
    expect(screen.getByText('Custom description')).toBeInTheDocument();
  });

  it('renders items in the exact order given — never re-sorted by this component', () => {
    const items = [
      makeAttentionItem({ reference: 'ref-1', title: 'Critical item', priority: 'CRITICAL' }),
      makeAttentionItem({ reference: 'ref-2', title: 'Low item', priority: 'LOW' }),
      makeAttentionItem({ reference: 'ref-3', title: 'High item', priority: 'HIGH' }),
    ];
    render(<AttentionList items={items} />);

    const titles = screen.getAllByText(/Critical item|Low item|High item/).map((el) => el.textContent);
    expect(titles).toEqual(['Critical item', 'Low item', 'High item']);
  });

  it('renders title, priority badge, plain-language category, site label, and explanation', () => {
    render(
      <AttentionList
        items={[
          makeAttentionItem({
            title: 'Repeated PPE non-compliance',
            priority: 'CRITICAL',
            category: 'RECURRING_PATTERN',
            site_label: 'North Yard',
            explanation: 'PPE non-compliance recurred across the last three inspections.',
          }),
        ]}
      />,
    );

    expect(screen.getByText('Repeated PPE non-compliance')).toBeInTheDocument();
    expect(screen.getByText('CRITICAL')).toBeInTheDocument();
    expect(screen.getByText(/Recurring pattern/)).toBeInTheDocument();
    expect(screen.getByText(/North Yard/)).toBeInTheDocument();
    expect(screen.getByText('PPE non-compliance recurred across the last three inspections.')).toBeInTheDocument();
  });

  it('renders a limitation note when the backend supplies one, honestly rather than hiding it', () => {
    render(<AttentionList items={[makeAttentionItem({ limitation: 'Based on a partial window — fewer than 10 events.' })]} />);
    expect(screen.getByText('Based on a partial window — fewer than 10 events.')).toBeInTheDocument();
  });

  it('falls back to a plain-formatted label for an unmapped category, never hiding or crashing on it', () => {
    render(<AttentionList items={[makeAttentionItem({ category: 'SOME_FUTURE_CATEGORY' as AttentionItem['category'] })]} />);
    expect(screen.getByText(/Some future category/)).toBeInTheDocument();
  });

  it('never offers a decision-recording, review, or "record" action — this delivery is read-only', () => {
    render(<AttentionList items={[makeAttentionItem()]} />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.queryByText(/decision/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/recorded/i)).not.toBeInTheDocument();
  });
});
