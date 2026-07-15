"""Read finance rows from Postgres for API list/get endpoints."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Case, DecimalField, F, QuerySet, Sum, Value, When
from django.db.models.functions import Abs, TruncMonth

from finance.comment_parse import parse_store_comment
from finance.models import Category, Receipt, Source, Transaction

TRANSACTION_HEADERS = [
    'Date',
    'Change',
    'Source',
    'Comment',
    'Sub category',
    'Receipt ID',
]

DEFAULT_PAGE_SIZE = 10


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
        'Creation Date': tx.creation_date.isoformat() if tx.creation_date else None,
        '__row': tx.row_number,
    }


def _base_queryset(*, source: str | None = None) -> QuerySet[Transaction]:
    qs = Transaction.objects.select_related('source', 'category', 'receipt').order_by(
        '-date', '-creation_date'
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
    page: int | None = None,
    source: str | None = None,
) -> dict:
    """Return sheet-shaped transaction rows from Postgres (no Main Category/Type).

    Without page: all matching rows (Dashboard / aggregates).
    With page: LIMIT/OFFSET using backend DEFAULT_PAGE_SIZE, plus total count.
    """
    qs = _base_queryset(source=source)
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


def get_income_expense_by_month() -> list[dict]:
    """Aggregate Income/Expense transactions by calendar month from Postgres.

    Returns [{ month: 'YYYY/MM', income, expense }, ...] sorted ascending.
    Expense sums are signed (typically negative). Transfers / uncategorized
    rows are excluded.
    """
    zero = Value(0, output_field=DecimalField(max_digits=14, decimal_places=2))
    rows = (
        Transaction.objects.filter(category__type__in=('Income', 'Expense'))
        .annotate(month=TruncMonth('date'))
        .values('month')
        .annotate(
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
        .order_by('month')
    )
    result = []
    for row in rows:
        month_date = row['month']
        if month_date is None:
            continue
        result.append(
            {
                'month': f'{month_date.year}/{month_date.month:02d}',
                'income': _dec_to_number(row['income'] or Decimal('0')),
                'expense': _dec_to_number(row['expense'] or Decimal('0')),
            }
        )
    return result


def get_spending_by_category(month: str = 'all') -> list[dict]:
    """Aggregate expense totals by main category for month='all' or 'YYYY/MM'.

    Returns [{ category, amount }, ...] sorted by amount descending.
    Amounts are absolute (positive). Uncategorized / non-Expense rows excluded.
    """
    month = (month or 'all').strip() or 'all'
    qs = Transaction.objects.filter(category__type='Expense')

    if month != 'all':
        parts = month.split('/')
        if len(parts) != 2:
            raise ReaderError('month must be "all" or YYYY/MM', status=400)
        try:
            year = int(parts[0])
            month_num = int(parts[1])
        except ValueError as exc:
            raise ReaderError('month must be "all" or YYYY/MM', status=400) from exc
        if year < 1 or month_num < 1 or month_num > 12:
            raise ReaderError('month must be "all" or YYYY/MM', status=400)
        qs = qs.filter(date__year=year, date__month=month_num)

    rows = (
        qs.values('category__main_category')
        .annotate(amount=Sum(Abs(F('change'))))
        .order_by('-amount')
    )
    result = []
    for row in rows:
        name = (row['category__main_category'] or '').strip() or 'Other'
        result.append(
            {
                'category': name,
                'amount': _dec_to_number(row['amount'] or Decimal('0')),
            }
        )
    return result


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
