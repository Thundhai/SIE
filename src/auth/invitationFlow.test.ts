import { afterEach, describe, expect, it } from 'vitest';
import {
  clearPendingInvitation,
  hashHasToken,
  readPendingInvitation,
  readTokenFromHash,
  safeReturnPath,
  storePendingInvitation,
} from './invitationFlow';

describe('invitationFlow', () => {
  afterEach(() => window.sessionStorage.clear());

  it('reads the code from the URL fragment only when it is plausibly a code', () => {
    expect(readTokenFromHash('#token=sie_link_abcdefghij')).toBe('sie_link_abcdefghij');
    expect(readTokenFromHash('token=sie_link_abcdefghij')).toBe('sie_link_abcdefghij');
    expect(readTokenFromHash('#token=short')).toBeNull();
    expect(readTokenFromHash('#other=sie_link_abcdefghij')).toBeNull();
    expect(readTokenFromHash('')).toBeNull();
  });

  it('keeps the pending code in sessionStorage until cleared', () => {
    storePendingInvitation('sie_link_abcdefghij');
    expect(readPendingInvitation()).toBe('sie_link_abcdefghij');
    clearPendingInvitation();
    expect(readPendingInvitation()).toBeNull();
  });

  it.each([
    ['/invite/complete', '/invite/complete'],
    ['/', '/'],
    ['//evil.example.com', null],
    ['https://evil.example.com', null],
    ['/\\evil.example.com', null],
    ['/x?next=https://evil.example.com', null],
    ['invite', null],
    [42, null],
    [undefined, null],
  ])('safeReturnPath(%s) -> %s', (input, expected) => {
    expect(safeReturnPath(input)).toBe(expected);
  });
});


describe('hashHasToken', () => {
  it('is true whenever the fragment names a token, valid or not', () => {
    expect(hashHasToken('#token=short')).toBe(true);
    expect(hashHasToken('#token=')).toBe(true);
    expect(hashHasToken('#token=sie_link_abcdefghijk')).toBe(true);
    expect(hashHasToken('')).toBe(false);
    expect(hashHasToken('#other=1')).toBe(false);
  });
});
