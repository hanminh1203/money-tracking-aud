"""Read finance rows from Postgres for API list/get endpoints."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db.models import Case, DecimalField, QuerySet, Sum, Value, When
from django.db.models.functions import TruncMonth
from django.utils import timezone

from finance.comment_parse import parse_store_comment
from finance.models import Category, Giftcard, Receipt, ReceiptItem, Source, Transaction, User

TRANSACTION_HEADERS = [
    'Date',
    'Change',
    'Source',
    'Comment',
    'Sub category',
    'Receipt ID',
    'Giftcard ID',
]

CATEGORY_EXPORT_COLUMNS = ['Main Category', 'Sub category', 'Type']
SOURCES_EXPORT_COLUMNS = ['Name', 'Type']
RECEIPT_EXPORT_COLUMNS = ['Receipt ID', 'Date', 'Total']
RECEIPT_ITEM_EXPORT_COLUMNS = ['Receipt ID', 'Name', 'Amount', 'Unit', 'Money']
GIFTCARD_EXPORT_COLUMNS = ['Giftcard ID', 'Shop', 'Date', 'Balance']

DEFAULT_PAGE_SIZE = 10


def _dec_cell(value: Decimal) -> str:
    """Format decimals as plain numeric strings for Sheets USER_ENTERED."""
    return format(value.normalize(), 'f')


class ReaderError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _dec_to_number(value: Decimal) -> float:
    return float(value)


def _tx_row(tx: Transaction) -> dict:
    return {
        'Date': tx.date.isoformat(),
        'Change': _dec_to_number(tx.change),
        'Source': tx.source.name if tx.source_id else '',
        'Comment': tx.comment,
        'Sub category': tx.category.sub_category if tx.category_id else '',
        'Receipt ID': str(tx.receipt_id) if tx.receipt_id else None,
        'Giftcard ID': str(tx.giftcard_id) if tx.giftcard_id else None,
        'Creation Date': tx.creation_date.isoformat() if tx.creation_date else None,
        '__row': tx.row_number,
    }


def _dashboard_tx_row(tx: Transaction) -> dict:
    """Return a transaction already shaped for the dashboard UI."""
    return {
        'row': tx.row_number,
        'date': tx.date.isoformat(),
        'creationDate': tx.creation_date.isoformat() if tx.creation_date else None,
        'change': _dec_to_number(tx.change),
        'source': tx.source.name,
        'comment': tx.comment,
        'subCategory': tx.category.sub_category if tx.category_id else '',
        'mainCategory': tx.category.main_category if tx.category_id else '',
        'type': tx.category.type if tx.category_id else '',
        'receiptId': str(tx.receipt_id) if tx.receipt_id else None,
    }


def _shift_month(value: date, offset: int) -> date:
    month_index = value.year * 12 + value.month - 1 + offset
    return date(month_index // 12, month_index % 12 + 1, 1)


def _base_queryset(*, user: User, source: str | None = None) -> QuerySet[Transaction]:
    qs = (
        Transaction.objects.filter(user=user)
        .select_related('source', 'category', 'receipt')
        .order_by('-date', '-creation_date')
    )
    name = (source or '').strip()
    if name:
        qs = qs.filter(source__name=name)
    return qs


def get_metadata() -> dict:
    """Return sources and categories in the same shape as Sheets get_metadata."""
    sources = [
        {'name': s.name, 'type': s.type or ''}
        for s in Source.objects.order_by('name')
    ]
    categories = [
        {
            'mainCategory': c.main_category,
            'subCategory': c.sub_category,
            'type': c.type or '',
        }
        for c in Category.objects.order_by('main_category', 'sub_category')
    ]
    return {'sources': sources, 'categories': categories}


def get_transaction_data(
    *,
    user: User,
    page: int | None = None,
    source: str | None = None,
) -> dict:
    """Return sheet-shaped transaction rows from Postgres (no Main Category/Type).

    Without page: all matching rows for pages that need a complete history.
    With page: LIMIT/OFFSET using backend DEFAULT_PAGE_SIZE, plus total count.
    """
    qs = _base_queryset(user=user, source=source)
    headers = list(TRANSACTION_HEADERS)

    if page is None:
        rows = [_tx_row(tx) for tx in qs.iterator()]
        return {'headers': headers, 'rows': rows}

    page = max(1, int(page))
    size = DEFAULT_PAGE_SIZE
    total = qs.count()
    total_pages = max(1, (total + size - 1) // size) if total else 1
    if page > total_pages:
        page = total_pages
    offset = (page - 1) * size
    rows = [_tx_row(tx) for tx in qs[offset : offset + size]]
    return {
        'headers': headers,
        'rows': rows,
        'page': page,
        'pageSize': size,
        'total': total,
        'totalPages': total_pages,
    }


def get_dashboard_data(*, user: User) -> dict:
    """Return all dashboard metrics, breakdowns, and current-month rows."""
    current_month = timezone.localdate().replace(day=1)
    first_month = _shift_month(current_month, -2)
    next_month = _shift_month(current_month, 1)
    month_dates = [_shift_month(first_month, offset) for offset in range(3)]
    months = [f'{value.year}/{value.month:02d}' for value in month_dates]

    zero = Value(0, output_field=DecimalField(max_digits=14, decimal_places=2))
    user_txs = Transaction.objects.filter(user=user)
    current_qs = user_txs.filter(
        date__gte=current_month,
        date__lt=next_month,
    )
    totals = current_qs.aggregate(
        income=Sum(
            Case(
                When(category__type='Income', then='change'),
                default=zero,
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        ),
        expense=Sum(
            Case(
                When(category__type='Expense', then='change'),
                default=zero,
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        ),
    )
    income = totals['income'] or Decimal('0')
    expense = totals['expense'] or Decimal('0')
    net_worth = user_txs.aggregate(total=Sum('change'))['total'] or Decimal('0')

    breakdown_rows = (
        user_txs.filter(
            date__gte=first_month,
            date__lt=next_month,
            category__type__in=('Income', 'Expense'),
        )
        .annotate(month=TruncMonth('date'))
        .values('category__type', 'category__sub_category', 'month')
        .annotate(amount=Sum('change'))
        .order_by('category__type', 'category__sub_category', 'month')
    )

    breakdown = {'Income': {}, 'Expense': {}}
    for row in breakdown_rows:
        category_type = row['category__type']
        sub_category = row['category__sub_category']
        month_date = row['month']
        if category_type not in breakdown or not sub_category or month_date is None:
            continue
        values = breakdown[category_type].setdefault(
            sub_category,
            {month: 0.0 for month in months},
        )
        month_key = f'{month_date.year}/{month_date.month:02d}'
        values[month_key] = _dec_to_number(row['amount'] or Decimal('0'))

    def pivot_rows(category_type: str) -> list[dict]:
        return [
            {'subCategory': name, 'amounts': values}
            for name, values in sorted(breakdown[category_type].items())
        ]

    transactions = [
        _dashboard_tx_row(tx)
        for tx in current_qs.select_related('source', 'category', 'receipt').order_by(
            '-date', '-creation_date'
        )
    ]

    return {
        'summary': {
            'netWorth': _dec_to_number(net_worth),
            'income': _dec_to_number(income),
            'expense': _dec_to_number(expense),
            'saving': _dec_to_number(income + expense),
        },
        'months': months,
        'incomeBreakdown': pivot_rows('Income'),
        'expenseBreakdown': pivot_rows('Expense'),
        'transactions': transactions,
    }


def get_receipt(*, user: User, receipt_id: str) -> dict:
    """Return receipt detail in the same shape as the former Sheets get_receipt."""
    rid = str(receipt_id or '').strip()
    if not rid:
        raise ReaderError('Receipt ID is required', status=400)

    try:
        receipt = (
            Receipt.objects.filter(user=user)
            .prefetch_related(
                'items',
                'transactions__source',
                'transactions__category',
            )
            .get(pk=rid)
        )
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


def get_giftcards(*, user: User) -> list[dict]:
    """Return giftcards with balance > 0, ordered by date desc then shop asc."""
    return [
        {
            'id': str(g.id),
            'shop': g.shop,
            'date': g.date.isoformat(),
            'balance': _dec_to_number(g.balance),
        }
        for g in Giftcard.objects.filter(user=user, balance__gt=0).order_by('-date', 'shop')
    ]


def get_export_payload(*, user: User) -> dict[str, dict]:
    """Return sheet-shaped value matrices for a full workbook export.

    Keys match management count labels. Each entry has:
    ``columns`` (header names) and ``rows`` (list of cell lists, no header row).
    """
    transactions = [
        [
            tx.date.isoformat(),
            _dec_cell(tx.change),
            tx.source.name if tx.source_id else '',
            tx.comment or '',
            tx.category.sub_category if tx.category_id else '',
            str(tx.receipt_id) if tx.receipt_id else '',
            str(tx.giftcard_id) if tx.giftcard_id else '',
        ]
        for tx in Transaction.objects.filter(user=user)
        .select_related('source', 'category')
        .order_by('row_number')
        .iterator()
    ]

    giftcards = [
        [
            str(g.id),
            g.shop or '',
            g.date.isoformat(),
            _dec_cell(g.balance),
        ]
        for g in Giftcard.objects.filter(user=user).order_by('row_number').iterator()
    ]

    receipts = [
        [str(r.id), r.date.isoformat(), _dec_cell(r.total)]
        for r in Receipt.objects.filter(user=user).order_by('id').iterator()
    ]

    receipt_items = [
        [
            str(it.receipt_id),
            it.name or '',
            _dec_cell(it.amount),
            it.unit or '',
            _dec_cell(it.money),
        ]
        for it in ReceiptItem.objects.filter(user=user)
        .order_by('receipt_id', 'id')
        .iterator()
    ]

    categories = [
        [c.main_category or '', c.sub_category or '', c.type or '']
        for c in Category.objects.order_by('main_category', 'sub_category').iterator()
    ]

    sources = [
        [s.name or '', s.type or '']
        for s in Source.objects.order_by('name').iterator()
    ]

    return {
        'transactions': {
            'table_name': settings.TRANSACTIONS_TABLE,
            'columns': list(TRANSACTION_HEADERS),
            'rows': transactions,
        },
        'giftcards': {
            'table_name': settings.GIFTCARD_TABLE,
            'columns': list(GIFTCARD_EXPORT_COLUMNS),
            'rows': giftcards,
        },
        'receipt': {
            'table_name': settings.RECEIPT_TABLE,
            'columns': list(RECEIPT_EXPORT_COLUMNS),
            'rows': receipts,
        },
        'receipt_items': {
            'table_name': settings.RECEIPT_ITEMS_TABLE,
            'columns': list(RECEIPT_ITEM_EXPORT_COLUMNS),
            'rows': receipt_items,
        },
        'category': {
            'table_name': settings.CATEGORY_TABLE,
            'columns': list(CATEGORY_EXPORT_COLUMNS),
            'rows': categories,
        },
        'sources': {
            'table_name': settings.SOURCES_TABLE,
            'columns': list(SOURCES_EXPORT_COLUMNS),
            'rows': sources,
        },
    }
