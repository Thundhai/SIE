import { describe, expect, it } from 'vitest';
import { resolveInitialOrganization } from './organizationResolution';

describe('resolveInitialOrganization', () => {
  it('returns "none" for a user with zero organization memberships', () => {
    expect(resolveInitialOrganization([])).toEqual({ kind: 'none' });
  });

  it('selects the one organization a user with exactly one membership has', () => {
    const result = resolveInitialOrganization([
      { organization_id: 'org-1', organization_name: 'Only Org', role: 'ORG_ADMIN' },
    ]);
    expect(result).toEqual({ kind: 'selected', organizationId: 'org-1' });
  });

  it('is deterministic for multiple memberships — the lowest organization_id, independent of input order', () => {
    const memberships = [
      { organization_id: 'org-b', organization_name: 'Org B', role: 'VIEWER' },
      { organization_id: 'org-a', organization_name: 'Org A', role: 'ORG_ADMIN' },
    ];

    const forward = resolveInitialOrganization(memberships);
    const reversed = resolveInitialOrganization([...memberships].reverse());

    expect(forward).toEqual({ kind: 'selected', organizationId: 'org-a' });
    expect(reversed).toEqual({ kind: 'selected', organizationId: 'org-a' });
  });

  it('does not mutate the input array', () => {
    const memberships = [
      { organization_id: 'org-b', organization_name: 'Org B', role: 'VIEWER' },
      { organization_id: 'org-a', organization_name: 'Org A', role: 'ORG_ADMIN' },
    ];
    const original = [...memberships];

    resolveInitialOrganization(memberships);

    expect(memberships).toEqual(original);
  });
});
