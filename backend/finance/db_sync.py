"""Compare and bulk-sync Sheet mirror tables into Postgres (per user)."""

from __future__ import annotations

import re
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction as db_transaction
from django.utils import timezone

from finance.db_writer import _optional_date, _parse_date, receipt_item_id_for_row
from finance.models import (
    Category,
    Giftcard,
    GiftcardPayment,
    Payment,
    Product,
    ProductItem,
    Receipt,
    ReceiptItem,
    Source,
    Transaction,
    User,
)
from finance.sheets_client import SheetsClient

# Sync/compare these user-owned tables (including Category/Source lookups).
MIRROR_TABLE_KEYS = (
    'transactions',
    'payment',
    'giftcard_payment',
    'receipt',
    'receipt_items',
    'giftcards',
    'products',
    'product_items',
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


def _receipt_fp(
    receipt_id: uuid.UUID, transaction_id: uuid.UUID, d: date, total: Decimal
) -> tuple:
    return (str(receipt_id), str(transaction_id), d.isoformat(), _fp_dec(total))


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
    comment: str,
    sub_category: str,
) -> tuple:
    return (
        str(transaction_id),
        d.isoformat(),
        _fp_dec(change),
        str(comment or ''),
        str(sub_category or '').strip(),
    )


def _payment_fp(
    payment_id: uuid.UUID,
    transaction_id: uuid.UUID,
    source: str,
    amount: Decimal,
) -> tuple:
    return (
        str(payment_id),
        str(transaction_id),
        str(source or '').strip(),
        _fp_dec(amount),
    )


def _giftcard_payment_fp(
    giftcard_payment_id: uuid.UUID,
    transaction_id: uuid.UUID,
    giftcard_id: uuid.UUID,
    amount: Decimal,
) -> tuple:
    return (
        str(giftcard_payment_id),
        str(transaction_id),
        str(giftcard_id),
        _fp_dec(amount),
    )


def _parse_receipt_row(
    row: dict, index: int
) -> tuple[uuid.UUID, uuid.UUID, date, Decimal]:
    try:
        rid = _optional_uuid(_cell(row, 'Receipt ID'))
        if rid is None:
            raise ValueError('Receipt ID is required')
        transaction_id = _optional_uuid(_cell(row, 'Transaction ID'))
        if transaction_id is None:
            raise ValueError('Transaction ID is required')
        return (
            rid,
            transaction_id,
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
    end_date: date | None,
) -> tuple:
    return (
        str(product_item_id),
        str(product_id),
        _fp_dec(price) if price is not None else '',
        str(transaction_id) if transaction_id else '',
        str(receipt_item_id) if receipt_item_id else '',
        end_date.isoformat() if end_date else '',
    )


def _category_fp(main_category: str, sub_category: str, type_name: str) -> tuple:
    return (
        str(main_category or '').strip(),
        str(sub_category or '').strip(),
        str(type_name or '').strip(),
    )


def _source_fp(name: str, type_name: str) -> tuple:
    return (str(name or '').strip(), str(type_name or '').strip())


def _parse_category_row(row: dict, index: int) -> tuple[str, str, str]:
    try:
        main_category = str(_cell(row, 'Main Category') or '').strip()
        if not main_category:
            raise ValueError('Main Category is required')
        sub_category = str(_cell(row, 'Sub category', 'Sub Category') or '').strip()
        if not sub_category:
            raise ValueError('Sub category is required')
        type_name = str(_cell(row, 'Type') or '').strip()
        return main_category, sub_category, type_name
    except ValueError as exc:
        raise SyncError(f'Category row {index + 1}: {exc}') from exc


def _parse_source_row(row: dict, index: int) -> tuple[str, str]:
    try:
        name = str(_cell(row, 'Name') or '').strip()
        if not name:
            raise ValueError('Name is required')
        type_name = str(_cell(row, 'Type') or '').strip()
        return name, type_name
    except ValueError as exc:
        raise SyncError(f'Source row {index + 1}: {exc}') from exc


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
) -> tuple[
    uuid.UUID, uuid.UUID, Decimal | None, uuid.UUID | None, uuid.UUID | None, date | None
]:
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
        end_date = _optional_date(_cell(row, 'End Date', 'end_date'))
        return pi_id, product_id, price, transaction_id, receipt_item_id, end_date
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
) -> tuple[uuid.UUID, int, date, Decimal, str, str]:
    try:
        transaction_id = _optional_uuid(_cell(row, 'Transaction ID'))
        if transaction_id is None:
            raise ValueError('Transaction ID is required')
        sheet_row = row.get('__sheet_row')
        if sheet_row is None:
            raise ValueError('Sheet row number is required')
        return (
            transaction_id,
            int(sheet_row),
            _parse_date(_cell(row, 'Date')),
            _sheet_dec(_cell(row, 'Change')),
            str(_cell(row, 'Comment') or ''),
            str(_cell(row, 'Sub category', 'Sub Category') or '').strip(),
        )
    except ValueError as exc:
        raise SyncError(f'Transaction row {index + 1}: {exc}') from exc


def _parse_payment_row(
    row: dict, index: int
) -> tuple[uuid.UUID, int, uuid.UUID, str, Decimal]:
    try:
        payment_id = _optional_uuid(_cell(row, 'Payment ID'))
        if payment_id is None:
            raise ValueError('Payment ID is required')
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
            payment_id,
            int(sheet_row),
            transaction_id,
            source_name,
            _sheet_dec(_cell(row, 'Amount')),
        )
    except ValueError as exc:
        raise SyncError(f'Payment row {index + 1}: {exc}') from exc


def _parse_giftcard_payment_row(
    row: dict, index: int
) -> tuple[uuid.UUID, int, uuid.UUID, uuid.UUID, Decimal]:
    try:
        giftcard_payment_id = _optional_uuid(_cell(row, 'Giftcard Payment ID'))
        if giftcard_payment_id is None:
            raise ValueError('Giftcard Payment ID is required')
        transaction_id = _optional_uuid(_cell(row, 'Transaction ID'))
        if transaction_id is None:
            raise ValueError('Transaction ID is required')
        giftcard_id = _optional_uuid(_cell(row, 'Giftcard ID'))
        if giftcard_id is None:
            raise ValueError('Giftcard ID is required')
        sheet_row = row.get('__sheet_row')
        if sheet_row is None:
            raise ValueError('Sheet row number is required')
        return (
            giftcard_payment_id,
            int(sheet_row),
            transaction_id,
            giftcard_id,
            _sheet_dec(_cell(row, 'Amount')),
        )
    except ValueError as exc:
        raise SyncError(f'Giftcard payment row {index + 1}: {exc}') from exc


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
            comment,
            sub_category,
        )
        for i, row in enumerate(source['transactions'])
        for (
            transaction_id,
            _row_number,
            d,
            change,
            comment,
            sub_category,
        ) in [_parse_tx_row(row, i)]
    ]
    payments = [
        _payment_fp(payment_id, transaction_id, source_name, amount)
        for i, row in enumerate(source.get('payments', []))
        for payment_id, _row_number, transaction_id, source_name, amount in [
            _parse_payment_row(row, i)
        ]
    ]
    giftcard_payments = [
        _giftcard_payment_fp(giftcard_payment_id, transaction_id, giftcard_id, amount)
        for i, row in enumerate(source.get('giftcard_payments', []))
        for giftcard_payment_id, _row_number, transaction_id, giftcard_id, amount in [
            _parse_giftcard_payment_row(row, i)
        ]
    ]
    products = [
        _product_fp(*_parse_product_row(row, i)) for i, row in enumerate(source.get('products', []))
    ]
    product_items = [
        _product_item_fp(*_parse_product_item_row(row, i))
        for i, row in enumerate(source.get('product_items', []))
    ]
    categories = [
        _category_fp(*_parse_category_row(row, i))
        for i, row in enumerate(source.get('categories', []))
    ]
    sources = [
        _source_fp(*_parse_source_row(row, i)) for i, row in enumerate(source.get('sources', []))
    ]
    return {
        'receipt': receipts,
        'receipt_items': items,
        'giftcards': giftcards,
        'transactions': transactions,
        'payment': payments,
        'giftcard_payment': giftcard_payments,
        'products': products,
        'product_items': product_items,
        'category': categories,
        'sources': sources,
    }


def _db_fingerprints(*, user: User) -> dict[str, list[tuple]]:
    receipts = [
        _receipt_fp(r.id, r.transaction_id, r.date, r.total)
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
            tx.comment,
            tx.category.sub_category if tx.category_id else '',
        )
        for tx in Transaction.objects.filter(user=user)
        .select_related('category')
        .iterator()
    ]
    payments = [
        _payment_fp(p.id, p.transaction_id, p.source.name if p.source_id else '', p.amount)
        for p in Payment.objects.filter(user=user).select_related('source').iterator()
    ]
    giftcard_payments = [
        _giftcard_payment_fp(gp.id, gp.transaction_id, gp.giftcard_id, gp.amount)
        for gp in GiftcardPayment.objects.filter(user=user).iterator()
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
            pi.end_date,
        )
        for pi in ProductItem.objects.filter(user=user).iterator()
    ]
    categories = [
        _category_fp(c.main_category, c.sub_category, c.type)
        for c in Category.objects.filter(user=user).iterator()
    ]
    sources = [
        _source_fp(s.name, s.type) for s in Source.objects.filter(user=user).iterator()
    ]
    return {
        'receipt': receipts,
        'receipt_items': items,
        'giftcards': giftcards,
        'transactions': transactions,
        'payment': payments,
        'giftcard_payment': giftcard_payments,
        'products': products,
        'product_items': product_items,
        'category': categories,
        'sources': sources,
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
    Wipe this user's mirror rows (including Source/Category) and reload from Sheet.

    Parses all sheet rows first so validation errors leave the DB unchanged.
    """
    source = client.get_mirror_source_rows()

    source_objs: list[Source] = []
    source_by_name: dict[str, uuid.UUID] = {}
    for i, row in enumerate(source.get('sources', [])):
        name, type_name = _parse_source_row(row, i)
        if name in source_by_name:
            raise SyncError(f'Source row {i + 1}: duplicate name {name!r}')
        source_id = uuid.uuid4()
        source_by_name[name] = source_id
        source_objs.append(
            Source(id=source_id, version=1, user=user, name=name, type=type_name)
        )

    category_objs: list[Category] = []
    category_by_sub: dict[str, uuid.UUID] = {}
    for i, row in enumerate(source.get('categories', [])):
        main_category, sub_category, type_name = _parse_category_row(row, i)
        if sub_category in category_by_sub:
            raise SyncError(f'Category row {i + 1}: duplicate Sub category {sub_category!r}')
        category_id = uuid.uuid4()
        category_by_sub[sub_category] = category_id
        category_objs.append(
            Category(
                id=category_id,
                version=1,
                user=user,
                main_category=main_category,
                sub_category=sub_category,
                type=type_name,
            )
        )

    receipt_objs: list[Receipt] = []
    seen_receipt_ids: set[uuid.UUID] = set()
    seen_receipt_tx_ids: set[uuid.UUID] = set()
    # Placeholder — receipts are built after transactions so Transaction ID can be validated.
    item_objs: list[ReceiptItem] = []

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
            comment,
            sub_category,
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
        category_id = None
        if sub_category:
            category_id = category_by_sub.get(sub_category)
            if category_id is None:
                raise SyncError(
                    f'Transaction row {i + 1}: Sub category {sub_category!r} '
                    f'not found (add it to Category first)'
                )
        tx_objs.append(
            Transaction(
                id=transaction_id,
                version=1,
                user=user,
                row_number=row_number,
                date=d,
                change=change,
                comment=comment,
                category_id=category_id,
            )
        )

    for i, row in enumerate(source['receipts']):
        rid, transaction_id, d, total = _parse_receipt_row(row, i)
        if rid in seen_receipt_ids:
            raise SyncError(f'Receipt row {i + 1}: duplicate Receipt ID {rid}')
        if transaction_id in seen_receipt_tx_ids:
            raise SyncError(
                f'Receipt row {i + 1}: duplicate Transaction ID {transaction_id}'
            )
        if transaction_id not in seen_tx_ids:
            raise SyncError(
                f'Receipt row {i + 1}: Transaction ID {transaction_id} not found '
                f'in Transactions table'
            )
        seen_receipt_ids.add(rid)
        seen_receipt_tx_ids.add(transaction_id)
        receipt_objs.append(
            Receipt(
                id=rid,
                version=1,
                user=user,
                transaction_id=transaction_id,
                date=d,
                total=total,
            )
        )

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

    payment_objs: list[Payment] = []
    seen_payment_ids: set[uuid.UUID] = set()
    seen_payment_rows: set[int] = set()
    for i, row in enumerate(source.get('payments', [])):
        payment_id, row_number, transaction_id, source_name, amount = _parse_payment_row(row, i)
        if payment_id in seen_payment_ids:
            raise SyncError(f'Payment row {i + 1}: duplicate Payment ID {payment_id}')
        if row_number in seen_payment_rows:
            raise SyncError(f'Payment row {i + 1}: duplicate sheet row_number {row_number}')
        if transaction_id not in seen_tx_ids:
            raise SyncError(
                f'Payment row {i + 1}: Transaction ID {transaction_id} not found'
            )
        if source_name not in source_by_name:
            raise SyncError(
                f'Payment row {i + 1}: Source {source_name!r} not found '
                f'(add it to Sources first)'
            )
        seen_payment_ids.add(payment_id)
        seen_payment_rows.add(row_number)
        payment_objs.append(
            Payment(
                id=payment_id,
                version=1,
                user=user,
                transaction_id=transaction_id,
                source_id=source_by_name[source_name],
                amount=abs(amount),
                row_number=row_number,
            )
        )

    giftcard_payment_objs: list[GiftcardPayment] = []
    seen_gcp_ids: set[uuid.UUID] = set()
    seen_gcp_rows: set[int] = set()
    for i, row in enumerate(source.get('giftcard_payments', [])):
        (
            giftcard_payment_id,
            row_number,
            transaction_id,
            giftcard_id,
            amount,
        ) = _parse_giftcard_payment_row(row, i)
        if giftcard_payment_id in seen_gcp_ids:
            raise SyncError(
                f'Giftcard payment row {i + 1}: duplicate Giftcard Payment ID {giftcard_payment_id}'
            )
        if row_number in seen_gcp_rows:
            raise SyncError(
                f'Giftcard payment row {i + 1}: duplicate sheet row_number {row_number}'
            )
        if transaction_id not in seen_tx_ids:
            raise SyncError(
                f'Giftcard payment row {i + 1}: Transaction ID {transaction_id} not found'
            )
        if giftcard_id not in seen_giftcard_ids:
            raise SyncError(
                f'Giftcard payment row {i + 1}: Giftcard ID {giftcard_id} not found'
            )
        seen_gcp_ids.add(giftcard_payment_id)
        seen_gcp_rows.add(row_number)
        giftcard_payment_objs.append(
            GiftcardPayment(
                id=giftcard_payment_id,
                version=1,
                user=user,
                transaction_id=transaction_id,
                giftcard_id=giftcard_id,
                amount=abs(amount),
                row_number=row_number,
            )
        )

    funding_by_tx: dict[uuid.UUID, Decimal] = {}
    for payment in payment_objs:
        funding_by_tx[payment.transaction_id] = (
            funding_by_tx.get(payment.transaction_id, Decimal('0')) + abs(payment.amount)
        )
    for gp in giftcard_payment_objs:
        funding_by_tx[gp.transaction_id] = (
            funding_by_tx.get(gp.transaction_id, Decimal('0')) + abs(gp.amount)
        )
    for tx in tx_objs:
        expected = abs(tx.change)
        actual = funding_by_tx.get(tx.id, Decimal('0'))
        if abs(expected - actual) > Decimal('0.009'):
            raise SyncError(
                f'Transaction {tx.id}: funding ({actual}) must equal abs(change) ({expected})'
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
        pi_id, product_id, price, sheet_tx_id, receipt_item_id, end_date = (
            _parse_product_item_row(row, i)
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
                end_date=end_date,
            )
        )

    with db_transaction.atomic():
        ProductItem.objects.filter(user=user).delete()
        Product.objects.filter(user=user).delete()
        GiftcardPayment.objects.filter(user=user).delete()
        Payment.objects.filter(user=user).delete()
        ReceiptItem.objects.filter(user=user).delete()
        Receipt.objects.filter(user=user).delete()
        Transaction.objects.filter(user=user).delete()
        Giftcard.objects.filter(user=user).delete()
        Category.objects.filter(user=user).delete()
        Source.objects.filter(user=user).delete()
        Source.objects.bulk_create(source_objs)
        Category.objects.bulk_create(category_objs)
        Giftcard.objects.bulk_create(giftcard_objs)
        Transaction.objects.bulk_create(tx_objs)
        Receipt.objects.bulk_create(receipt_objs)
        ReceiptItem.objects.bulk_create(item_objs)
        Payment.objects.bulk_create(payment_objs)
        GiftcardPayment.objects.bulk_create(giftcard_payment_objs)
        Product.objects.bulk_create(product_objs)
        ProductItem.objects.bulk_create(product_item_objs)

    return {
        'ok': True,
        'inserted': {
            'transactions': len(tx_objs),
            'payment': len(payment_objs),
            'giftcard_payment': len(giftcard_payment_objs),
            'receipt': len(receipt_objs),
            'receipt_items': len(item_objs),
            'giftcards': len(giftcard_objs),
            'products': len(product_objs),
            'product_items': len(product_item_objs),
            'category': len(category_objs),
            'sources': len(source_objs),
        },
    }
