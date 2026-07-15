"""Compare and bulk-sync Sheet mirror tables into Postgres."""

from __future__ import annotations

import re
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction as db_transaction
from django.utils import timezone

from finance.db_writer import _parse_date
from finance.models import Category, Receipt, ReceiptItem, Source, Transaction
from finance.sheets_client import SheetsClient

MIRROR_TABLE_KEYS = (
    'transactions',
    'receipt',
    'receipt_items',
    'category',
    'sources',
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
    return (str(receipt_id), str(name or '').strip(), _fp_dec(amount), str(unit or '').strip(), _fp_dec(money))


def _tx_fp(
    row_number: int,
    d: date,
    change: Decimal,
    source: str,
    comment: str,
    sub_category: str,
    receipt_id: uuid.UUID | None,
) -> tuple:
    return (
        int(row_number),
        d.isoformat(),
        _fp_dec(change),
        str(source or '').strip(),
        str(comment or ''),
        str(sub_category or '').strip(),
        str(receipt_id) if receipt_id else '',
    )


def _category_fp(main_category: str, sub_category: str, type_: str) -> tuple:
    return (
        str(main_category or '').strip(),
        str(sub_category or '').strip(),
        str(type_ or '').strip(),
    )


def _source_fp(name: str, type_: str) -> tuple:
    return (str(name or '').strip(), str(type_ or '').strip())


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


def _parse_tx_row(
    row: dict, index: int
) -> tuple[int, date, Decimal, str, str, str, uuid.UUID | None]:
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
        )
    except ValueError as exc:
        raise SyncError(f'Transaction row {index + 1}: {exc}') from exc


def _parse_category_row(row: dict, index: int) -> tuple[str, str, str]:
    try:
        main = str(_cell(row, 'Main Category') or '').strip()
        sub = str(_cell(row, 'Sub category', 'Sub Category') or '').strip()
        if not main:
            raise ValueError('Main Category is required')
        if not sub:
            raise ValueError('Sub category is required')
        return (main, sub, str(_cell(row, 'Type') or '').strip())
    except ValueError as exc:
        raise SyncError(f'Category row {index + 1}: {exc}') from exc


def _parse_source_row(row: dict, index: int) -> tuple[str, str]:
    try:
        name = str(_cell(row, 'Name') or '').strip()
        if not name:
            raise ValueError('Name is required')
        return (name, str(_cell(row, 'Type') or '').strip())
    except ValueError as exc:
        raise SyncError(f'Source row {index + 1}: {exc}') from exc


def _parse_sheet_fingerprints(source: dict[str, list[dict]]) -> dict[str, list[tuple]]:
    receipts = [
        _receipt_fp(*_parse_receipt_row(row, i)) for i, row in enumerate(source['receipts'])
    ]
    items = [
        _item_fp(*_parse_item_row(row, i)) for i, row in enumerate(source['receipt_items'])
    ]
    transactions = [
        _tx_fp(*_parse_tx_row(row, i)) for i, row in enumerate(source['transactions'])
    ]
    categories = [
        _category_fp(*_parse_category_row(row, i)) for i, row in enumerate(source['categories'])
    ]
    sources = [
        _source_fp(*_parse_source_row(row, i)) for i, row in enumerate(source['sources'])
    ]
    return {
        'receipt': receipts,
        'receipt_items': items,
        'transactions': transactions,
        'category': categories,
        'sources': sources,
    }


def _db_fingerprints() -> dict[str, list[tuple]]:
    receipts = [
        _receipt_fp(r.id, r.date, r.total) for r in Receipt.objects.all().iterator()
    ]
    items = [
        _item_fp(it.receipt_id, it.name, it.amount, it.unit, it.money)
        for it in ReceiptItem.objects.all().iterator()
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
        )
        for tx in Transaction.objects.select_related('source', 'category').iterator()
    ]
    categories = [
        _category_fp(c.main_category, c.sub_category, c.type)
        for c in Category.objects.all().iterator()
    ]
    sources = [_source_fp(s.name, s.type) for s in Source.objects.all().iterator()]
    return {
        'receipt': receipts,
        'receipt_items': items,
        'transactions': transactions,
        'category': categories,
        'sources': sources,
    }


def _table_status(sheet_fps: list[tuple], db_fps: list[tuple]) -> dict:
    return {
        'sheet_count': len(sheet_fps),
        'db_count': len(db_fps),
        'matched': sorted(sheet_fps) == sorted(db_fps),
    }


def compare_mirror(client: SheetsClient) -> dict:
    """Return Sheet vs Postgres match status for mirror tables."""
    source = client.get_mirror_source_rows()
    sheet_fps = _parse_sheet_fingerprints(source)
    db_fps = _db_fingerprints()

    tables = {
        key: _table_status(sheet_fps[key], db_fps[key]) for key in MIRROR_TABLE_KEYS
    }
    return {
        'matched': all(t['matched'] for t in tables.values()),
        'checked_at': timezone.now().isoformat(),
        'tables': tables,
    }


def sync_from_sheets(client: SheetsClient) -> dict:
    """
    Wipe Postgres mirror tables and reload from Google Sheet.

    Parses all sheet rows first so validation errors leave the DB unchanged.
    Wipe + insert run in one atomic block.
    """
    source = client.get_mirror_source_rows()

    category_objs: list[Category] = []
    category_by_sub: dict[str, uuid.UUID] = {}
    for i, row in enumerate(source['categories']):
        main, sub, type_ = _parse_category_row(row, i)
        if sub in category_by_sub:
            raise SyncError(f'Category row {i + 1}: duplicate Sub category {sub!r}')
        cid = uuid.uuid4()
        category_by_sub[sub] = cid
        category_objs.append(
            Category(
                id=cid,
                version=1,
                main_category=main,
                sub_category=sub,
                type=type_,
            )
        )

    source_objs: list[Source] = []
    source_by_name: dict[str, uuid.UUID] = {}
    for i, row in enumerate(source['sources']):
        name, type_ = _parse_source_row(row, i)
        if name in source_by_name:
            raise SyncError(f'Source row {i + 1}: duplicate Name {name!r}')
        sid = uuid.uuid4()
        source_by_name[name] = sid
        source_objs.append(Source(id=sid, version=1, name=name, type=type_))

    receipt_objs: list[Receipt] = []
    seen_receipt_ids: set[uuid.UUID] = set()
    for i, row in enumerate(source['receipts']):
        rid, d, total = _parse_receipt_row(row, i)
        if rid in seen_receipt_ids:
            raise SyncError(f'Receipt row {i + 1}: duplicate Receipt ID {rid}')
        seen_receipt_ids.add(rid)
        receipt_objs.append(Receipt(id=rid, version=1, date=d, total=total))

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
                receipt_id=rid,
                name=name,
                amount=amount,
                unit=unit,
                money=money,
            )
        )

    tx_objs: list[Transaction] = []
    seen_tx_rows: set[int] = set()
    for i, row in enumerate(source['transactions']):
        row_number, d, change, source_name, comment, sub_category, receipt_id = _parse_tx_row(
            row, i
        )
        if row_number in seen_tx_rows:
            raise SyncError(
                f'Transaction row {i + 1}: duplicate sheet row_number {row_number}'
            )
        seen_tx_rows.add(row_number)
        if source_name not in source_by_name:
            raise SyncError(
                f'Transaction row {i + 1}: Source {source_name!r} not found in Sources table'
            )
        category_id = None
        if sub_category:
            category_id = category_by_sub.get(sub_category)
            if category_id is None:
                raise SyncError(
                    f'Transaction row {i + 1}: Sub category {sub_category!r} '
                    f'not found in Category table'
                )
        if receipt_id is not None and receipt_id not in seen_receipt_ids:
            raise SyncError(
                f'Transaction row {i + 1}: Receipt ID {receipt_id} not found in Receipt table'
            )
        tx_objs.append(
            Transaction(
                id=uuid.uuid4(),
                version=1,
                row_number=row_number,
                date=d,
                change=change,
                source_id=source_by_name[source_name],
                comment=comment,
                category_id=category_id,
                receipt_id=receipt_id,
            )
        )

    with db_transaction.atomic():
        Transaction.objects.all().delete()
        ReceiptItem.objects.all().delete()
        Receipt.objects.all().delete()
        Category.objects.all().delete()
        Source.objects.all().delete()
        Category.objects.bulk_create(category_objs)
        Source.objects.bulk_create(source_objs)
        Receipt.objects.bulk_create(receipt_objs)
        ReceiptItem.objects.bulk_create(item_objs)
        Transaction.objects.bulk_create(tx_objs)

    return {
        'ok': True,
        'inserted': {
            'transactions': len(tx_objs),
            'receipt': len(receipt_objs),
            'receipt_items': len(item_objs),
            'category': len(category_objs),
            'sources': len(source_objs),
        },
    }
