"""Dual-write finance rows to Postgres after successful Sheets appends."""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction as db_transaction

from finance.models import Category, Receipt, ReceiptItem, Source, Transaction

logger = logging.getLogger(__name__)


def _parse_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value or '').strip()
    if not text:
        raise ValueError('Date is required')
    # ISO date or datetime (forms / API)
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
    # Google Sheet display format
    for fmt in ('%d/%m/%Y', '%d/%m/%y'):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f'Invalid date: {value!r}')


def _dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f'Invalid decimal: {value!r}') from exc


def _resolve_source_id(name: str) -> uuid.UUID:
    text = str(name or '').strip()
    if not text:
        raise ValueError('Source is required')
    try:
        return Source.objects.values_list('id', flat=True).get(name=text)
    except Source.DoesNotExist as exc:
        raise ValueError(f'Source {text!r} not found') from exc


def _resolve_category_id(sub_category: str) -> uuid.UUID | None:
    text = str(sub_category or '').strip()
    if not text:
        return None
    try:
        return Category.objects.values_list('id', flat=True).get(sub_category=text)
    except Category.DoesNotExist as exc:
        raise ValueError(f'Sub category {text!r} not found') from exc


def save_transactions(rows: list[dict]) -> None:
    """
    Insert Transaction rows.

    Each row dict: date, change, source, row_number, comment?, sub_category?, receipt_id?
    source / sub_category are sheet names resolved to Source / Category FKs.
    row_number is the 1-based Google Sheets row for the Transactions table.
    """
    if not rows:
        return
    try:
        objs = []
        for row in rows:
            receipt_id = row.get('receipt_id')
            objs.append(
                Transaction(
                    id=uuid.uuid4(),
                    version=1,
                    row_number=int(row['row_number']),
                    date=_parse_date(row['date']),
                    change=_dec(row['change']),
                    source_id=_resolve_source_id(row.get('source') or ''),
                    comment=str(row.get('comment') or ''),
                    category_id=_resolve_category_id(row.get('sub_category') or ''),
                    receipt_id=uuid.UUID(str(receipt_id)) if receipt_id else None,
                )
            )
        Transaction.objects.bulk_create(objs)
    except Exception:
        logger.exception('Postgres dual-write failed for transaction(s)')


def save_transaction(
    *,
    date: Any,
    change: Any,
    source: str,
    row_number: int,
    comment: str = '',
    sub_category: str = '',
    receipt_id: Any = None,
) -> None:
    save_transactions(
        [
            {
                'date': date,
                'change': change,
                'source': source,
                'row_number': row_number,
                'comment': comment,
                'sub_category': sub_category,
                'receipt_id': receipt_id,
            }
        ]
    )


def save_receipt_bundle(
    *,
    receipt_id: Any,
    date: Any,
    total: Any,
    items: list[dict],
    transactions: list[dict],
) -> None:
    """
    Insert Receipt + ReceiptItems + linked Transactions in one DB transaction.

    receipt_id must equal the sheet Receipt ID (becomes Receipt.id).
    items: name, amount, unit, money
    transactions: date, change, source, row_number, comment?, sub_category?
    """
    try:
        rid = uuid.UUID(str(receipt_id))
        with db_transaction.atomic():
            Receipt.objects.create(
                id=rid,
                version=1,
                date=_parse_date(date),
                total=_dec(total),
            )
            ReceiptItem.objects.bulk_create(
                [
                    ReceiptItem(
                        id=uuid.uuid4(),
                        version=1,
                        receipt_id=rid,
                        name=str(it['name']),
                        amount=_dec(it['amount']),
                        unit=str(it['unit']),
                        money=_dec(it['money']),
                    )
                    for it in items
                ]
            )
            Transaction.objects.bulk_create(
                [
                    Transaction(
                        id=uuid.uuid4(),
                        version=1,
                        row_number=int(tx['row_number']),
                        date=_parse_date(tx.get('date', date)),
                        change=_dec(tx['change']),
                        source_id=_resolve_source_id(tx.get('source') or ''),
                        comment=str(tx.get('comment') or ''),
                        category_id=_resolve_category_id(tx.get('sub_category') or ''),
                        receipt_id=rid,
                    )
                    for tx in transactions
                ]
            )
    except Exception:
        logger.exception('Postgres dual-write failed for receipt bundle %s', receipt_id)
