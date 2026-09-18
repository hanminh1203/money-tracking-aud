"""Groq chat + vision helpers — port of frontend/src/lib/groqAgent.js."""

from __future__ import annotations

import json
import re
from typing import Any

import requests
from django.conf import settings
from django.utils import timezone

GROQ_API_URL = 'https://api.groq.com/openai/v1/chat/completions'
RECEIPT_UNITS = ['kg', 'g', 'ml', 'l', 'piece']


class GroqError(Exception):
    pass


def _require_key() -> str:
    key = settings.GROQ_API_KEY
    if not key:
        raise GroqError('GROQ_API_KEY is not configured on the server')
    return key


def _chat(messages: list[dict], model: str) -> dict:
    res = requests.post(
        GROQ_API_URL,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {_require_key()}',
        },
        json={
            'model': model,
            'messages': messages,
            'response_format': {'type': 'json_object'},
            'temperature': 0,
        },
        timeout=90,
    )
    if not res.ok:
        try:
            msg = res.json().get('error', {}).get('message') or f'Groq API error: {res.status_code}'
        except Exception:
            msg = f'Groq API error: {res.status_code} {res.reason}'
        raise GroqError(msg)
    data = res.json()
    content = (data.get('choices') or [{}])[0].get('message', {}).get('content')
    if not content:
        raise GroqError('No response from Groq')
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise GroqError('Groq returned a non-JSON response') from exc


def parse_finance_message(message: str, metadata: dict) -> dict:
    source_names = [s['name'] for s in metadata.get('sources') or []]
    category_list = [
        f"{c['mainCategory']} > {c['subCategory']} ({c['type']})"
        for c in metadata.get('categories') or []
    ]
    today = timezone.localdate().isoformat()

    system_prompt = f"""You are a finance assistant that extracts structured transaction data from natural language.
Return ONLY valid JSON (no markdown, no extra text) matching exactly one of these schemas:

Transaction: {{"action":"transaction","date":"YYYY-MM-DD","amount":number,"type":"Income"|"Expense","source":"<one of sources>","subCategory":"<one of sub categories>","comment":"string"}}
Transfer: {{"action":"transfer","date":"YYYY-MM-DD","amount":number,"fromSource":"<source>","toSource":"<source>","comment":"string"}}
Unknown: {{"action":"unknown","reason":"string"}}

Today's date is {today}. Use it if the message doesn't mention a date. Resolve relative dates ("yesterday", "last Monday") against today.

Available sources (use EXACTLY as written): {', '.join(source_names)}
Available categories, format "Main > Sub (Type)" (use the Sub value EXACTLY as written): {'; '.join(category_list)}

Rules:
- amount must be a positive number (never negative).
- source/fromSource/toSource must exactly match one of the available sources.
- subCategory must exactly match one of the available sub categories, and its Type must match the transaction type (Income/Expense).
- If the message is a transfer between two of the user's own sources (e.g. "move", "transfer"), use the Transfer schema.
- If required info (amount, source, or category/destination) is missing, ambiguous, or doesn't match the available lists, return the Unknown schema with a short, specific reason.
- Do not invent sources or categories that aren't in the lists."""

    return _chat(
        [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': message},
        ],
        settings.GROQ_MODEL,
    )


def normalize_unit(unit: Any) -> str:
    u = str(unit or '').strip().lower()
    if u in RECEIPT_UNITS:
        return u
    if u in ('pcs', 'pc', 'ea', 'each', 'unit', 'units', 'x'):
        return 'piece'
    if u in ('kilogram', 'kilograms', 'kgs'):
        return 'kg'
    if u in ('gram', 'grams', 'gm'):
        return 'g'
    if u in (
        'millilitre',
        'milliliter',
        'millilitres',
        'milliliters',
        'mls',
    ):
        return 'ml'
    if u in ('litre', 'liter', 'litres', 'liters'):
        return 'l'
    return 'piece'


def extract_receipt_from_image(image_data_url: str, metadata: dict) -> dict:
    if not str(image_data_url).startswith('data:image/'):
        raise GroqError('imageDataUrl must be a data:image/... URL')

    source_names = [s['name'] for s in metadata.get('sources') or []]
    expense_categories = [
        c for c in (metadata.get('categories') or []) if c.get('type') == 'Expense'
    ]
    category_list = [f"{c['mainCategory']} > {c['subCategory']}" for c in expense_categories]
    today = timezone.localdate().isoformat()

    system_prompt = f"""You extract structured receipt data from a receipt photo.
Return ONLY valid JSON matching this schema:
{{
  "store": "string",
  "date": "YYYY-MM-DD"
  "items": [{{"name": "string", "amount": 1, "money": number}}]
}}

Today's date is {today}. Use it only if the receipt date is unreadable.

Rules:
- Read every purchasable line item.
- items[].money is the line price paid (positive number).
- store: merchant name as printed.
- All money fields are positive numbers."""
    parsed = _chat(
        [
            {'role': 'system', 'content': system_prompt},
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'text',
                        'text': 'Extract the receipt fields from this image into the JSON schema.',
                    },
                    {'type': 'image_url', 'image_url': {'url': image_data_url}},
                ],
            },
        ],
        settings.GROQ_VISION_MODEL,
    )

    allowed_sources = set(source_names)
    allowed_subs = {c['subCategory'] for c in expense_categories}

    items = []
    for it in parsed.get('items') or []:
        money_raw = it.get('money')
        money = ''
        if money_raw != '' and money_raw is not None:
            try:
                money = str(abs(float(money_raw)) or '')
            except (TypeError, ValueError):
                money = ''
        amount_raw = it.get('amount')
        amount = '' if amount_raw == '' or amount_raw is None else str(amount_raw)
        name = str(it.get('name') or '').strip()
        item = {
            'name': name,
            'amount': amount,
            'unit': normalize_unit(it.get('unit')),
            'money': money,
        }
        if item['name'] or item['money']:
            items.append(item)

    sources = []
    for s in parsed.get('sources') or []:
        raw = str(s.get('source') or '').strip()
        amount_raw = s.get('amount')
        amount = ''
        if amount_raw != '' and amount_raw is not None:
            try:
                amount = str(abs(float(amount_raw)) or '')
            except (TypeError, ValueError):
                amount = ''
        entry = {
            'source': raw if raw in allowed_sources else '',
            'amount': amount,
        }
        if entry['source'] or entry['amount']:
            sources.append(entry)

    sub = str(parsed.get('subCategory') or '').strip()
    date_str = str(parsed.get('date') or '').strip()

    return {
        'store': str(parsed.get('store') or '').strip(),
        'date': date_str if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str) else today,
        'subCategory': sub if sub in allowed_subs else '',
        'comment': str(parsed.get('comment') or '').strip(),
        'sources': sources or [{'source': '', 'amount': ''}],
        'items': items or [{'name': '', 'amount': '', 'unit': 'piece', 'money': ''}],
    }
