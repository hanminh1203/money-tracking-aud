"""Compare and bulk-sync Sheet mirror tables into Postgres (per user)."""

from __future__ import annotations

import re
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction as db_transaction
from django.utils import timezone

from finance.db_writer import _parse_date
from finance.models import Category, Giftcard, Receipt, ReceiptItem, Source, Transaction, User
from finance.sheets_client import SheetsClient

# Sync/compare only these user-owned tables (Category/Source are shared, not synced).
MIRROR_TABLE_KEYS = (
    'transactions',
    'receipt',
    'receipt_items',
    'giftcards',
)


class SyncError(Exception):
    """Raised when Sheet→Postgres sync cannot proceed safely."""


def _cell(row: dict, *names: str) -> Any:
    lower = {str(k).strip().lower(): v for k, v in row.items()}
    for name in names:
        if name.lower() in lower:
            return lower[name.lower()]
    return None


def _sheet_dec(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = re.sub(r'[^0-9.\-]', '', str(value or '').strip())
    if not text or text == '-' or text == '.':
        raise ValueError(f'Invalid decimal: {value!r}')
    try:
        return Decimal(text)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f'Invalid decimal: {value!r}') from exc


def _optional_uuid(value: Any) -> uuid.UUID | None:
    text = str(value or '').strip()
    if not text:
        return None
    try:
        return uuid.UUID(text)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f'Invalid UUID: {value!r}') from exc


def _fp_dec(value: Decimal) -> str:
    return format(value.normalize(), 'f')


def _receipt_fp(receipt_id: uuid.UUID, d: date, total: Decimal) -> tuple:
    return (str(receipt_id), d.isoformat(), _fp_dec(total))


def _item_fp(
    receipt_id: uuid.UUID, name: str, amount: Decimal, unit: str, money: Decimal
) -> tuple:
    return (
        str(receipt_id),
        str(name or '').strip(),
        _fp_dec(amount),
        str(unit or '').strip(),
        _fp_dec(money),
    )


def _giftcard_fp(
    row_number: int, giftcard_id: uuid.UUID, shop: str, d: date, balance: Decimal
) -> tuple:
    return (
        int(row_number),
        str(giftcard_id),
        str(shop or '').strip(),
        d.isoformat(),
        _fp_dec(balance),
    )


def _tx_fp(
    row_number: int,
    d: date,
    change: Decimal,
    source: str,
    comment: str,
    sub_category: str,
    receipt_id: uuid.UUID | None,
    giftcard_id: uuid.UUID | None,
) -> tuple:
    return (
        int(row_number),
        d.isoformat(),
        _fp_dec(change),
        str(source or '').strip(),
        str(comment or ''),
        str(sub_category or '').strip(),
        str(receipt_id) if receipt_id else '',
        str(giftcard_id) if giftcard_id else '',
    )


def _parse_receipt_row(row: dict, index: int) -> tuple[uuid.UUID, date, Decimal]:
    try:
        rid = _optional_uuid(_cell(row, 'Receipt ID'))
        if rid is None:
            raise ValueError('Receipt ID is required')
        return (
            rid,
            _parse_date(_cell(row, 'Date')),
            _sheet_dec(_cell(row, 'Total')),
        )
    except ValueError as exc:
        raise SyncError(f'Receipt row {index + 1}: {exc}') from exc


def _parse_item_row(row: dict, index: int) -> tuple[uuid.UUID, str, Decimal, str, Decimal]:
    try:
        rid = _optional_uuid(_cell(row, 'Receipt ID'))
        if rid is None:
            raise ValueError('Receipt ID is required')
        name = str(_cell(row, 'Name') or '').strip()
        if not name:
            raise ValueError('Name is required')
        unit = str(_cell(row, 'Unit') or '').strip()
        return (
            rid,
            name,
            _sheet_dec(_cell(row, 'Amount')),
            unit,
            _sheet_dec(_cell(row, 'Money')),
        )
    except ValueError as exc:
        raise SyncError(f'Receipt item row {index + 1}: {exc}') from exc


def _parse_giftcard_row(
    row: dict, index: int
) -> tuple[int, uuid.UUID, str, date, Decimal]:
    try:
        gid = _optional_uuid(_cell(row, 'Giftcard ID'))
        if gid is None:
            raise ValueError('Giftcard ID is required')
        shop = str(_cell(row, 'Shop') or '').strip()
        if not shop:
            raise ValueError('Shop is required')
        sheet_row = row.get('__sheet_row')
        if sheet_row is None:
            raise ValueError('Sheet row number is required')
        return (
            int(sheet_row),
            gid,
            shop,
            _parse_date(_cell(row, 'Date')),
            _sheet_dec(_cell(row, 'Balance')),
        )
    except ValueError as exc:
        raise SyncError(f'Giftcard row {index + 1}: {exc}') from exc


def _parse_tx_row(
    row: dict, index: int
) -> tuple[int, date, Decimal, str, str, str, uuid.UUID | None, uuid.UUID | None]:
    try:
        source_name = str(_cell(row, 'Source') or '').strip()
        if not source_name:
            raise ValueError('Source is required')
        sheet_row = row.get('__sheet_row')
        if sheet_row is None:
            raise ValueError('Sheet row number is required')
        return (
            int(sheet_row),
            _parse_date(_cell(row, 'Date')),
            _sheet_dec(_cell(row, 'Change')),
            source_name,
            str(_cell(row, 'Comment') or ''),
            str(_cell(row, 'Sub category', 'Sub Category') or '').strip(),
            _optional_uuid(_cell(row, 'Receipt ID')),
            _optional_uuid(_cell(row, 'Giftcard ID')),
        )
    except ValueError as exc:
        raise SyncError(f'Transaction row {index + 1}: {exc}') from exc


def _parse_sheet_fingerprints(source: dict[str, list[dict]]) -> dict[str, list[tuple]]:
    receipts = [
        _receipt_fp(*_parse_receipt_row(row, i)) for i, row in enumerate(source['receipts'])
    ]
    items = [
        _item_fp(*_parse_item_row(row, i)) for i, row in enumerate(source['receipt_items'])
    ]
    giftcards = [
        _giftcard_fp(*_parse_giftcard_row(row, i)) for i, row in enumerate(source['giftcards'])
    ]
    transactions = [
        _tx_fp(*_parse_tx_row(row, i)) for i, row in enumerate(source['transactions'])
    ]
    return {
        'receipt': receipts,
        'receipt_items': items,
        'giftcards': giftcards,
        'transactions': transactions,
    }


def _db_fingerprints(*, user: User) -> dict[str, list[tuple]]:
    receipts = [
        _receipt_fp(r.id, r.date, r.total)
        for r in Receipt.objects.filter(user=user).iterator()
    ]
    items = [
        _item_fp(it.receipt_id, it.name, it.amount, it.unit, it.money)
        for it in ReceiptItem.objects.filter(user=user).iterator()
    ]
    giftcards = [
        _giftcard_fp(g.row_number, g.id, g.shop, g.date, g.balance)
        for g in Giftcard.objects.filter(user=user).iterator()
    ]
    transactions = [
        _tx_fp(
            tx.row_number,
            tx.date,
            tx.change,
            tx.source.name if tx.source_id else '',
            tx.comment,
            tx.category.sub_category if tx.category_id else '',
            tx.receipt_id,
            tx.giftcard_id,
        )
        for tx in Transaction.objects.filter(user=user)
        .select_related('source', 'category')
        .iterator()
    ]
    return {
        'receipt': receipts,
        'receipt_items': items,
        'giftcards': giftcards,
        'transactions': transactions,
    }


def _table_status(sheet_fps: list[tuple], db_fps: list[tuple]) -> dict:
    return {
        'sheet_count': len(sheet_fps),
        'db_count': len(db_fps),
        'matched': sorted(sheet_fps) == sorted(db_fps),
    }


def compare_mirror(client: SheetsClient, *, user: User) -> dict:
    """Return Sheet vs Postgres match status for user-owned mirror tables."""
    source = client.get_mirror_source_rows()
    sheet_fps = _parse_sheet_fingerprints(source)
    db_fps = _db_fingerprints(user=user)

    tables = {
        key: _table_status(sheet_fps[key], db_fps[key]) for key in MIRROR_TABLE_KEYS
    }
    return {
        'matched': all(t['matched'] for t in tables.values()),
        'checked_at': timezone.now().isoformat(),
        'tables': tables,
    }


def sync_from_sheets(client: SheetsClient, *, user: User) -> dict:
    """
    Wipe this user's Transaction/Receipt/ReceiptItem/Giftcard rows and reload from Sheet.

    Resolves Source/Category names against existing shared tables (not synced).
    Parses all sheet rows first so validation errors leave the DB unchanged.
    """
    source = client.get_mirror_source_rows()

    source_by_name = {s.name: s.id for s in Source.objects.all()}
    category_by_sub = {c.sub_category: c.id for c in Category.objects.all()}

    receipt_objs: list[Receipt] = []
    seen_receipt_ids: set[uuid.UUID] = set()
    for i, row in enumerate(source['receipts']):
        rid, d, total = _parse_receipt_row(row, i)
        if rid in seen_receipt_ids:
            raise SyncError(f'Receipt row {i + 1}: duplicate Receipt ID {rid}')
        seen_receipt_ids.add(rid)
        receipt_objs.append(Receipt(id=rid, version=1, user=user, date=d, total=total))

    item_objs: list[ReceiptItem] = []
    for i, row in enumerate(source['receipt_items']):
        rid, name, amount, unit, money = _parse_item_row(row, i)
        if rid not in seen_receipt_ids:
            raise SyncError(
                f'Receipt item row {i + 1}: Receipt ID {rid} not found in Receipt table'
            )
        item_objs.append(
            ReceiptItem(
                id=uuid.uuid4(),
                version=1,
                user=user,
                receipt_id=rid,
                name=name,
                amount=amount,
                unit=unit,
                money=money,
            )
        )

    giftcard_objs: list[Giftcard] = []
    seen_giftcard_ids: set[uuid.UUID] = set()
    seen_giftcard_rows: set[int] = set()
    for i, row in enumerate(source['giftcards']):
        row_number, gid, shop, d, balance = _parse_giftcard_row(row, i)
        if gid in seen_giftcard_ids:
            raise SyncError(f'Giftcard row {i + 1}: duplicate Giftcard ID {gid}')
        if row_number in seen_giftcard_rows:
            raise SyncError(
                f'Giftcard row {i + 1}: duplicate sheet row_number {row_number}'
            )
        seen_giftcard_ids.add(gid)
        seen_giftcard_rows.add(row_number)
        giftcard_objs.append(
            Giftcard(
                id=gid,
                version=1,
                user=user,
                row_number=row_number,
                shop=shop,
                date=d,
                balance=balance,
            )
        )

    tx_objs: list[Transaction] = []
    seen_tx_rows: set[int] = set()
    for i, row in enumerate(source['transactions']):
        (
            row_number,
            d,
            change,
            source_name,
            comment,
            sub_category,
            receipt_id,
            giftcard_id,
        ) = _parse_tx_row(row, i)
        if row_number in seen_tx_rows:
            raise SyncError(
                f'Transaction row {i + 1}: duplicate sheet row_number {row_number}'
            )
        seen_tx_rows.add(row_number)
        if source_name not in source_by_name:
            raise SyncError(
                f'Transaction row {i + 1}: Source {source_name!r} not found '
                f'(add it to Sources first)'
            )
        category_id = None
        if sub_category:
            category_id = category_by_sub.get(sub_category)
            if category_id is None:
                raise SyncError(
                    f'Transaction row {i + 1}: Sub category {sub_category!r} '
                    f'not found (add it to Category first)'
                )
        if receipt_id is not None and receipt_id not in seen_receipt_ids:
            raise SyncError(
                f'Transaction row {i + 1}: Receipt ID {receipt_id} not found in Receipt table'
            )
        if giftcard_id is not None and giftcard_id not in seen_giftcard_ids:
            raise SyncError(
                f'Transaction row {i + 1}: Giftcard ID {giftcard_id} not found in Giftcard table'
            )
        tx_objs.append(
            Transaction(
                id=uuid.uuid4(),
                version=1,
                user=user,
                row_number=row_number,
                date=d,
                change=change,
                source_id=source_by_name[source_name],
                comment=comment,
                category_id=category_id,
                receipt_id=receipt_id,
                giftcard_id=giftcard_id,
            )
        )

    with db_transaction.atomic():
        Transaction.objects.filter(user=user).delete()
        ReceiptItem.objects.filter(user=user).delete()
        Receipt.objects.filter(user=user).delete()
        Giftcard.objects.filter(user=user).delete()
        Receipt.objects.bulk_create(receipt_objs)
        ReceiptItem.objects.bulk_create(item_objs)
        Giftcard.objects.bulk_create(giftcard_objs)
        Transaction.objects.bulk_create(tx_objs)

    return {
        'ok': True,
        'inserted': {
            'transactions': len(tx_objs),
            'receipt': len(receipt_objs),
            'receipt_items': len(item_objs),
            'giftcards': len(giftcard_objs),
        },
    }
