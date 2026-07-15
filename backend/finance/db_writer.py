"""Dual-write finance rows to Postgres after successful Sheets appends."""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction as db_transaction

from finance.models import Receipt, ReceiptItem, Transaction

logger = logging.getLogger(__name__)


def _parse_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value or '').strip()
    if not text:
        raise ValueError('Date is required')
    # ISO date or datetime
    return date.fromisoformat(text[:10])


def _dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f'Invalid decimal: {value!r}') from exc


def save_transactions(rows: list[dict]) -> None:
    """
    Insert Transaction rows.

    Each row dict: date, change, source, comment?, sub_category?, receipt_id?
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
                    date=_parse_date(row['date']),
                    change=_dec(row['change']),
                    source=str(row.get('source') or ''),
                    comment=str(row.get('comment') or ''),
                    sub_category=str(row.get('sub_category') or ''),
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
    transactions: date, change, source, comment?, sub_category?
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
                        date=_parse_date(tx.get('date', date)),
                        change=_dec(tx['change']),
                        source=str(tx.get('source') or ''),
                        comment=str(tx.get('comment') or ''),
                        sub_category=str(tx.get('sub_category') or ''),
                        receipt_id=rid,
                    )
                    for tx in transactions
                ]
            )
    except Exception:
        logger.exception('Postgres dual-write failed for receipt bundle %s', receipt_id)
