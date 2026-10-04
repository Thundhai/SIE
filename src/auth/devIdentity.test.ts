import { afterEach, describe, expect, it, vi } from 'vitest';
import { getDevIdentityConfig } from './devIdentity';

describe('getDevIdentityConfig', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('returns null when no dev identity is configured', () => {
    expect(getDevIdentityConfig()).toBeNull();
  });

  it('resolves a configured dev identity under the test/dev auth mode', () => {
    vi.stubEnv('VITE_DEV_USER_ID', 'user-1');
    vi.stubEnv('VITE_DEV_ORGANIZATION_ID', 'org-1');

    const config = getDevIdentityConfig();

    expect(config).not.toBeNull();
    expect(config?.userId).toBe('user-1');
    expect(config?.organizationId).toBe('org-1');
  });

  it('SECURITY: returns null in production mode even when both dev identity variables are set', () => {
    // This is the exact live misconfiguration the G3-0 audit flagged as
    // a real risk: VITE_DEV_USER_ID/VITE_DEV_ORGANIZATION_ID present in
    // a deployment's build environment must never be sufficient, on
    // their own, to activate development identity.
    vi.stubEnv('MODE', 'production');
    vi.stubEnv('VITE_DEV_USER_ID', 'user-1');
    vi.stubEnv('VITE_DEV_ORGANIZATION_ID', 'org-1');

    expect(getDevIdentityConfig()).toBeNull();
  });
});
