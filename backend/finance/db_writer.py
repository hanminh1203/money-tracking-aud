"""Dual-write finance rows to Postgres after successful Sheets appends."""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction as db_transaction

from finance.funding import validate_funding
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

logger = logging.getLogger(__name__)

RECEIPT_ITEM_NAMESPACE = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')


def receipt_item_id_for_row(
    *,
    item_id: Any = None,
    receipt_id: Any,
    name: str,
    amount: Any,
    unit: str,
    money: Any,
) -> uuid.UUID:
    """Resolve receipt item id from sheet value or deterministic fallback."""
    text = str(item_id or '').strip()
    if text:
        return uuid.UUID(text)
    key = f'{receipt_id}:{name}:{amount}:{unit}:{money}'
    return uuid.uuid5(RECEIPT_ITEM_NAMESPACE, key)


def _receipt_item_kwargs(
    *,
    owner: User,
    receipt_id: uuid.UUID,
    it: dict,
) -> dict:
    item_id = receipt_item_id_for_row(
        item_id=it.get('id'),
        receipt_id=receipt_id,
        name=str(it['name']),
        amount=it['amount'],
        unit=str(it['unit']),
        money=it['money'],
    )
    return {
        'id': item_id,
        'version': 1,
        'user': owner,
        'receipt_id': receipt_id,
        'name': str(it['name']),
        'amount': _dec(it['amount']),
        'unit': str(it['unit']),
        'money': _dec(it['money']),
    }


def _parse_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value or '').strip()
    if not text:
        raise ValueError('Date is required')
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
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


def _resolve_transaction_id(row: dict) -> uuid.UUID:
    tid = row.get('transaction_id') or row.get('id')
    if tid:
        return uuid.UUID(str(tid))
    return uuid.uuid4()


def _resolve_payment_id(row: dict) -> uuid.UUID:
    pid = row.get('payment_id') or row.get('id')
    if pid:
        return uuid.UUID(str(pid))
    return uuid.uuid4()


def _resolve_giftcard_payment_id(row: dict) -> uuid.UUID:
    gid = row.get('giftcard_payment_id') or row.get('id')
    if gid:
        return uuid.UUID(str(gid))
    return uuid.uuid4()


def _create_payments(
    *,
    owner: User,
    transaction_id: uuid.UUID,
    payments: list[dict],
    giftcard_payments: list[dict],
) -> None:
    Payment.objects.bulk_create(
        [
            Payment(
                id=_resolve_payment_id(row),
                version=1,
                user=owner,
                transaction_id=transaction_id,
                source_id=_resolve_source_id(row.get('source') or ''),
                amount=abs(_dec(row['amount'])),
                row_number=int(row['row_number']),
            )
            for row in payments
        ]
    )
    GiftcardPayment.objects.bulk_create(
        [
            GiftcardPayment(
                id=_resolve_giftcard_payment_id(row),
                version=1,
                user=owner,
                transaction_id=transaction_id,
                giftcard_id=uuid.UUID(str(row['giftcard_id'])),
                amount=abs(_dec(row['amount'])),
                row_number=int(row['row_number']),
            )
            for row in giftcard_payments
        ]
    )


def save_transaction_bundle(
    *,
    user: User,
    date: Any,
    change: Any,
    row_number: int,
    transaction_id: Any = None,
    comment: str = '',
    sub_category: str = '',
    receipt_id: Any = None,
    payments: list[dict] | None = None,
    giftcard_payments: list[dict] | None = None,
) -> None:
    """Insert one Transaction with Payment and/or GiftcardPayment rows."""
    owner = _require_user(user)
    payment_rows = list(payments or [])
    giftcard_rows = list(giftcard_payments or [])
    signed_change = _dec(change)
    validate_funding(signed_change, payment_rows, giftcard_rows)
    tid = _resolve_transaction_id({'transaction_id': transaction_id})
    try:
        with db_transaction.atomic():
            Transaction.objects.create(
                id=tid,
                version=1,
                user=owner,
                row_number=int(row_number),
                date=_parse_date(date),
                change=signed_change,
                comment=str(comment or ''),
                category_id=_resolve_category_id(sub_category or ''),
                receipt_id=uuid.UUID(str(receipt_id)) if receipt_id else None,
            )
            _create_payments(
                owner=owner,
                transaction_id=tid,
                payments=payment_rows,
                giftcard_payments=giftcard_rows,
            )
    except Exception:
        logger.exception('Postgres dual-write failed for transaction bundle %s', tid)


def save_transactions(
    rows: list[dict],
    *,
    user: User,
) -> None:
    """Insert multiple transaction bundles (e.g. transfers)."""
    for row in rows:
        save_transaction_bundle(
            user=user,
            date=row['date'],
            change=row['change'],
            row_number=int(row['row_number']),
            transaction_id=row.get('transaction_id'),
            comment=str(row.get('comment') or ''),
            sub_category=str(row.get('sub_category') or ''),
            receipt_id=row.get('receipt_id'),
            payments=row.get('payments') or [],
            giftcard_payments=row.get('giftcard_payments') or [],
        )


def save_transaction(
    *,
    user: User,
    date: Any,
    change: Any,
    row_number: int,
    transaction_id: Any = None,
    comment: str = '',
    sub_category: str = '',
    receipt_id: Any = None,
    payments: list[dict] | None = None,
    giftcard_payments: list[dict] | None = None,
    source: str | None = None,
    amount: Any = None,
) -> None:
    """Backward-compatible wrapper when callers pass a single source."""
    payment_rows = list(payments or [])
    giftcard_rows = list(giftcard_payments or [])
    if not payment_rows and not giftcard_rows and source:
        payment_rows = [{'source': source, 'amount': abs(_dec(amount or change)), 'row_number': row_number}]
    save_transaction_bundle(
        user=user,
        date=date,
        change=change,
        row_number=row_number,
        transaction_id=transaction_id,
        comment=comment,
        sub_category=sub_category,
        receipt_id=receipt_id,
        payments=payment_rows,
        giftcard_payments=giftcard_rows,
    )


def save_receipt_bundle(
    *,
    user: User,
    receipt_id: Any,
    date: Any,
    total: Any,
    items: list[dict],
    transaction: dict,
    payments: list[dict],
    giftcard_payments: list[dict] | None = None,
) -> None:
    """Insert Receipt + ReceiptItems + one linked Transaction with funding rows."""
    owner = _require_user(user)
    try:
        rid = uuid.UUID(str(receipt_id))
        signed_total = -abs(_dec(total))
        validate_funding(signed_total, payments, giftcard_payments)
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
                    ReceiptItem(**_receipt_item_kwargs(owner=owner, receipt_id=rid, it=it))
                    for it in items
                ]
            )
            tid = _resolve_transaction_id(transaction)
            Transaction.objects.create(
                id=tid,
                version=1,
                user=owner,
                row_number=int(transaction['row_number']),
                date=_parse_date(transaction.get('date', date)),
                change=signed_total,
                comment=str(transaction.get('comment') or ''),
                category_id=_resolve_category_id(transaction.get('sub_category') or ''),
                receipt_id=rid,
            )
            _create_payments(
                owner=owner,
                transaction_id=tid,
                payments=payments,
                giftcard_payments=list(giftcard_payments or []),
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
    transaction: dict,
    payment: dict,
) -> None:
    """Insert Giftcard + buy Transaction with one Payment."""
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
            tid = _resolve_transaction_id(transaction)
            signed_change = _dec(transaction['change'])
            validate_funding(signed_change, [payment], [])
            Transaction.objects.create(
                id=tid,
                version=1,
                user=owner,
                row_number=int(transaction['row_number']),
                date=_parse_date(transaction.get('date', date)),
                change=signed_change,
                comment=str(transaction.get('comment') or ''),
                category_id=_resolve_category_id(transaction.get('sub_category') or ''),
            )
            _create_payments(
                owner=owner,
                transaction_id=tid,
                payments=[payment],
                giftcard_payments=[],
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
    transaction_id: Any = None,
    giftcard_payment: dict,
) -> None:
    """Insert use Transaction with GiftcardPayment and update Giftcard.balance."""
    owner = _require_user(user)
    try:
        gid = uuid.UUID(str(giftcard_id))
        signed_change = _dec(change)
        validate_funding(signed_change, [], [giftcard_payment])
        with db_transaction.atomic():
            updated = Giftcard.objects.filter(pk=gid, user=owner).update(
                balance=_dec(new_balance)
            )
            if not updated:
                raise ValueError(f'Giftcard {gid} not found')
            tid = _resolve_transaction_id({'transaction_id': transaction_id})
            Transaction.objects.create(
                id=tid,
                version=1,
                user=owner,
                row_number=int(row_number),
                date=_parse_date(date),
                change=signed_change,
                comment=str(comment or ''),
                category_id=_resolve_category_id(sub_category or ''),
            )
            _create_payments(
                owner=owner,
                transaction_id=tid,
                payments=[],
                giftcard_payments=[giftcard_payment],
            )
    except Exception:
        logger.exception('Postgres dual-write failed for giftcard use %s', giftcard_id)


def update_transaction_detail(
    *,
    user: User,
    transaction: Transaction,
    date: Any,
    change: Any,
    comment: str,
    sub_category: str,
    payments: list[dict],
    giftcard_payments: list[dict] | None = None,
    receipt_total: Any | None = None,
    items: list[dict] | None = None,
) -> None:
    """Update a transaction and replace funding rows after Sheets writes succeed."""
    owner = _require_user(user)
    payment_rows = list(payments or [])
    giftcard_rows = list(giftcard_payments or [])
    signed_change = _dec(change)
    validate_funding(signed_change, payment_rows, giftcard_rows)
    try:
        with db_transaction.atomic():
            transaction.date = _parse_date(date)
            transaction.change = signed_change
            transaction.comment = str(comment or '')
            transaction.category_id = _resolve_category_id(sub_category or '')
            transaction.version = (transaction.version or 1) + 1
            transaction.save(
                update_fields=[
                    'date',
                    'change',
                    'comment',
                    'category_id',
                    'version',
                ]
            )

            Payment.objects.filter(transaction=transaction, user=owner).delete()
            GiftcardPayment.objects.filter(transaction=transaction, user=owner).delete()
            _create_payments(
                owner=owner,
                transaction_id=transaction.id,
                payments=payment_rows,
                giftcard_payments=giftcard_rows,
            )

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
                                **_receipt_item_kwargs(
                                    owner=owner,
                                    receipt_id=receipt.id,
                                    it=it,
                                )
                            )
                            for it in items
                        ]
                    )
    except Exception:
        logger.exception(
            'Postgres dual-write failed for transaction update %s', transaction.id
        )
        raise


def save_product(*, user: User, product_id: Any, name: str) -> None:
    owner = _require_user(user)
    try:
        Product.objects.create(
            id=uuid.UUID(str(product_id)),
            version=1,
            user=owner,
            name=str(name).strip(),
        )
    except Exception:
        logger.exception('Postgres dual-write failed for product %s', product_id)


def update_product(*, user: User, product_id: Any, name: str) -> None:
    owner = _require_user(user)
    try:
        product = Product.objects.get(pk=product_id, user=owner)
        product.name = str(name).strip()
        product.version = (product.version or 1) + 1
        product.save(update_fields=['name', 'version'])
    except Product.DoesNotExist as exc:
        raise ValueError(f'Product {product_id} not found') from exc
    except Exception:
        logger.exception('Postgres dual-write failed for product update %s', product_id)
        raise


def delete_product(*, user: User, product_id: Any) -> None:
    owner = _require_user(user)
    try:
        Product.objects.filter(pk=product_id, user=owner).delete()
    except Exception:
        logger.exception('Postgres dual-write failed for product delete %s', product_id)


def save_product_item(
    *,
    user: User,
    product_item_id: Any,
    product_id: Any,
    price: Any | None = None,
    transaction_id: Any | None = None,
    receipt_item_id: Any | None = None,
) -> None:
    owner = _require_user(user)
    try:
        tx_id = uuid.UUID(str(transaction_id)) if transaction_id else None
        ri_id = uuid.UUID(str(receipt_item_id)) if receipt_item_id else None
        if bool(tx_id) == bool(ri_id):
            raise ValueError('Product item must link to transaction or receipt item')
        ProductItem.objects.create(
            id=uuid.UUID(str(product_item_id)),
            version=1,
            user=owner,
            product_id=uuid.UUID(str(product_id)),
            transaction_id=tx_id,
            receipt_item_id=ri_id,
            price=_dec(price) if price is not None else None,
        )
    except Exception:
        logger.exception('Postgres dual-write failed for product item %s', product_item_id)
        raise


def delete_product_item(*, user: User, product_item_id: Any) -> None:
    owner = _require_user(user)
    try:
        ProductItem.objects.filter(pk=product_item_id, user=owner).delete()
    except Exception:
        logger.exception('Postgres dual-write failed for product item delete %s', product_item_id)
