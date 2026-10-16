import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { AttentionItem } from '../../services/api/attention';
import type { Site } from '../../services/api/sites';
import { AttentionList } from './AttentionList';

function makeAttentionItem(overrides: Partial<AttentionItem> = {}): AttentionItem {
  return {
    category: 'SIGNIFICANT_ANOMALY',
    priority: 'HIGH',
    title: 'Vehicle incidents above baseline',
    explanation: 'Vehicle incidents this period are above the recent baseline.',
    scope: 'organization',
    site_id: null,
    as_of: { as_of: '2026-06-01T00:00:00Z', generated_at: '2026-06-01T00:05:00Z', window_days: 90 },
    evidence: [{ evidence_type: 'safety_event', reference_id: 'evt-1', label: null }],
    limitation: null,
    reference: 'ref-anomaly-vehicle-incidents',
    ...overrides,
  };
}

function makeSite(overrides: Partial<Site> = {}): Site {
  return { id: 'site-1', name: 'North Yard', location: null, country: null, status: 'ACTIVE', organization_id: 'org-1', ...overrides };
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

  it('renders the human-readable priority label, not the raw backend enum, for every supported priority', () => {
    const items = [
      makeAttentionItem({ reference: 'ref-low', title: 'Low item', priority: 'LOW' }),
      makeAttentionItem({ reference: 'ref-moderate', title: 'Moderate item', priority: 'MODERATE' }),
      makeAttentionItem({ reference: 'ref-high', title: 'High item', priority: 'HIGH' }),
      makeAttentionItem({ reference: 'ref-critical', title: 'Critical item', priority: 'CRITICAL' }),
    ];
    render(<AttentionList items={items} />);

    expect(screen.getByText('Low')).toBeInTheDocument();
    expect(screen.getByText('Moderate')).toBeInTheDocument();
    expect(screen.getByText('High')).toBeInTheDocument();
    expect(screen.getByText('Critical')).toBeInTheDocument();
    expect(screen.queryByText('LOW')).not.toBeInTheDocument();
    expect(screen.queryByText('MODERATE')).not.toBeInTheDocument();
    expect(screen.queryByText('HIGH')).not.toBeInTheDocument();
    expect(screen.queryByText('CRITICAL')).not.toBeInTheDocument();
  });

  it('renders title, priority badge, plain-language category, and explanation', () => {
    render(
      <AttentionList
        items={[
          makeAttentionItem({
            title: 'Repeated PPE non-compliance',
            priority: 'CRITICAL',
            category: 'RECURRING_PATTERN',
            explanation: 'PPE non-compliance recurred across the last three inspections.',
          }),
        ]}
      />,
    );

    expect(screen.getByText('Repeated PPE non-compliance')).toBeInTheDocument();
    expect(screen.getByText('Critical')).toBeInTheDocument();
    expect(screen.getByText(/Recurring pattern/)).toBeInTheDocument();
    expect(screen.getByText('PPE non-compliance recurred across the last three inspections.')).toBeInTheDocument();
  });

  it('resolves a site label from the provided site list by matching site_id — the DTO itself carries no label', () => {
    render(
      <AttentionList
        items={[makeAttentionItem({ site_id: 'site-1', scope: 'site' })]}
        sites={[makeSite({ id: 'site-1', name: 'North Yard' })]}
      />,
    );
    expect(screen.getByText(/North Yard/)).toBeInTheDocument();
  });

  it('shows no site suffix, and never a fabricated name, when the site_id has no match in the provided site list', () => {
    render(<AttentionList items={[makeAttentionItem({ site_id: 'site-unknown', scope: 'site' })]} sites={[makeSite({ id: 'site-1', name: 'North Yard' })]} />);
    expect(screen.queryByText(/North Yard/)).not.toBeInTheDocument();
    expect(screen.queryByText('site-unknown')).not.toBeInTheDocument();
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
