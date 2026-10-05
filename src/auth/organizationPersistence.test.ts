import { afterEach, describe, expect, it } from 'vitest';
import {
  clearPersistedOrganizationId,
  persistActiveOrganizationId,
  readPersistedOrganizationId,
  resolveActiveOrganization,
} from './organizationPersistence';

afterEach(() => {
  window.sessionStorage.clear();
});

describe('organizationPersistence — sessionStorage read/write/clear', () => {
  it('returns null when nothing has been persisted', () => {
    expect(readPersistedOrganizationId()).toBeNull();
  });

  it('round-trips a persisted organization id', () => {
    persistActiveOrganizationId('org-b');
    expect(readPersistedOrganizationId()).toBe('org-b');
  });

  it('clears a persisted organization id', () => {
    persistActiveOrganizationId('org-b');
    clearPersistedOrganizationId();
    expect(readPersistedOrganizationId()).toBeNull();
  });

  it('uses sessionStorage, never localStorage', () => {
    persistActiveOrganizationId('org-b');
    expect(window.localStorage.getItem('sie.activeOrganizationId')).toBeNull();
    expect(window.sessionStorage.getItem('sie.activeOrganizationId')).toBe('org-b');
  });
});

const MEMBERSHIPS = [
  { organization_id: 'org-b', organization_name: 'Org B', role: 'ORG_ADMIN' },
  { organization_id: 'org-a', organization_name: 'Org A', role: 'VIEWER' },
];

describe('resolveActiveOrganization — persistence is a UI preference, never authorization', () => {
  it('SECURITY: prefers a persisted id only when it is present in the CURRENT authenticated memberships list', () => {
    const result = resolveActiveOrganization(MEMBERSHIPS, 'org-b');
    expect(result).toEqual({ kind: 'selected', organizationId: 'org-b' });
  });

  it('SECURITY: discards a persisted id absent from the current memberships list, falling back to the deterministic pick', () => {
    const result = resolveActiveOrganization(MEMBERSHIPS, 'org-does-not-exist');
    // Deterministic fallback (resolveInitialOrganization): lowest id by
    // string comparison -- 'org-a' < 'org-b'.
    expect(result).toEqual({ kind: 'selected', organizationId: 'org-a' });
  });

  it('SECURITY: a discarded invalid persisted id is actually removed from storage, not merely ignored once', () => {
    persistActiveOrganizationId('org-revoked');
    resolveActiveOrganization(MEMBERSHIPS, 'org-revoked');
    expect(readPersistedOrganizationId()).toBeNull();
  });

  it('falls back to the deterministic pick when nothing is persisted at all', () => {
    const result = resolveActiveOrganization(MEMBERSHIPS, null);
    expect(result).toEqual({ kind: 'selected', organizationId: 'org-a' });
  });

  it('zero memberships -> organization setup required, regardless of what is persisted', () => {
    const result = resolveActiveOrganization([], 'org-b');
    expect(result).toEqual({ kind: 'none' });
  });
});
