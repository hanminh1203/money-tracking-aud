"""Read finance rows from Postgres for API list/get endpoints."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Case, DecimalField, Q, QuerySet, Sum, Value, When
from django.db.models.functions import TruncMonth
from django.utils import timezone

from finance.comment_parse import parse_store_comment
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
RECEIPT_ITEM_EXPORT_COLUMNS = [
    'Receipt Item ID',
    'Receipt ID',
    'Name',
    'Amount',
    'Unit',
    'Money',
]
GIFTCARD_EXPORT_COLUMNS = ['Giftcard ID', 'Shop', 'Date', 'Balance']
PRODUCT_EXPORT_COLUMNS = ['Product ID', 'Name']
PRODUCT_ITEM_EXPORT_COLUMNS = [
    'Product Item ID',
    'Product ID',
    'Price',
    'Transaction Row',
    'Receipt Item ID',
]

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
        'id': str(tx.id),
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
        'id': str(tx.id),
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
        'giftcardId': str(tx.giftcard_id) if tx.giftcard_id else None,
    }


def _receipt_items(receipt: Receipt, *, user: User | None = None) -> list[dict]:
    product_by_receipt_item: dict[str, dict] = {}
    if user is not None:
        for pi in (
            ProductItem.objects.filter(user=user, receipt_item__receipt=receipt)
            .select_related('product', 'receipt_item')
            .iterator()
        ):
            product_by_receipt_item[str(pi.receipt_item_id)] = {
                'productItemId': str(pi.id),
                'productId': str(pi.product_id),
                'productName': pi.product.name,
            }

    items = sorted(
        receipt.items.all(),
        key=lambda it: (
            it.creation_date.isoformat() if it.creation_date else '',
            str(it.id),
        ),
    )
    return [
        {
            'id': str(it.id),
            'name': it.name,
            'amount': _dec_to_number(it.amount),
            'unit': it.unit,
            'money': _dec_to_number(it.money),
            **product_by_receipt_item.get(str(it.id), {}),
        }
        for it in items
    ]


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

    items = _receipt_items(receipt, user=user)

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


def get_transaction(*, user: User, transaction_id: str) -> dict:
    """Return one user-owned transaction, with nested receipt items when linked."""
    tid = str(transaction_id or '').strip()
    if not tid:
        raise ReaderError('Transaction ID is required', status=400)

    try:
        tx = (
            Transaction.objects.filter(user=user)
            .select_related('source', 'category', 'receipt')
            .prefetch_related('receipt__items', 'receipt__transactions__source')
            .get(pk=tid)
        )
    except (Transaction.DoesNotExist, ValueError, ValidationError) as exc:
        raise ReaderError('Transaction not found', status=404) from exc

    data = _dashboard_tx_row(tx)
    if tx.receipt_id and tx.receipt:
        data['receipt'] = {
            'receiptId': str(tx.receipt.id),
            'date': tx.receipt.date.isoformat(),
            'total': _dec_to_number(tx.receipt.total),
            'sources': [
                {
                    'transactionId': str(linked.id),
                    'source': linked.source.name if linked.source_id else '',
                    'amount': abs(_dec_to_number(linked.change)),
                }
                for linked in tx.receipt.transactions.all()
            ],
            'items': _receipt_items(tx.receipt, user=user),
        }
    else:
        data['receipt'] = None

    data['products'] = [
        {
            'id': str(pi.id),
            'productId': str(pi.product_id),
            'name': pi.product.name,
            'price': _dec_to_number(pi.price) if pi.price is not None else None,
        }
        for pi in ProductItem.objects.filter(user=user, transaction_id=tx.id)
        .select_related('product')
        .order_by('creation_date')
    ]
    return data


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


def _resolved_product_item_price(pi: ProductItem) -> Decimal:
    if pi.price is not None:
        return pi.price
    if pi.receipt_item_id and pi.receipt_item:
        return pi.receipt_item.money
    if pi.transaction_id and pi.transaction:
        return abs(pi.transaction.change)
    return Decimal('0')


def _product_item_purchase_date(pi: ProductItem) -> date | None:
    if pi.transaction_id and pi.transaction:
        return pi.transaction.date
    if pi.receipt_item_id and pi.receipt_item:
        return pi.receipt_item.receipt.date
    return None


def _product_item_label(pi: ProductItem) -> str:
    if pi.transaction_id and pi.transaction:
        store, comment = parse_store_comment(pi.transaction.comment or '')
        parts = [p for p in (store, pi.transaction.source.name if pi.transaction.source_id else '', comment) if p]
        return ' · '.join(parts) if parts else 'Transaction'
    if pi.receipt_item_id and pi.receipt_item:
        return pi.receipt_item.name
    return ''


def _product_item_row(pi: ProductItem) -> dict:
    purchase_date = _product_item_purchase_date(pi)
    row = {
        'id': str(pi.id),
        'date': purchase_date.isoformat() if purchase_date else None,
        'price': _dec_to_number(_resolved_product_item_price(pi)),
        'label': _product_item_label(pi),
    }
    if pi.transaction_id:
        row['linkType'] = 'transaction'
        row['transactionId'] = str(pi.transaction_id)
    else:
        row['linkType'] = 'receipt_item'
        row['receiptItemId'] = str(pi.receipt_item_id)
        row['receiptId'] = str(pi.receipt_item.receipt_id) if pi.receipt_item_id else None
    return row


def _product_stats(items: list[ProductItem]) -> dict:
    dated = []
    for pi in items:
        d = _product_item_purchase_date(pi)
        if d is not None:
            dated.append((d, _resolved_product_item_price(pi)))
    dated.sort(key=lambda x: x[0])

    total_purchases = len(dated)
    total_spent = sum((price for _, price in dated), Decimal('0'))
    last_purchase_date = dated[-1][0].isoformat() if dated else None

    cost_per_day = None
    avg_days_between = None
    if dated:
        last_date, last_price = dated[-1]
        days_owned = max((timezone.localdate() - last_date).days, 1)
        cost_per_day = _dec_to_number(last_price / Decimal(days_owned))
    if len(dated) >= 2:
        gaps = [(dated[i][0] - dated[i - 1][0]).days for i in range(1, len(dated))]
        avg_days_between = round(sum(gaps) / len(gaps), 1)

    return {
        'costPerDay': cost_per_day,
        'avgDaysBetweenPurchases': avg_days_between,
        'totalPurchases': total_purchases,
        'lastPurchaseDate': last_purchase_date,
        'totalSpent': _dec_to_number(total_spent),
    }


def get_products(*, user: User) -> list[dict]:
    products = Product.objects.filter(user=user).order_by('name', 'id')
    rows = []
    for product in products:
        items = list(
            ProductItem.objects.filter(user=user, product=product)
            .select_related('transaction', 'receipt_item__receipt')
        )
        stats = _product_stats(items)
        rows.append(
            {
                'id': str(product.id),
                'name': product.name,
                'purchaseCount': stats['totalPurchases'],
                'lastPurchaseDate': stats['lastPurchaseDate'],
                'costPerDay': stats['costPerDay'],
            }
        )
    return rows


def get_product_detail(*, user: User, product_id: str) -> dict:
    pid = str(product_id or '').strip()
    if not pid:
        raise ReaderError('Product ID is required', status=400)
    try:
        product = Product.objects.get(pk=pid, user=user)
    except (Product.DoesNotExist, ValueError) as exc:
        raise ReaderError('Product not found', status=404) from exc

    items = list(
        ProductItem.objects.filter(user=user, product=product)
        .select_related(
            'transaction__source',
            'receipt_item__receipt',
        )
        .order_by('-transaction__date', '-receipt_item__receipt__date', '-creation_date')
    )
    items.sort(
        key=lambda pi: _product_item_purchase_date(pi) or date.min,
        reverse=True,
    )
    stats = _product_stats(items)
    return {
        'id': str(product.id),
        'name': product.name,
        'stats': stats,
        'purchases': [_product_item_row(pi) for pi in items],
    }


def search_link_candidates(
    *,
    user: User,
    product_id: str,
    link_type: str,
    q: str = '',
    page: int = 1,
) -> dict:
    pid = str(product_id or '').strip()
    if not pid:
        raise ReaderError('Product ID is required', status=400)
    if not Product.objects.filter(pk=pid, user=user).exists():
        raise ReaderError('Product not found', status=404)

    page = max(1, int(page))
    size = DEFAULT_PAGE_SIZE
    query = (q or '').strip().lower()

    if link_type == 'transaction':
        linked_ids = set(
            ProductItem.objects.filter(user=user, product_id=pid, transaction_id__isnull=False)
            .values_list('transaction_id', flat=True)
        )
        qs = (
            Transaction.objects.filter(user=user)
            .exclude(id__in=linked_ids)
            .select_related('source', 'category')
            .order_by('-date', '-creation_date')
        )
        if query:
            qs = qs.filter(
                Q(comment__icontains=query)
                | Q(source__name__icontains=query)
                | Q(category__sub_category__icontains=query)
            )
        total = qs.count()
        total_pages = max(1, (total + size - 1) // size) if total else 1
        if page > total_pages:
            page = total_pages
        offset = (page - 1) * size
        rows = []
        for tx in qs[offset : offset + size]:
            store, comment = parse_store_comment(tx.comment or '')
            label = ' · '.join(
                p for p in (store, tx.source.name if tx.source_id else '', comment) if p
            )
            rows.append(
                {
                    'id': str(tx.id),
                    'date': tx.date.isoformat(),
                    'amount': abs(_dec_to_number(tx.change)),
                    'label': label or 'Transaction',
                }
            )
        return {
            'type': 'transaction',
            'rows': rows,
            'page': page,
            'pageSize': size,
            'total': total,
            'totalPages': total_pages,
        }

    if link_type == 'receipt_item':
        linked_ids = set(
            ProductItem.objects.filter(user=user, product_id=pid, receipt_item_id__isnull=False)
            .values_list('receipt_item_id', flat=True)
        )
        qs = (
            ReceiptItem.objects.filter(user=user)
            .exclude(id__in=linked_ids)
            .select_related('receipt')
            .order_by('-receipt__date', 'name')
        )
        if query:
            qs = qs.filter(name__icontains=query)
        total = qs.count()
        total_pages = max(1, (total + size - 1) // size) if total else 1
        if page > total_pages:
            page = total_pages
        offset = (page - 1) * size
        rows = [
            {
                'id': str(it.id),
                'receiptId': str(it.receipt_id),
                'date': it.receipt.date.isoformat(),
                'amount': _dec_to_number(it.money),
                'label': it.name,
            }
            for it in qs[offset : offset + size]
        ]
        return {
            'type': 'receipt_item',
            'rows': rows,
            'page': page,
            'pageSize': size,
            'total': total,
            'totalPages': total_pages,
        }

    raise ReaderError('type must be transaction or receipt_item', status=400)


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
            str(it.id),
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

    products = [
        [str(p.id), p.name or '']
        for p in Product.objects.filter(user=user).order_by('name', 'id').iterator()
    ]

    product_items = [
        [
            str(pi.id),
            str(pi.product_id),
            _dec_cell(pi.price) if pi.price is not None else '',
            str(pi.transaction.row_number) if pi.transaction_id else '',
            str(pi.receipt_item_id) if pi.receipt_item_id else '',
        ]
        for pi in ProductItem.objects.filter(user=user)
        .select_related('transaction')
        .order_by('product_id', 'creation_date')
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
        'products': {
            'table_name': settings.PRODUCT_TABLE,
            'columns': list(PRODUCT_EXPORT_COLUMNS),
            'rows': products,
        },
        'product_items': {
            'table_name': settings.PRODUCT_ITEMS_TABLE,
            'columns': list(PRODUCT_ITEM_EXPORT_COLUMNS),
            'rows': product_items,
        },
    }
