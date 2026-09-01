"""Dual-write finance rows to Postgres after successful Sheets appends."""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction as db_transaction

from finance.models import Category, Giftcard, Receipt, ReceiptItem, Source, Transaction, User

logger = logging.getLogger(__name__)

GIFTCARD_SOURCE_NAME = 'Giftcard'


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


def _require_user(user: User | None) -> User:
    if user is None:
        raise ValueError('User is required')
    return user


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


def save_transactions(rows: list[dict], *, user: User) -> None:
    """
    Insert Transaction rows.

    Each row dict: date, change, source, row_number, comment?, sub_category?, receipt_id?, giftcard_id?
    source / sub_category are sheet names resolved to Source / Category FKs.
    row_number is the 1-based Google Sheets row for the Transactions table.
    """
    if not rows:
        return
    owner = _require_user(user)
    try:
        objs = []
        for row in rows:
            receipt_id = row.get('receipt_id')
            giftcard_id = row.get('giftcard_id')
            objs.append(
                Transaction(
                    id=uuid.uuid4(),
                    version=1,
                    user=owner,
                    row_number=int(row['row_number']),
                    date=_parse_date(row['date']),
                    change=_dec(row['change']),
                    source_id=_resolve_source_id(row.get('source') or ''),
                    comment=str(row.get('comment') or ''),
                    category_id=_resolve_category_id(row.get('sub_category') or ''),
                    receipt_id=uuid.UUID(str(receipt_id)) if receipt_id else None,
                    giftcard_id=uuid.UUID(str(giftcard_id)) if giftcard_id else None,
                )
            )
        Transaction.objects.bulk_create(objs)
    except Exception:
        logger.exception('Postgres dual-write failed for transaction(s)')


def save_transaction(
    *,
    user: User,
    date: Any,
    change: Any,
    source: str,
    row_number: int,
    comment: str = '',
    sub_category: str = '',
    receipt_id: Any = None,
    giftcard_id: Any = None,
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
                'giftcard_id': giftcard_id,
            }
        ],
        user=user,
    )


def save_receipt_bundle(
    *,
    user: User,
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
    owner = _require_user(user)
    try:
        rid = uuid.UUID(str(receipt_id))
        with db_transaction.atomic():
            Receipt.objects.create(
                id=rid,
                version=1,
                user=owner,
                date=_parse_date(date),
                total=_dec(total),
            )
            ReceiptItem.objects.bulk_create(
                [
                    ReceiptItem(
                        id=uuid.uuid4(),
                        version=1,
                        user=owner,
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
                        user=owner,
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


def save_giftcard_purchase(
    *,
    user: User,
    giftcard_id: Any,
    shop: str,
    date: Any,
    balance: Any,
    row_number: int,
    transactions: list[dict],
) -> None:
    """Insert Giftcard + linked buy Transactions in one DB transaction."""
    owner = _require_user(user)
    try:
        gid = uuid.UUID(str(giftcard_id))
        with db_transaction.atomic():
            Giftcard.objects.create(
                id=gid,
                version=1,
                user=owner,
                row_number=int(row_number),
                shop=str(shop),
                date=_parse_date(date),
                balance=_dec(balance),
            )
            Transaction.objects.bulk_create(
                [
                    Transaction(
                        id=uuid.uuid4(),
                        version=1,
                        user=owner,
                        row_number=int(tx['row_number']),
                        date=_parse_date(tx.get('date', date)),
                        change=_dec(tx['change']),
                        source_id=_resolve_source_id(tx.get('source') or ''),
                        comment=str(tx.get('comment') or ''),
                        category_id=_resolve_category_id(tx.get('sub_category') or ''),
                        giftcard_id=gid,
                    )
                    for tx in transactions
                ]
            )
    except Exception:
        logger.exception('Postgres dual-write failed for giftcard purchase %s', giftcard_id)


def save_giftcard_use(
    *,
    user: User,
    giftcard_id: Any,
    new_balance: Any,
    date: Any,
    change: Any,
    comment: str,
    sub_category: str,
    row_number: int,
) -> None:
    """Insert use Transaction and update Giftcard.balance in one DB transaction."""
    owner = _require_user(user)
    try:
        gid = uuid.UUID(str(giftcard_id))
        with db_transaction.atomic():
            updated = Giftcard.objects.filter(pk=gid, user=owner).update(
                balance=_dec(new_balance)
            )
            if not updated:
                raise ValueError(f'Giftcard {gid} not found')
            Transaction.objects.create(
                id=uuid.uuid4(),
                version=1,
                user=owner,
                row_number=int(row_number),
                date=_parse_date(date),
                change=_dec(change),
                source_id=_resolve_source_id(GIFTCARD_SOURCE_NAME),
                comment=str(comment or ''),
                category_id=_resolve_category_id(sub_category or ''),
                giftcard_id=gid,
            )
    except Exception:
        logger.exception('Postgres dual-write failed for giftcard use %s', giftcard_id)


def update_transaction_detail(
    *,
    user: User,
    transaction: Transaction,
    date: Any,
    change: Any,
    source: str,
    comment: str,
    sub_category: str,
    receipt_total: Any | None = None,
    items: list[dict] | None = None,
    sibling_updates: list[Transaction] | None = None,
) -> None:
    """Update a transaction (and linked receipt items) after Sheets writes succeed."""
    owner = _require_user(user)
    try:
        with db_transaction.atomic():
            transaction.date = _parse_date(date)
            transaction.change = _dec(change)
            transaction.source_id = _resolve_source_id(source)
            transaction.comment = str(comment or '')
            transaction.category_id = _resolve_category_id(sub_category or '')
            transaction.version = (transaction.version or 1) + 1
            transaction.save(
                update_fields=[
                    'date',
                    'change',
                    'source_id',
                    'comment',
                    'category_id',
                    'version',
                ]
            )

            for sibling in sibling_updates or []:
                sibling.date = transaction.date
                sibling.comment = transaction.comment
                sibling.category_id = transaction.category_id
                sibling.version = (sibling.version or 1) + 1
                sibling.save(update_fields=['date', 'comment', 'category_id', 'version'])

            if transaction.receipt_id:
                receipt = Receipt.objects.select_for_update().get(
                    pk=transaction.receipt_id, user=owner
                )
                receipt.date = transaction.date
                if receipt_total is not None:
                    receipt.total = _dec(receipt_total)
                receipt.version = (receipt.version or 1) + 1
                receipt.save(update_fields=['date', 'total', 'version'])

                if items is not None:
                    ReceiptItem.objects.filter(receipt=receipt, user=owner).delete()
                    ReceiptItem.objects.bulk_create(
                        [
                            ReceiptItem(
                                id=uuid.uuid4(),
                                version=1,
                                user=owner,
                                receipt=receipt,
                                name=str(it['name']),
                                amount=_dec(it['amount']),
                                unit=str(it['unit']),
                                money=_dec(it['money']),
                            )
                            for it in items
                        ]
                    )
    except Exception:
        logger.exception(
            'Postgres dual-write failed for transaction update %s', transaction.id
        )
        raise

