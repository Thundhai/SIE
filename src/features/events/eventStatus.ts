import type { StatusTone } from '../../types/common';

/**
 * `SafetyEventSummary.status`/`SafetyEventDetail.status` is a plain
 * string (see `types/events.ts`'s own docstring) — the real backend's
 * `status` column is free text, not a governed enum. These two functions
 * are the one place an arbitrary status string is turned into a
 * `StatusBadge` tone/label, shared by `EventsPage` and `EventDetailPage`
 * so the two screens can never disagree.
 *
 * The fixture's own four example values (`open`/`under_review`/
 * `closed`/`quarantined`) get a considered tone; anything else — any
 * real backend status this milestone can't know in advance — falls back
 * to a neutral tone and its own value, formatted for readability, rather
 * than being coerced into one of those four (§16: never transform a real
 * value to match a fixture example).
 */

const KNOWN_STATUS_TONE: Record<string, StatusTone> = {
  open: 'informational',
  under_review: 'warning',
  closed: 'success',
  quarantined: 'neutral',
};

const KNOWN_STATUS_LABEL: Record<string, string> = {
  open: 'Open',
  under_review: 'Under review',
  closed: 'Closed',
  quarantined: 'Quarantined',
};

function normalize(status: string): string {
  return status.trim().toLowerCase();
}

export function eventStatusTone(status: string): StatusTone {
  return KNOWN_STATUS_TONE[normalize(status)] ?? 'neutral';
}

export function eventStatusLabel(status: string): string {
  const key = normalize(status);
  if (KNOWN_STATUS_LABEL[key]) return KNOWN_STATUS_LABEL[key];
  return status
    .replace(/[_-]+/g, ' ')
    .trim()
    .replace(/\w\S*/g, (word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase());
}

/** A short, human-readable label for a canonical, ALL_CAPS backend value
 * (e.g. `event_type`/`event_subtype`: "NEAR_MISS" -> "Near miss") — used
 * by `ApiEventRepository` to derive a display title/subtype from real
 * data that carries no separate free-text label. Purely a formatting
 * transform of the real value, never a substitution for it — the raw
 * canonical value itself is still shown alongside it (see
 * `EventDetailPage`'s Classification section). */
export function formatCanonicalLabel(value: string): string {
  return value
    .replace(/[_-]+/g, ' ')
    .trim()
    .toLowerCase()
    .replace(/^\w/, (c) => c.toUpperCase());
}
