"""Google OAuth helpers and session token management."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.http import HttpRequest

GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL = 'https://www.googleapis.com/oauth2/v3/userinfo'
GOOGLE_REVOKE_URL = 'https://oauth2.googleapis.com/revoke'

SESSION_ACCESS = 'google_access_token'
SESSION_REFRESH = 'google_refresh_token'
SESSION_EXPIRES = 'google_token_expires_at'
SESSION_EMAIL = 'google_email'
SESSION_USER_ID = 'finance_user_id'


class AuthError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def build_login_url(state: str) -> str:
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_REDIRECT_URI:
        raise AuthError('Google OAuth is not configured', status=500)
    params = {
        'client_id': settings.GOOGLE_CLIENT_ID,
        'redirect_uri': settings.GOOGLE_REDIRECT_URI,
        'response_type': 'code',
        'scope': ' '.join(settings.GOOGLE_SCOPES),
        'access_type': 'offline',
        'prompt': 'consent',
        'include_granted_scopes': 'true',
        'state': state,
    }
    return f'{GOOGLE_AUTH_URL}?{urlencode(params)}'


def exchange_code(code: str) -> dict[str, Any]:
    res = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            'code': code,
            'client_id': settings.GOOGLE_CLIENT_ID,
            'client_secret': settings.GOOGLE_CLIENT_SECRET,
            'redirect_uri': settings.GOOGLE_REDIRECT_URI,
            'grant_type': 'authorization_code',
        },
        timeout=30,
    )
    if not res.ok:
        try:
            msg = res.json().get('error_description') or res.json().get('error') or res.text
        except Exception:
            msg = res.text
        raise AuthError(f'Token exchange failed: {msg}', status=400)
    return res.json()


def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    res = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            'client_id': settings.GOOGLE_CLIENT_ID,
            'client_secret': settings.GOOGLE_CLIENT_SECRET,
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token',
        },
        timeout=30,
    )
    if not res.ok:
        try:
            msg = res.json().get('error_description') or res.json().get('error') or res.text
        except Exception:
            msg = res.text
        raise AuthError(f'Token refresh failed: {msg}', status=401)
    return res.json()


def fetch_email(access_token: str) -> str | None:
    res = requests.get(
        GOOGLE_USERINFO_URL,
        headers={'Authorization': f'Bearer {access_token}'},
        timeout=15,
    )
    if not res.ok:
        return None
    return res.json().get('email')


def store_tokens(request: HttpRequest, token_data: dict[str, Any], email: str | None = None) -> None:
    access = token_data.get('access_token')
    if not access:
        raise AuthError('No access_token in Google response', status=500)
    expires_in = int(token_data.get('expires_in') or 3600)
    request.session[SESSION_ACCESS] = access
    request.session[SESSION_EXPIRES] = int(time.time()) + expires_in - 60
    if token_data.get('refresh_token'):
        request.session[SESSION_REFRESH] = token_data['refresh_token']
    if email:
        request.session[SESSION_EMAIL] = email
    request.session.modified = True


def store_finance_user(request: HttpRequest, user_id: str) -> None:
    request.session[SESSION_USER_ID] = str(user_id)
    request.session.modified = True


def clear_tokens(request: HttpRequest) -> None:
    access = request.session.get(SESSION_ACCESS)
    if access:
        try:
            requests.post(GOOGLE_REVOKE_URL, params={'token': access}, timeout=10)
        except Exception:
            pass
    for key in (
        SESSION_ACCESS,
        SESSION_REFRESH,
        SESSION_EXPIRES,
        SESSION_EMAIL,
        SESSION_USER_ID,
    ):
        request.session.pop(key, None)
    request.session.modified = True


def is_authenticated(request: HttpRequest) -> bool:
    return bool(request.session.get(SESSION_ACCESS) or request.session.get(SESSION_REFRESH))


def get_access_token(request: HttpRequest) -> str:
    access = request.session.get(SESSION_ACCESS)
    expires_at = int(request.session.get(SESSION_EXPIRES) or 0)
    now = int(time.time())

    if access and expires_at > now:
        return access

    refresh = request.session.get(SESSION_REFRESH)
    if not refresh:
        raise AuthError('Not authenticated', status=401)

    data = refresh_access_token(refresh)
    store_tokens(request, data)
    return request.session[SESSION_ACCESS]


def get_finance_user(request: HttpRequest):
    """Return the finance.User for this session, creating from email if needed."""
    from finance.models import User

    uid = request.session.get(SESSION_USER_ID)
    if uid:
        try:
            return User.objects.get(pk=uid)
        except (User.DoesNotExist, ValueError, TypeError):
            pass

    email = (request.session.get(SESSION_EMAIL) or '').strip()
    if not email:
        raise AuthError('Not authenticated', status=401)

    user, _ = User.objects.get_or_create(email=email)
    store_finance_user(request, str(user.id))
    return user
