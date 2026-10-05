import { afterEach, describe, expect, it, vi } from 'vitest';
import { notifySessionInvalidated, registerSessionInvalidationHandler } from './sessionInvalidation';

describe('sessionInvalidation', () => {
  afterEach(() => {
    registerSessionInvalidationHandler(null);
  });

  it('calls the registered handler when notified', () => {
    const handler = vi.fn();
    registerSessionInvalidationHandler(handler);

    notifySessionInvalidated();

    expect(handler).toHaveBeenCalledTimes(1);
  });

  it('does nothing when no handler is registered (e.g. dev mode)', () => {
    expect(() => notifySessionInvalidated()).not.toThrow();
  });

  it('a newly-registered handler replaces the previous one, never stacking both', () => {
    const first = vi.fn();
    const second = vi.fn();
    registerSessionInvalidationHandler(first);
    registerSessionInvalidationHandler(second);

    notifySessionInvalidated();

    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });

  it('registering null clears the handler', () => {
    const handler = vi.fn();
    registerSessionInvalidationHandler(handler);
    registerSessionInvalidationHandler(null);

    notifySessionInvalidated();

    expect(handler).not.toHaveBeenCalled();
  });
});
