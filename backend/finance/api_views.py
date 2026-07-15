"""Auth and finance API views."""

from __future__ import annotations

import json
import secrets
import time
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
    get_metadata as db_get_metadata,
    get_receipt as db_get_receipt,
    get_transaction_data,
)
from .db_sync import SyncError, compare_mirror, sync_from_sheets
from .groq_client import GroqError, extract_receipt_from_image, parse_finance_message
from .sheets_client import SheetsClient, SheetsError


def json_error(message: str, status: int = 400) -> JsonResponse:
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
        except oauth.AuthError as exc:
            return json_error(str(exc), status=exc.status)
        request.google_access_token = token  # type: ignore[attr-defined]
        return view(request, *args, **kwargs)

    return wrapper


def sheets_for(request: HttpRequest) -> SheetsClient:
    return SheetsClient(request.google_access_token)  # type: ignore[attr-defined]


@ensure_csrf_cookie
@require_GET
def auth_me(request: HttpRequest) -> JsonResponse:
    # Touch CSRF cookie for the SPA
    get_token(request)
    authenticated = oauth.is_authenticated(request)
    return JsonResponse(
        {
            'authenticated': authenticated,
            'email': request.session.get(oauth.SESSION_EMAIL) if authenticated else None,
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
        oauth.store_tokens(request, token_data, email=email)
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
    if request.method == 'GET':
        try:
            page = _parse_positive_int(request.GET.get('page'), 'page')
            source = (request.GET.get('source') or '').strip() or None
            data = get_transaction_data(page=page, source=source)
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
def income_expense(request: HttpRequest) -> JsonResponse:
    try:
        data = sheets_for(request).get_income_expense_by_month()
    except SheetsError as exc:
        return json_error(str(exc), status=exc.status or 502)
    return JsonResponse(data, safe=False)


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
    try:
        data = db_get_receipt(receipt_id)
    except ReaderError as exc:
        return json_error(str(exc), status=exc.status)
    return JsonResponse(data)


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
    sheet_check = _check_google_sheet(sheets_for(request))
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


@require_GET
@require_auth
def management_status(request: HttpRequest) -> JsonResponse:
    try:
        result = compare_mirror(sheets_for(request))
    except SyncError as exc:
        return json_error(str(exc))
    except SheetsError as exc:
        status = getattr(exc, 'status', None) or 502
        return json_error(str(exc), status=status)
    return JsonResponse(result)


@require_POST
@require_auth
def management_sync(request: HttpRequest) -> JsonResponse:
    try:
        result = sync_from_sheets(sheets_for(request))
    except SyncError as exc:
        return json_error(str(exc))
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
