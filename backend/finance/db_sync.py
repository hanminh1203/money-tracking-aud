"""Compare and bulk-sync Sheet mirror tables into Postgres (per user)."""

from __future__ import annotations

import re
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction as db_transaction
from django.utils import timezone

from finance.db_writer import _parse_date, receipt_item_id_for_row
from finance.models import (
    Category,
    Giftcard,
    Product,
    ProductItem,
    Receipt,
    ReceiptItem,
    Source,
    Transaction,
    User,
)
from finance.sheets_client import SheetsClient

# Sync/compare only these user-owned tables (Category/Source are shared, not synced).
MIRROR_TABLE_KEYS = (
    'transactions',
    'receipt',
    'receipt_items',
    'giftcards',
    'products',
    'product_items',
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
    item_id: uuid.UUID,
    receipt_id: uuid.UUID,
    name: str,
    amount: Decimal,
    unit: str,
    money: Decimal,
) -> tuple:
    return (
        str(item_id),
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
    transaction_id: uuid.UUID,
    d: date,
    change: Decimal,
    source: str,
    comment: str,
    sub_category: str,
    receipt_id: uuid.UUID | None,
    giftcard_id: uuid.UUID | None,
) -> tuple:
    return (
        str(transaction_id),
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


def _parse_item_row(
    row: dict, index: int
) -> tuple[uuid.UUID, uuid.UUID, str, Decimal, str, Decimal]:
    try:
        rid = _optional_uuid(_cell(row, 'Receipt ID'))
        if rid is None:
            raise ValueError('Receipt ID is required')
        name = str(_cell(row, 'Name') or '').strip()
        if not name:
            raise ValueError('Name is required')
        unit = str(_cell(row, 'Unit') or '').strip()
        amount = _sheet_dec(_cell(row, 'Amount'))
        money = _sheet_dec(_cell(row, 'Money'))
        item_id = receipt_item_id_for_row(
            item_id=_cell(row, 'Receipt Item ID'),
            receipt_id=rid,
            name=name,
            amount=amount,
            unit=unit,
            money=money,
        )
        return (item_id, rid, name, amount, unit, money)
    except ValueError as exc:
        raise SyncError(f'Receipt item row {index + 1}: {exc}') from exc


def _product_fp(product_id: uuid.UUID, name: str) -> tuple:
    return (str(product_id), str(name or '').strip())


def _product_item_fp(
    product_item_id: uuid.UUID,
    product_id: uuid.UUID,
    price: Decimal | None,
    transaction_id: uuid.UUID | None,
    receipt_item_id: uuid.UUID | None,
) -> tuple:
    return (
        str(product_item_id),
        str(product_id),
        _fp_dec(price) if price is not None else '',
        str(transaction_id) if transaction_id else '',
        str(receipt_item_id) if receipt_item_id else '',
    )


def _parse_product_row(row: dict, index: int) -> tuple[uuid.UUID, str]:
    try:
        pid = _optional_uuid(_cell(row, 'Product ID'))
        if pid is None:
            raise ValueError('Product ID is required')
        name = str(_cell(row, 'Name') or '').strip()
        if not name:
            raise ValueError('Name is required')
        return pid, name
    except ValueError as exc:
        raise SyncError(f'Product row {index + 1}: {exc}') from exc


def _parse_product_item_row(
    row: dict, index: int
) -> tuple[uuid.UUID, uuid.UUID, Decimal | None, uuid.UUID | None, uuid.UUID | None]:
    try:
        pi_id = _optional_uuid(_cell(row, 'Product Item ID'))
        if pi_id is None:
            raise ValueError('Product Item ID is required')
        product_id = _optional_uuid(_cell(row, 'Product ID'))
        if product_id is None:
            raise ValueError('Product ID is required')
        price_raw = _cell(row, 'Price')
        price = _sheet_dec(price_raw) if str(price_raw or '').strip() else None
        transaction_id = _optional_uuid(_cell(row, 'Transaction ID'))
        receipt_item_id = _optional_uuid(_cell(row, 'Receipt Item ID'))
        if bool(transaction_id) == bool(receipt_item_id):
            raise ValueError('Exactly one of Transaction ID or Receipt Item ID is required')
        if transaction_id is not None and price is None:
            raise ValueError('Price is required when Transaction ID is set')
        return pi_id, product_id, price, transaction_id, receipt_item_id
    except ValueError as exc:
        raise SyncError(f'Product item row {index + 1}: {exc}') from exc


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
) -> tuple[uuid.UUID, int, date, Decimal, str, str, str, uuid.UUID | None, uuid.UUID | None]:
    try:
        transaction_id = _optional_uuid(_cell(row, 'Transaction ID'))
        if transaction_id is None:
            raise ValueError('Transaction ID is required')
        source_name = str(_cell(row, 'Source') or '').strip()
        if not source_name:
            raise ValueError('Source is required')
        sheet_row = row.get('__sheet_row')
        if sheet_row is None:
            raise ValueError('Sheet row number is required')
        return (
            transaction_id,
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
        _tx_fp(
            transaction_id,
            d,
            change,
            source_name,
            comment,
            sub_category,
            receipt_id,
            giftcard_id,
        )
        for i, row in enumerate(source['transactions'])
        for (
            transaction_id,
            _row_number,
            d,
            change,
            source_name,
            comment,
            sub_category,
            receipt_id,
            giftcard_id,
        ) in [_parse_tx_row(row, i)]
    ]
    products = [
        _product_fp(*_parse_product_row(row, i)) for i, row in enumerate(source.get('products', []))
    ]
    product_items = [
        _product_item_fp(*_parse_product_item_row(row, i))
        for i, row in enumerate(source.get('product_items', []))
    ]
    return {
        'receipt': receipts,
        'receipt_items': items,
        'giftcards': giftcards,
        'transactions': transactions,
        'products': products,
        'product_items': product_items,
    }


def _db_fingerprints(*, user: User) -> dict[str, list[tuple]]:
    receipts = [
        _receipt_fp(r.id, r.date, r.total)
        for r in Receipt.objects.filter(user=user).iterator()
    ]
    items = [
        _item_fp(it.id, it.receipt_id, it.name, it.amount, it.unit, it.money)
        for it in ReceiptItem.objects.filter(user=user).iterator()
    ]
    giftcards = [
        _giftcard_fp(g.row_number, g.id, g.shop, g.date, g.balance)
        for g in Giftcard.objects.filter(user=user).iterator()
    ]
    transactions = [
        _tx_fp(
            tx.id,
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
    products = [
        _product_fp(p.id, p.name) for p in Product.objects.filter(user=user).iterator()
    ]
    product_items = [
        _product_item_fp(
            pi.id,
            pi.product_id,
            pi.price,
            pi.transaction_id,
            pi.receipt_item_id,
        )
        for pi in ProductItem.objects.filter(user=user).iterator()
    ]
    return {
        'receipt': receipts,
        'receipt_items': items,
        'giftcards': giftcards,
        'transactions': transactions,
        'products': products,
        'product_items': product_items,
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
        item_id, rid, name, amount, unit, money = _parse_item_row(row, i)
        if rid not in seen_receipt_ids:
            raise SyncError(
                f'Receipt item row {i + 1}: Receipt ID {rid} not found in Receipt table'
            )
        item_objs.append(
            ReceiptItem(
                id=item_id,
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
    seen_tx_ids: set[uuid.UUID] = set()
    for i, row in enumerate(source['transactions']):
        (
            transaction_id,
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
        if transaction_id in seen_tx_ids:
            raise SyncError(
                f'Transaction row {i + 1}: duplicate Transaction ID {transaction_id}'
            )
        seen_tx_rows.add(row_number)
        seen_tx_ids.add(transaction_id)
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
                id=transaction_id,
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

    product_objs: list[Product] = []
    seen_product_ids: set[uuid.UUID] = set()
    for i, row in enumerate(source.get('products', [])):
        pid, name = _parse_product_row(row, i)
        if pid in seen_product_ids:
            raise SyncError(f'Product row {i + 1}: duplicate Product ID {pid}')
        seen_product_ids.add(pid)
        product_objs.append(Product(id=pid, version=1, user=user, name=name))

    tx_by_id = {tx.id: tx for tx in tx_objs}
    receipt_item_by_id = {it.id: it for it in item_objs}

    product_item_objs: list[ProductItem] = []
    seen_product_item_ids: set[uuid.UUID] = set()
    for i, row in enumerate(source.get('product_items', [])):
        pi_id, product_id, price, sheet_tx_id, receipt_item_id = _parse_product_item_row(
            row, i
        )
        if pi_id in seen_product_item_ids:
            raise SyncError(f'Product item row {i + 1}: duplicate Product Item ID {pi_id}')
        seen_product_item_ids.add(pi_id)
        if product_id not in seen_product_ids:
            raise SyncError(
                f'Product item row {i + 1}: Product ID {product_id} not found in Product table'
            )
        transaction_id = None
        if sheet_tx_id is not None:
            if sheet_tx_id not in tx_by_id:
                raise SyncError(
                    f'Product item row {i + 1}: Transaction ID {sheet_tx_id} not found'
                )
            transaction_id = sheet_tx_id
        if receipt_item_id is not None and receipt_item_id not in receipt_item_by_id:
            raise SyncError(
                f'Product item row {i + 1}: Receipt Item ID {receipt_item_id} not found'
            )
        product_item_objs.append(
            ProductItem(
                id=pi_id,
                version=1,
                user=user,
                product_id=product_id,
                transaction_id=transaction_id,
                receipt_item_id=receipt_item_id,
                price=price,
            )
        )

    with db_transaction.atomic():
        ProductItem.objects.filter(user=user).delete()
        Product.objects.filter(user=user).delete()
        Transaction.objects.filter(user=user).delete()
        ReceiptItem.objects.filter(user=user).delete()
        Receipt.objects.filter(user=user).delete()
        Giftcard.objects.filter(user=user).delete()
        Receipt.objects.bulk_create(receipt_objs)
        ReceiptItem.objects.bulk_create(item_objs)
        Giftcard.objects.bulk_create(giftcard_objs)
        Transaction.objects.bulk_create(tx_objs)
        Product.objects.bulk_create(product_objs)
        ProductItem.objects.bulk_create(product_item_objs)

    return {
        'ok': True,
        'inserted': {
            'transactions': len(tx_objs),
            'receipt': len(receipt_objs),
            'receipt_items': len(item_objs),
            'giftcards': len(giftcard_objs),
            'products': len(product_objs),
            'product_items': len(product_item_objs),
        },
    }
