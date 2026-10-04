import { afterEach, describe, expect, it, vi } from 'vitest';
import { getAuthMode } from './authMode';

describe('getAuthMode', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('defaults to "dev" under the test runner (MODE === "test")', () => {
    expect(getAuthMode()).toBe('dev');
  });

  it('is "dev" for a local development server build', () => {
    vi.stubEnv('MODE', 'development');
    expect(getAuthMode()).toBe('dev');
  });

  it('is "production" only when MODE is exactly "production"', () => {
    vi.stubEnv('MODE', 'production');
    expect(getAuthMode()).toBe('production');
  });

  it('treats an unrecognized MODE value as "production" — fails toward the safer, more restrictive mode', () => {
    vi.stubEnv('MODE', 'staging');
    expect(getAuthMode()).toBe('production');
  });
});
