"""Copy a transaction subcategory onto receipt items that do not have one.

The Google Sheet is written first, then Postgres. Re-running is safe: a
Receipt_Items cell that already has a subcategory is left as it is. If that
cell was written and Postgres was not, the next run copies the sheet value
into Postgres and does not append a new row.
"""

from __future__ import annotations

import uuid

from django.conf import settings

from finance.db_sync import _parse_item_row, _parse_receipt_row, _parse_tx_row
from finance.models import Category, ReceiptItem, Transaction, User
from finance.sheets_client import SUB_CATEGORY_COLUMN, SheetsClient, SheetsError


class ItemSubcategoryBackfillError(Exception):
    """A sheet or database write failed after some cells may already be filled."""

    status = 500

    def __init__(self, message: str, summary: dict):
        super().__init__(message)
        self.summary = summary


def _empty_summary(*, dry_run: bool) -> dict:
    return {
        'dry_run': bool(dry_run),
        'updated': 0,
        'repaired_from_sheet': 0,
        'skipped_already_set': 0,
        'skipped_blank_transaction': 0,
        'skipped_unknown_category': 0,
        'skipped_orphan': 0,
        'skipped_not_on_sheet': 0,
        'failed': 0,
    }


def _require_column(client: SheetsClient) -> None:
    table = client.get_table(settings.RECEIPT_ITEMS_TABLE)
    names = [column['name'] for column in table.get('columns') or []]
    if SUB_CATEGORY_COLUMN not in names:
        raise SheetsError(
            'Receipt_Items is missing the "Sub category" column. '
            'Add it as column 7, immediately after Money, then run this again.'
        )


def _sheet_transactions(rows: list[dict]) -> dict[uuid.UUID, str]:
    indexed: dict[uuid.UUID, str] = {}
    for index, row in enumerate(rows or []):
        transaction_id, _row_number, _date, _change, _comment, sub_category = _parse_tx_row(
            row, index
        )
        indexed[transaction_id] = str(sub_category or '').strip()
    return indexed


def _sheet_receipt_transactions(rows: list[dict]) -> dict[uuid.UUID, uuid.UUID]:
    indexed: dict[uuid.UUID, uuid.UUID] = {}
    for index, row in enumerate(rows or []):
        receipt_id, transaction_id, _date, _total = _parse_receipt_row(row, index)
        indexed.setdefault(receipt_id, transaction_id)
    return indexed


def _chosen_subcategory(
    *,
    transaction_id: uuid.UUID,
    sheet_subs: dict[uuid.UUID, str],
    pg_transactions: dict[uuid.UUID, Transaction],
    categories: dict[str, uuid.UUID],
) -> tuple[str, uuid.UUID | None]:
    """Return ``(name, category id)`` or ``('', None)`` when it cannot be copied.

    The sheet transaction subcategory wins when it is a known category, so the
    item matches the transaction row in the spreadsheet. Otherwise the Postgres
    transaction subcategory is used.
    """
    sheet_sub = sheet_subs.get(transaction_id) or ''
    pg = pg_transactions.get(transaction_id)
    pg_sub = ''
    if pg is not None and pg.category_id:
        pg_sub = str(pg.category.sub_category or '').strip()
    if sheet_sub and sheet_sub in categories:
        return sheet_sub, categories[sheet_sub]
    if pg_sub and pg_sub in categories:
        return pg_sub, categories[pg_sub]
    if sheet_sub or pg_sub:
        return sheet_sub or pg_sub, None
    return '', None


def backfill_receipt_item_subcategories(
    *,
    user: User,
    client: SheetsClient,
    dry_run: bool = False,
) -> dict:
    """Fill blank Receipt_Items subcategories from their transaction.

    ``dry_run`` reads the sheet and reports counts without writing. A non-blank
    item subcategory is never overwritten. Postgres is updated only for this user.
    """
    _require_column(client)
    summary = _empty_summary(dry_run=dry_run)
    source = client.get_mirror_source_rows()
    sheet_subs = _sheet_transactions(source.get('transactions') or [])
    receipt_tx = _sheet_receipt_transactions(source.get('receipts') or [])
    categories = {
        category.sub_category: category.id
        for category in Category.objects.filter(user=user)
    }
    pg_transactions = {
        tx.id: tx
        for tx in Transaction.objects.filter(user=user).select_related('category')
    }
    pg_items = {
        item.id: item
        for item in ReceiptItem.objects.filter(user=user).select_related('category')
    }

    planned: list[dict] = []
    for index, row in enumerate(source.get('receipt_items') or []):
        item_id, receipt_id, _name, _amount, _unit, _money, item_sub = _parse_item_row(
            row, index
        )
        sheet_row = row.get('__sheet_row')
        pg_item = pg_items.get(item_id)
        current = ''
        if pg_item is not None and pg_item.category_id:
            current = str(pg_item.category.sub_category or '').strip()

        if item_sub:
            if pg_item is None or current == item_sub:
                summary['skipped_already_set'] += 1
                continue
            category_id = categories.get(item_sub)
            if category_id is None:
                summary['skipped_unknown_category'] += 1
                continue
            summary['repaired_from_sheet'] += 1
            planned.append(
                {
                    'kind': 'repair',
                    'item': pg_item,
                    'category_id': category_id,
                    'item_id': item_id,
                }
            )
            continue

        if sheet_row is None:
            summary['skipped_not_on_sheet'] += 1
            continue
        transaction_id = receipt_tx.get(receipt_id)
        if transaction_id is None:
            summary['skipped_orphan'] += 1
            continue
        chosen, category_id = _chosen_subcategory(
            transaction_id=transaction_id,
            sheet_subs=sheet_subs,
            pg_transactions=pg_transactions,
            categories=categories,
        )
        if category_id is None:
            if chosen:
                summary['skipped_unknown_category'] += 1
            else:
                summary['skipped_blank_transaction'] += 1
            continue
        if pg_item is not None and current == chosen:
            # Sheet cell is blank but Postgres already has the transaction
            # subcategory. Still write the sheet so a later Sync does not clear it.
            pass
        summary['updated'] += 1
        planned.append(
            {
                'kind': 'fill',
                'item': pg_item,
                'category_id': category_id,
                'sheet_row': int(sheet_row),
                'sub_category': chosen,
                'item_id': item_id,
            }
        )

    if dry_run:
        return summary

    filled = 0
    repaired = 0
    for step in planned:
        try:
            if step['kind'] == 'fill':
                client.update_table_cell_at_row(
                    settings.RECEIPT_ITEMS_TABLE,
                    sheet_row=step['sheet_row'],
                    update_column=SUB_CATEGORY_COLUMN,
                    new_value=step['sub_category'],
                )
            item = step['item']
            if item is not None and item.category_id != step['category_id']:
                item.category_id = step['category_id']
                item.version = (item.version or 1) + 1
                item.save(update_fields=['category_id', 'version'])
            if step['kind'] == 'fill':
                filled += 1
            else:
                repaired += 1
        except Exception as exc:
            summary['updated'] = filled
            summary['repaired_from_sheet'] = repaired
            summary['failed'] = 1
            summary['failed_item_id'] = str(step['item_id'])
            message = (
                f'{exc} Stopped at receipt item {step["item_id"]}. '
                'Run this backfill again. A cell already written on the sheet is copied '
                'into Postgres and is not overwritten.'
            )
            raise ItemSubcategoryBackfillError(message, summary) from exc

    return summary
