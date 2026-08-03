"""Auth and finance API views."""

from __future__ import annotations

import json
import secrets
import sys
import time
import traceback
from datetime import datetime, timezone
from functools import wraps
from typing import Callable
from urllib.parse import urlencode

from django.conf import settings
from django.db import connection, OperationalError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import oauth
from .db_reader import (
    ReaderError,
    get_dashboard_data,
    get_export_payload,
    get_giftcards as db_get_giftcards,
    get_metadata as db_get_metadata,
    get_receipt as db_get_receipt,
    get_transaction_data,
)
from .db_sync import SyncError, compare_mirror, sync_from_sheets
from .groq_client import GroqError, extract_receipt_from_image, parse_finance_message
from .models import User
from .sheets_client import SheetsClient, SheetsError


def json_error(message: str, status: int = 400) -> JsonResponse:
    # Print stack when called from an except block (most API error paths).
    if sys.exc_info()[0] is not None:
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
    return JsonResponse({'error': message}, status=status)


def parse_json(request: HttpRequest) -> dict:
    if not request.body:
        return {}
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError as exc:
        raise ValueError('Invalid JSON body') from exc
    if not isinstance(data, dict):
        raise ValueError('JSON body must be an object')
    return data


def require_auth(view: Callable):
    @wraps(view)
    def wrapper(request: HttpRequest, *args, **kwargs):
        try:
            token = oauth.get_access_token(request)
            user = oauth.get_finance_user(request)
        except oauth.AuthError as exc:
            return json_error(str(exc), status=exc.status)
        request.google_access_token = token  # type: ignore[attr-defined]
        request.finance_user = user  # type: ignore[attr-defined]
        return view(request, *args, **kwargs)

    return wrapper


def sheets_for(request: HttpRequest) -> SheetsClient:
    user: User = request.finance_user  # type: ignore[attr-defined]
    return SheetsClient(
        request.google_access_token,  # type: ignore[attr-defined]
        user.sheet_id,
        user=user,
    )


@ensure_csrf_cookie
@require_GET
def auth_me(request: HttpRequest) -> JsonResponse:
    # Touch CSRF cookie for the SPA
    get_token(request)
    authenticated = oauth.is_authenticated(request)
    email = None
    sheet_id = None
    if authenticated:
        email = request.session.get(oauth.SESSION_EMAIL)
        try:
            user = oauth.get_finance_user(request)
            sheet_id = user.sheet_id or None
        except oauth.AuthError:
            pass
    return JsonResponse(
        {
            'authenticated': authenticated,
            'email': email,
            'sheetId': sheet_id,
        }
    )


@require_GET
def google_login(request: HttpRequest) -> HttpResponse:
    try:
        state = secrets.token_urlsafe(24)
        request.session['oauth_state'] = state
        request.session.modified = True
        url = oauth.build_login_url(state)
    except oauth.AuthError as exc:
        return json_error(str(exc), status=exc.status)
    return HttpResponse(status=302, headers={'Location': url})


@require_GET
def google_callback(request: HttpRequest) -> HttpResponse:
    error = request.GET.get('error')
    if error:
        qs = urlencode({'auth_error': error})
        return HttpResponse(
            status=302,
            headers={'Location': f'{settings.FRONTEND_URL}/?{qs}'},
        )

    state = request.GET.get('state')
    expected = request.session.pop('oauth_state', None)
    if not state or not expected or state != expected:
        qs = urlencode({'auth_error': 'invalid_state'})
        return HttpResponse(
            status=302,
            headers={'Location': f'{settings.FRONTEND_URL}/?{qs}'},
        )

    code = request.GET.get('code')
    if not code:
        qs = urlencode({'auth_error': 'missing_code'})
        return HttpResponse(
            status=302,
            headers={'Location': f'{settings.FRONTEND_URL}/?{qs}'},
        )

    try:
        token_data = oauth.exchange_code(code)
        email = oauth.fetch_email(token_data['access_token'])
        if not email:
            raise oauth.AuthError('Could not read Google account email', status=400)
        user, _ = User.objects.get_or_create(email=email)
        oauth.store_tokens(request, token_data, email=email)
        oauth.store_finance_user(request, str(user.id))
    except oauth.AuthError as exc:
        qs = urlencode({'auth_error': str(exc)})
        return HttpResponse(
            status=302,
            headers={'Location': f'{settings.FRONTEND_URL}/?{qs}'},
        )

    return HttpResponse(status=302, headers={'Location': f'{settings.FRONTEND_URL}/'})


@require_POST
def logout(request: HttpRequest) -> JsonResponse:
    oauth.clear_tokens(request)
    return JsonResponse({'ok': True})


def _parse_positive_int(value: str | None, name: str) -> int | None:
    if value is None or value == '':
        return None
    try:
        n = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{name} must be an integer') from exc
    if n < 1:
        raise ValueError(f'{name} must be >= 1')
    return n


@require_http_methods(['GET', 'POST'])
@require_auth
def transactions(request: HttpRequest) -> JsonResponse:
    user: User = request.finance_user  # type: ignore[attr-defined]
    if request.method == 'GET':
        try:
            page = _parse_positive_int(request.GET.get('page'), 'page')
            source = (request.GET.get('source') or '').strip() or None
            data = get_transaction_data(user=user, page=page, source=source)
        except ValueError as exc:
            return json_error(str(exc))
        return JsonResponse(data)

    try:
        body = parse_json(request)
        result = sheets_for(request).add_transaction(
            date=body.get('date'),
            amount=body.get('amount'),
            type=body.get('type'),
            source=body.get('source'),
            sub_category=body.get('subCategory') or '',
            comment=body.get('comment') or '',
        )
    except ValueError as exc:
        return json_error(str(exc))
    except SheetsError as exc:
        return json_error(str(exc), status=exc.status or 400)
    return JsonResponse(result)


@require_GET
@require_auth
def metadata(request: HttpRequest) -> JsonResponse:
    return JsonResponse(db_get_metadata())


@require_GET
@require_auth
def dashboard(request: HttpRequest) -> JsonResponse:
    user: User = request.finance_user  # type: ignore[attr-defined]
    return JsonResponse(get_dashboard_data(user=user))


@require_http_methods(['POST'])
@require_auth
def create_transfer(request: HttpRequest) -> JsonResponse:
    try:
        body = parse_json(request)
        result = sheets_for(request).add_transfer(
            date=body.get('date'),
            amount=body.get('amount'),
            from_source=body.get('fromSource'),
            to_source=body.get('toSource'),
            comment=body.get('comment') or '',
        )
    except ValueError as exc:
        return json_error(str(exc))
    except SheetsError as exc:
        return json_error(str(exc), status=exc.status or 400)
    return JsonResponse(result)


@require_http_methods(['POST'])
@require_auth
def create_receipt(request: HttpRequest) -> JsonResponse:
    try:
        body = parse_json(request)
        result = sheets_for(request).add_receipt(
            date=body.get('date'),
            store=body.get('store'),
            sub_category=body.get('subCategory'),
            comment=body.get('comment') or '',
            sources=body.get('sources') or [],
            items=body.get('items') or [],
        )
    except ValueError as exc:
        return json_error(str(exc))
    except SheetsError as exc:
        return json_error(str(exc), status=exc.status or 400)
    return JsonResponse(result)


@require_GET
@require_auth
def get_receipt(request: HttpRequest, receipt_id: str) -> JsonResponse:
    user: User = request.finance_user  # type: ignore[attr-defined]
    try:
        data = db_get_receipt(user=user, receipt_id=receipt_id)
    except ReaderError as exc:
        return json_error(str(exc), status=exc.status)
    return JsonResponse(data)


@require_GET
@require_auth
def giftcards(request: HttpRequest) -> JsonResponse:
    user: User = request.finance_user  # type: ignore[attr-defined]
    return JsonResponse(db_get_giftcards(user=user), safe=False)


@require_http_methods(['POST'])
@require_auth
def buy_giftcard(request: HttpRequest) -> JsonResponse:
    try:
        body = parse_json(request)
        result = sheets_for(request).buy_giftcard(
            shop=body.get('shop'),
            date=body.get('date'),
            balance=body.get('balance'),
            source=body.get('source'),
        )
    except ValueError as exc:
        return json_error(str(exc))
    except SheetsError as exc:
        return json_error(str(exc), status=exc.status or 400)
    return JsonResponse(result)


@require_http_methods(['POST'])
@require_auth
def use_giftcard(request: HttpRequest, giftcard_id: str) -> JsonResponse:
    try:
        body = parse_json(request)
        result = sheets_for(request).use_giftcard(
            giftcard_id=giftcard_id,
            amount=body.get('amount'),
            comment=body.get('comment') or '',
            sub_category=body.get('subCategory') or '',
        )
    except ValueError as exc:
        return json_error(str(exc))
    except SheetsError as exc:
        return json_error(str(exc), status=exc.status or 400)
    return JsonResponse(result)


@require_http_methods(['POST'])
@require_auth
def assistant_parse(request: HttpRequest) -> JsonResponse:
    try:
        body = parse_json(request)
        message = (body.get('message') or '').strip()
        if not message:
            return json_error('message is required')
        metadata = body.get('metadata')
        if not metadata:
            metadata = db_get_metadata()
        result = parse_finance_message(message, metadata)
    except ValueError as exc:
        return json_error(str(exc))
    except GroqError as exc:
        return json_error(str(exc), status=502)
    return JsonResponse(result)


def _check_database() -> dict:
    start = time.monotonic()
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except OperationalError as exc:
        return {
            'ok': False,
            'latency_ms': round((time.monotonic() - start) * 1000),
            'message': str(exc),
        }
    return {
        'ok': True,
        'latency_ms': round((time.monotonic() - start) * 1000),
        'message': 'Connected to PostgreSQL',
    }


def _check_google_sheet(client: SheetsClient) -> dict:
    start = time.monotonic()
    try:
        info = client.check_connection()
    except SheetsError as exc:
        return {
            'ok': False,
            'latency_ms': round((time.monotonic() - start) * 1000),
            'message': str(exc),
        }
    return {
        'ok': True,
        'latency_ms': round((time.monotonic() - start) * 1000),
        'message': 'Connected to Google Sheet',
        'title': info.get('title'),
        'spreadsheet_id': info.get('spreadsheet_id'),
    }


@require_GET
@require_auth
def health(request: HttpRequest) -> JsonResponse:
    db_check = _check_database()
    user: User = request.finance_user  # type: ignore[attr-defined]
    if not (user.sheet_id or '').strip():
        sheet_check = {
            'ok': False,
            'latency_ms': 0,
            'message': 'Sheet ID is not configured for this user',
        }
    else:
        try:
            sheet_check = _check_google_sheet(sheets_for(request))
        except SheetsError as exc:
            sheet_check = {
                'ok': False,
                'latency_ms': 0,
                'message': str(exc),
            }
    all_ok = db_check['ok'] and sheet_check['ok']
    return JsonResponse(
        {
            'status': 'ok' if all_ok else 'degraded',
            'checks': {
                'database': db_check,
                'google_sheet': sheet_check,
            },
            'checked_at': datetime.now(timezone.utc).isoformat(),
        },
        status=200 if all_ok else 503,
    )


@require_http_methods(['GET', 'PUT'])
@require_auth
def management_settings(request: HttpRequest) -> JsonResponse:
    user: User = request.finance_user  # type: ignore[attr-defined]
    if request.method == 'GET':
        return JsonResponse({'sheetId': user.sheet_id or None})

    try:
        body = parse_json(request)
        sheet_id = str(body.get('sheetId') or '').strip()
        if not sheet_id:
            return json_error('sheetId is required')
        user.sheet_id = sheet_id
        user.save(update_fields=['sheet_id'])
    except ValueError as exc:
        return json_error(str(exc))
    return JsonResponse({'sheetId': user.sheet_id})


@require_GET
@require_auth
def management_status(request: HttpRequest) -> JsonResponse:
    user: User = request.finance_user  # type: ignore[attr-defined]
    try:
        result = compare_mirror(sheets_for(request), user=user)
    except SyncError as exc:
        return json_error(str(exc))
    except SheetsError as exc:
        status = getattr(exc, 'status', None) or 502
        return json_error(str(exc), status=status)
    return JsonResponse(result)


@require_POST
@require_auth
def management_sync(request: HttpRequest) -> JsonResponse:
    user: User = request.finance_user  # type: ignore[attr-defined]
    try:
        result = sync_from_sheets(sheets_for(request), user=user)
    except SyncError as exc:
        return json_error(str(exc))
    except SheetsError as exc:
        status = getattr(exc, 'status', None) or 502
        return json_error(str(exc), status=status)
    return JsonResponse(result)


@require_POST
@require_auth
def management_export(request: HttpRequest) -> JsonResponse:
    """Create a new Google Sheet from this user's Postgres mirror tables."""
    user: User = request.finance_user  # type: ignore[attr-defined]
    try:
        payload = get_export_payload(user=user)
        title = f"Finance Export {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC"
        result = sheets_for(request).export_workbook(title, payload)
    except SheetsError as exc:
        status = getattr(exc, 'status', None) or 502
        return json_error(str(exc), status=status)
    return JsonResponse(result)


@require_http_methods(['POST'])
@require_auth
def receipt_ocr(request: HttpRequest) -> JsonResponse:
    try:
        body = parse_json(request)
        image = body.get('imageDataUrl') or ''
        if not image:
            return json_error('imageDataUrl is required')
        metadata = body.get('metadata')
        if not metadata:
            metadata = db_get_metadata()
        result = extract_receipt_from_image(image, metadata)
    except ValueError as exc:
        return json_error(str(exc))
    except GroqError as exc:
        return json_error(str(exc), status=502)
    return JsonResponse(result)
