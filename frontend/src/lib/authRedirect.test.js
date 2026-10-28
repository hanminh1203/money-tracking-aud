import assert from 'node:assert/strict';
import { test } from 'node:test';
import { loginUrl } from './api.js';
import {
  AUTH_REDIRECT_LOCK_MS,
  handleUnauthorizedResponse,
  isSafeReturnPath,
  loginLocation,
  resetAuthRedirectForTests,
  setUnauthorizedHandler,
  tokenExpired,
} from './authRedirect.js';

test('isSafeReturnPath allows in-app paths and rejects open redirects', () => {
  assert.equal(isSafeReturnPath('/transactions?q=rent'), true);
  assert.equal(isSafeReturnPath('/products/abc'), true);
  assert.equal(isSafeReturnPath('/'), true);
  assert.equal(isSafeReturnPath('/login'), false);
  assert.equal(isSafeReturnPath('/login?next=/transactions'), false);
  assert.equal(isSafeReturnPath('/api/dashboard'), false);
  assert.equal(isSafeReturnPath('//evil.example/phish'), false);
  assert.equal(isSafeReturnPath('https://evil.example'), false);
  assert.equal(isSafeReturnPath('/%2F%2Fevil.example'), false);
  assert.equal(isSafeReturnPath('/transactions/../login'), false);
  assert.equal(isSafeReturnPath('/\\evil.example'), false);
  assert.equal(isSafeReturnPath(''), false);
  assert.equal(isSafeReturnPath(null), false);
});

test('loginLocation encodes a safe return path and skips the home page', () => {
  assert.equal(loginLocation('/'), '/login');
  assert.equal(loginLocation('/login'), '/login');
  assert.equal(loginLocation('https://evil.example'), '/login');
  assert.equal(
    loginLocation('/transactions?page=2'),
    `/login?next=${encodeURIComponent('/transactions?page=2')}`,
  );
});

test('loginUrl only appends a safe next path', () => {
  assert.equal(
    loginUrl('/transactions?q=rent'),
    `/api/auth/google/login?next=${encodeURIComponent('/transactions?q=rent')}`,
  );
  assert.equal(loginUrl('https://evil.example'), '/api/auth/google/login');
  assert.equal(loginUrl('//evil.example'), '/api/auth/google/login');
  assert.equal(loginUrl('/login'), '/api/auth/google/login');
  assert.equal(loginUrl(undefined), '/api/auth/google/login');
});

test('tokenExpired follows the server expiry timestamp', () => {
  const now = Date.parse('2026-10-28T00:00:00Z');
  assert.equal(tokenExpired(null, now), false);
  assert.equal(tokenExpired(undefined, now), false);
  assert.equal(tokenExpired(now / 1000 + 60, now), false);
  assert.equal(tokenExpired(now / 1000 - 1, now), true);
  assert.equal(tokenExpired(now / 1000, now), true);
});

test('concurrent 401s schedule a single login redirect', () => {
  resetAuthRedirectForTests();
  const seen = [];
  setUnauthorizedHandler((detail) => seen.push(detail));
  const now = 1_000_000;

  const first = handleUnauthorizedResponse({
    status: 401,
    code: 'unauthenticated',
    apiPath: '/dashboard',
    pathname: '/transactions',
    search: '?page=2',
    now,
  });
  const second = handleUnauthorizedResponse({
    status: 401,
    code: 'unauthenticated',
    apiPath: '/metadata',
    pathname: '/transactions',
    search: '?page=2',
    now: now + 50,
  });
  const later = handleUnauthorizedResponse({
    status: 401,
    code: 'unauthenticated',
    apiPath: '/dashboard',
    pathname: '/sources',
    search: '',
    now: now + AUTH_REDIRECT_LOCK_MS,
  });

  assert.equal(first.redirect, true);
  assert.equal(first.returnTo, '/transactions?page=2');
  assert.equal(second.redirect, false);
  assert.equal(second.duplicate, true);
  assert.equal(later.redirect, true);
  assert.equal(seen.filter((detail) => detail.redirect).length, 2);
  assert.equal(seen.length, 3);
});

test('login page and auth flow endpoints do not redirect', () => {
  resetAuthRedirectForTests();
  const seen = [];
  setUnauthorizedHandler((detail) => seen.push(detail));
  const now = 2_000_000;

  const onLogin = handleUnauthorizedResponse({
    status: 401,
    code: 'unauthenticated',
    apiPath: '/auth/me',
    pathname: '/login',
    search: '?next=%2Fsources',
    now,
  });
  const callback = handleUnauthorizedResponse({
    status: 401,
    code: 'unauthenticated',
    apiPath: '/auth/google/callback?code=1',
    pathname: '/transactions',
    search: '',
    now,
  });
  const logout = handleUnauthorizedResponse({
    status: 401,
    code: 'unauthenticated',
    apiPath: '/auth/logout',
    pathname: '/transactions',
    search: '',
    now,
  });
  const after = handleUnauthorizedResponse({
    status: 401,
    code: 'unauthenticated',
    apiPath: '/dashboard',
    pathname: '/transactions',
    search: '',
    now,
  });

  assert.equal(onLogin.redirect, false);
  assert.equal(callback.redirect, false);
  assert.equal(logout.redirect, false);
  assert.equal(after.redirect, true);
  assert.equal(seen.filter((detail) => detail.redirect).length, 1);
});

test('other HTTP failures are not treated as an expired session', () => {
  resetAuthRedirectForTests();
  let calls = 0;
  setUnauthorizedHandler(() => {
    calls += 1;
  });
  const now = 3_000_000;

  const forbidden = handleUnauthorizedResponse({
    status: 403,
    code: 'unauthenticated',
    apiPath: '/dashboard',
    pathname: '/transactions',
    search: '',
    now,
  });
  const sheet = handleUnauthorizedResponse({
    status: 401,
    apiPath: '/management/status',
    pathname: '/management',
    search: '',
    now,
  });
  const anonymous = handleUnauthorizedResponse({
    status: 200,
    apiPath: '/auth/me',
    pathname: '/',
    search: '',
    now,
  });

  assert.equal(forbidden.redirect, false);
  assert.equal(sheet.redirect, false);
  assert.equal(anonymous.redirect, false);
  assert.equal(calls, 0);
});
