"""Read finance rows from Postgres for API list/get endpoints."""

from __future__ import annotations

from decimal import Decimal

from finance.comment_parse import parse_store_comment
from finance.models import Receipt, Transaction

TRANSACTION_HEADERS = [
    'Date',
    'Change',
    'Source',
    'Comment',
    'Sub category',
    'Receipt ID',
]


class ReaderError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _dec_to_number(value: Decimal) -> float:
    return float(value)


def get_transaction_data() -> dict:
    """Return sheet-shaped transaction rows from Postgres (no Main Category/Type)."""
    qs = Transaction.objects.select_related('source', 'category', 'receipt').order_by(
        '-date', '-creation_date'
    )
    rows = []
    for tx in qs.iterator():
        rows.append(
            {
                'Date': tx.date.isoformat(),
                'Change': _dec_to_number(tx.change),
                'Source': tx.source.name if tx.source_id else '',
                'Comment': tx.comment,
                'Sub category': tx.category.sub_category if tx.category_id else '',
                'Receipt ID': str(tx.receipt_id) if tx.receipt_id else None,
                'Creation Date': tx.creation_date.isoformat() if tx.creation_date else None,
                '__row': tx.row_number,
            }
        )
    return {'headers': list(TRANSACTION_HEADERS), 'rows': rows}


def get_receipt(receipt_id: str) -> dict:
    """Return receipt detail in the same shape as the former Sheets get_receipt."""
    rid = str(receipt_id or '').strip()
    if not rid:
        raise ReaderError('Receipt ID is required', status=400)

    try:
        receipt = Receipt.objects.prefetch_related(
            'items',
            'transactions__source',
            'transactions__category',
        ).get(pk=rid)
    except (Receipt.DoesNotExist, ValueError) as exc:
        raise ReaderError('Receipt not found', status=404) from exc

    items = [
        {
            'name': it.name,
            'amount': _dec_to_number(it.amount),
            'unit': it.unit,
            'money': _dec_to_number(it.money),
        }
        for it in receipt.items.all()
    ]

    sources = []
    store = ''
    comment = ''
    sub_category = ''
    for tx in receipt.transactions.all():
        sources.append(
            {
                'source': tx.source.name if tx.source_id else '',
                'amount': abs(_dec_to_number(tx.change)),
            }
        )
        if not sub_category and tx.category_id:
            sub_category = (tx.category.sub_category or '').strip()
        if not store and not comment:
            store, comment = parse_store_comment(tx.comment or '')

    return {
        'receiptId': rid,
        'date': receipt.date.isoformat(),
        'store': store,
        'subCategory': sub_category,
        'comment': comment,
        'total': _dec_to_number(receipt.total),
        'sources': sources,
        'items': items,
    }
