import { cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

type Listener<T> = (arg: T) => void;

class FakeUserManager {
  getUser = vi.fn();
  signinRedirect = vi.fn().mockResolvedValue(undefined);
  signinRedirectCallback = vi.fn().mockResolvedValue(undefined);
  signinSilentCallback = vi.fn().mockResolvedValue(undefined);
  removeUser = vi.fn().mockResolvedValue(undefined);

  private userLoadedListeners: Listener<unknown>[] = [];
  private userUnloadedListeners: Listener<void>[] = [];

  events = {
    addUserLoaded: (fn: Listener<unknown>) => this.userLoadedListeners.push(fn),
    removeUserLoaded: (fn: Listener<unknown>) => {
      this.userLoadedListeners = this.userLoadedListeners.filter((l) => l !== fn);
    },
    addUserUnloaded: (fn: Listener<void>) => this.userUnloadedListeners.push(fn),
    removeUserUnloaded: (fn: Listener<void>) => {
      this.userUnloadedListeners = this.userUnloadedListeners.filter((l) => l !== fn);
    },
    addSilentRenewError: vi.fn(),
    removeSilentRenewError: vi.fn(),
  };

  emitUserLoaded(user: unknown) {
    this.userLoadedListeners.forEach((fn) => fn(user));
  }

  emitUserUnloaded() {
    this.userUnloadedListeners.forEach((fn) => fn());
  }
}

let fakeManager: FakeUserManager;
let lastUserManagerSettings: Record<string, unknown> | undefined;

vi.mock('oidc-client-ts', () => ({
  // A constructor function (not an arrow function, which `new` cannot
  // invoke) that always returns the current `fakeManager` instance,
  // reassigned fresh in `beforeEach` below.
  UserManager: vi.fn(function UserManager(settings: Record<string, unknown>) {
    lastUserManagerSettings = settings;
    return fakeManager;
  }),
  WebStorageStateStore: vi.fn(),
}));

const { resetOidcUserManagerForTests, useOidcSession } = await import('./oidcSession');

function configureOidcProvider() {
  vi.stubEnv('VITE_OIDC_AUTHORITY', 'https://idp.example.com');
  vi.stubEnv('VITE_OIDC_CLIENT_ID', 'sie-spa');
}

describe('useOidcSession', () => {
  beforeEach(() => {
    fakeManager = new FakeUserManager();
    lastUserManagerSettings = undefined;
    resetOidcUserManagerForTests();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllEnvs();
  });

  it('resolves to "unauthenticated" when no OIDC provider is configured at all', async () => {
    // Deliberately no configureOidcProvider() call.
    const { result } = renderHook(() => useOidcSession());

    await waitFor(() => expect(result.current.status).toBe('unauthenticated'));
  });

  it('resolves to "unauthenticated" when the UserManager has no stored user', async () => {
    configureOidcProvider();
    fakeManager.getUser.mockResolvedValue(null);

    const { result } = renderHook(() => useOidcSession());

    await waitFor(() => expect(result.current.status).toBe('unauthenticated'));
    expect(result.current.user).toBeNull();
  });

  it('resolves to "authenticated" with a valid, unexpired stored user', async () => {
    configureOidcProvider();
    fakeManager.getUser.mockResolvedValue({ access_token: 'tok-1', expired: false });

    const { result } = renderHook(() => useOidcSession());

    await waitFor(() => expect(result.current.status).toBe('authenticated'));
    expect(result.current.getAccessTokenLive()).toBe('tok-1');
  });

  it('treats an expired stored user as "unauthenticated", never as a valid session', async () => {
    configureOidcProvider();
    fakeManager.getUser.mockResolvedValue({ access_token: 'tok-1', expired: true });

    const { result } = renderHook(() => useOidcSession());

    await waitFor(() => expect(result.current.status).toBe('unauthenticated'));
    expect(result.current.getAccessTokenLive()).toBeNull();
  });

  it('resolves to "error" when getUser() itself rejects', async () => {
    configureOidcProvider();
    fakeManager.getUser.mockRejectedValue(new Error('storage unavailable'));

    const { result } = renderHook(() => useOidcSession());

    await waitFor(() => expect(result.current.status).toBe('error'));
    expect(result.current.error?.message).toBe('storage unavailable');
  });

  it('reacts live to a userLoaded event (e.g. after a successful callback)', async () => {
    configureOidcProvider();
    fakeManager.getUser.mockResolvedValue(null);

    const { result } = renderHook(() => useOidcSession());
    await waitFor(() => expect(result.current.status).toBe('unauthenticated'));

    fakeManager.emitUserLoaded({ access_token: 'tok-2', expired: false });

    await waitFor(() => expect(result.current.status).toBe('authenticated'));
    expect(result.current.getAccessTokenLive()).toBe('tok-2');
  });

  it('signIn() calls UserManager.signinRedirect()', async () => {
    configureOidcProvider();
    fakeManager.getUser.mockResolvedValue(null);

    const { result } = renderHook(() => useOidcSession());
    await waitFor(() => expect(result.current.status).toBe('unauthenticated'));

    await result.current.signIn();

    expect(fakeManager.signinRedirect).toHaveBeenCalledTimes(1);
  });

  it('signOutLocally() calls UserManager.removeUser() and the session becomes unauthenticated (local reset, no IdP redirect)', async () => {
    configureOidcProvider();
    fakeManager.getUser.mockResolvedValue({ access_token: 'tok-1', expired: false });
    fakeManager.removeUser.mockImplementation(async () => {
      fakeManager.emitUserUnloaded();
    });

    const { result } = renderHook(() => useOidcSession());
    await waitFor(() => expect(result.current.status).toBe('authenticated'));

    await result.current.signOutLocally();

    expect(fakeManager.removeUser).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(result.current.status).toBe('unauthenticated'));
    expect(result.current.getAccessTokenLive()).toBeNull();
  });

  it('omits extraQueryParams entirely when no VITE_OIDC_AUDIENCE is configured', async () => {
    configureOidcProvider();
    fakeManager.getUser.mockResolvedValue(null);

    renderHook(() => useOidcSession());
    await waitFor(() => expect(lastUserManagerSettings).toBeDefined());

    expect(lastUserManagerSettings?.extraQueryParams).toBeUndefined();
  });

  it('forwards VITE_OIDC_AUDIENCE as the authorize request\'s audience param', async () => {
    configureOidcProvider();
    vi.stubEnv('VITE_OIDC_AUDIENCE', 'https://sie-api');
    fakeManager.getUser.mockResolvedValue(null);

    renderHook(() => useOidcSession());
    await waitFor(() => expect(lastUserManagerSettings).toBeDefined());

    expect(lastUserManagerSettings?.extraQueryParams).toEqual({ audience: 'https://sie-api' });
  });
});
