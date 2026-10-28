import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { loginLocation, setUnauthorizedHandler, tokenExpired } from '../lib/authRedirect';
import { fetchMe, loginUrl, logout as apiLogout } from '../lib/api';

const SESSION_EXPIRED = 'Your session has expired. Sign in again.';

/**
 * Session-based auth against the Django backend (Google OAuth code flow).
 * A 401 `unauthenticated` response, or an access-token expiry that the server
 * cannot refresh, clears local auth state and sends the user to /login.
 */
export function useAuth() {
  const navigate = useNavigate();
  const location = useLocation();
  const [signedIn, setSignedIn] = useState(false);
  const [email, setEmail] = useState(null);
  const [expiresAt, setExpiresAt] = useState(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState(null);
  const expiryCheckAt = useRef(0);

  const refresh = useCallback(async () => {
    try {
      const me = await fetchMe();
      if (!me.authenticated) {
        setSignedIn(false);
        setEmail(null);
        setExpiresAt(null);
        return;
      }
      setSignedIn(true);
      setEmail(me.email || null);
      setExpiresAt(typeof me.expiresAt === 'number' ? me.expiresAt : null);
      setError(null);
    } catch (err) {
      setSignedIn(false);
      setEmail(null);
      setExpiresAt(null);
      if (err.status === 401 && err.code === 'unauthenticated') {
        setError(SESSION_EXPIRED);
      } else {
        setError(err.message || String(err));
      }
    } finally {
      setReady(true);
    }
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(({ returnTo, redirect }) => {
      setSignedIn(false);
      setEmail(null);
      setExpiresAt(null);
      setError(SESSION_EXPIRED);
      if (redirect) {
        navigate(loginLocation(returnTo), { replace: true });
      }
    });
    return () => setUnauthorizedHandler(null);
  }, [navigate]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const authError = params.get('auth_error');
    if (authError) {
      setError(authError);
      params.delete('auth_error');
      const qs = params.toString();
      window.history.replaceState({}, '', `${window.location.pathname}${qs ? `?${qs}` : ''}`);
    }
    refresh();
  }, [refresh]);

  // Re-check when the reported access-token expiry has passed (app load sets
  // expiresAt; route changes re-run this). The server refreshes if it can;
  // a failed refresh comes back as 401 and the handler above goes to /login.
  useEffect(() => {
    if (!signedIn || !tokenExpired(expiresAt)) return;
    const now = Date.now();
    if (now - expiryCheckAt.current < 5000) return;
    expiryCheckAt.current = now;
    refresh();
  }, [location.pathname, location.search, signedIn, expiresAt, refresh]);

  const signIn = useCallback(() => {
    const next = new URLSearchParams(window.location.search).get('next');
    window.location.href = loginUrl(next);
  }, []);

  const signOut = useCallback(async () => {
    try {
      await apiLogout();
    } catch {
      // clear local state even if revoke fails
    }
    setSignedIn(false);
    setEmail(null);
    setExpiresAt(null);
    setError(null);
  }, []);

  return { signedIn, email, expiresAt, ready, error, signIn, signOut, refresh };
}
