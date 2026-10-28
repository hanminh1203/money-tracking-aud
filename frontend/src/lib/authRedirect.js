/**
 * Decide when an API response means the session is dead, and collapse
 * concurrent failures into a single redirect to /login.
 *
 * The Google access token lives in an HttpOnly session cookie, so the SPA
 * cannot read it. `/api/auth/me` reports `expiresAt` after the server has
 * refreshed if needed. A 401 with `code: "unauthenticated"` is the signal
 * that refresh failed or the session is otherwise invalid.
 */

export const AUTH_REDIRECT_LOCK_MS = 1000;

const LOGIN_PATH = '/login';

let unauthorizedHandler = null;
let lastRedirectAt = 0;

export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = typeof handler === 'function' ? handler : null;
}

export function resetAuthRedirectForTests() {
  unauthorizedHandler = null;
  lastRedirectAt = 0;
}

export function isLoginPath(pathname) {
  return pathname === LOGIN_PATH || (pathname || '').startsWith(`${LOGIN_PATH}/`);
}

/** OAuth browser hops. A 401 here must not send the router back to /login. */
export function isAuthFlowApiPath(path) {
  const pathname = String(path || '').split('?')[0];
  return (
    pathname === '/auth/google/login' ||
    pathname === '/auth/google/callback' ||
    pathname === '/auth/logout'
  );
}

export function isSafeReturnPath(value) {
  if (typeof value !== 'string' || value.length === 0 || value.length > 512) return false;
  if (!value.startsWith('/') || value.startsWith('//')) return false;
  if (/[\s\\]/.test(value)) return false;
  let url;
  try {
    url = new URL(value, 'http://localhost');
  } catch {
    return false;
  }
  if (url.origin !== 'http://localhost') return false;
  let path = url.pathname;
  try {
    path = decodeURIComponent(path);
  } catch {
    return false;
  }
  if (!path.startsWith('/') || path.startsWith('//') || path.includes('\\')) return false;
  if (path === LOGIN_PATH || path.startsWith(`${LOGIN_PATH}/`)) return false;
  if (path === '/api' || path.startsWith('/api/')) return false;
  return true;
}

export function loginLocation(returnTo) {
  if (!isSafeReturnPath(returnTo) || returnTo === '/') return LOGIN_PATH;
  return `${LOGIN_PATH}?next=${encodeURIComponent(returnTo)}`;
}

export function tokenExpired(expiresAt, nowMs = Date.now()) {
  if (typeof expiresAt !== 'number' || !Number.isFinite(expiresAt)) return false;
  return nowMs / 1000 >= expiresAt;
}

export function isSessionExpiredError(err) {
  return !!err && err.status === 401 && err.code === 'unauthenticated';
}

/**
 * @returns {{ redirect: boolean, duplicate?: boolean, returnTo?: string }}
 */
export function handleUnauthorizedResponse({
  status,
  code,
  apiPath,
  pathname,
  search,
  now = Date.now(),
} = {}) {
  if (status !== 401 || code !== 'unauthenticated') return { redirect: false };
  if (isAuthFlowApiPath(apiPath)) return { redirect: false };

  const here = `${pathname || '/'}${search || ''}`;
  const returnTo = isSafeReturnPath(here) ? here : '/';
  if (isLoginPath(pathname || '')) {
    unauthorizedHandler?.({ returnTo, redirect: false });
    return { redirect: false, returnTo };
  }
  if (now - lastRedirectAt < AUTH_REDIRECT_LOCK_MS) {
    unauthorizedHandler?.({ returnTo, redirect: false });
    return { redirect: false, duplicate: true, returnTo };
  }
  lastRedirectAt = now;
  unauthorizedHandler?.({ returnTo, redirect: true });
  return { redirect: true, returnTo };
}
