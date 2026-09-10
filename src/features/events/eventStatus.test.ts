import { describe, expect, it } from 'vitest';
import { eventStatusLabel, eventStatusTone, formatCanonicalLabel } from './eventStatus';

describe('eventStatusTone/eventStatusLabel', () => {
  it('gives the fixture-era known statuses their considered tone/label', () => {
    expect(eventStatusTone('open')).toBe('informational');
    expect(eventStatusLabel('open')).toBe('Open');
    expect(eventStatusTone('under_review')).toBe('warning');
    expect(eventStatusLabel('under_review')).toBe('Under review');
    expect(eventStatusTone('closed')).toBe('success');
    expect(eventStatusLabel('closed')).toBe('Closed');
    expect(eventStatusTone('quarantined')).toBe('neutral');
    expect(eventStatusLabel('quarantined')).toBe('Quarantined');
  });

  it('is case-insensitive on known values', () => {
    expect(eventStatusTone('OPEN')).toBe('informational');
    expect(eventStatusLabel('OPEN')).toBe('Open');
  });

  it('never coerces an unrecognized real backend status into a fixture-era one — falls back to neutral with its own formatted value', () => {
    expect(eventStatusTone('IN_PROGRESS')).toBe('neutral');
    expect(eventStatusLabel('IN_PROGRESS')).toBe('In Progress');
    expect(eventStatusTone('resolved-external')).toBe('neutral');
    expect(eventStatusLabel('resolved-external')).toBe('Resolved External');
  });
});

describe('formatCanonicalLabel', () => {
  it('turns an ALL_CAPS canonical value into a short, readable label', () => {
    expect(formatCanonicalLabel('INCIDENT')).toBe('Incident');
    expect(formatCanonicalLabel('NEAR_MISS')).toBe('Near miss');
    expect(formatCanonicalLabel('PROPERTY_DAMAGE')).toBe('Property damage');
  });
});
