"""Create missing one-line receipts on the sheet, then in Postgres.

Sheet rows are written first. A later Management Sync reloads Postgres from the
sheet, so a receipt that exists only in Postgres would be deleted. Re-running
this command is safe: transactions that already have a receipt are skipped, and
a receipt that reached the sheet but not Postgres is mirrored instead of
appended again.
"""

from __future__ import annotations

import uuid

from django.conf import settings

from finance.auto_receipt import (
    MISSING_DESCRIPTION,
    auto_receipt_sheet_rows,
    build_auto_receipt,
    money_amount,
    should_attach_auto_receipt,
)
from finance.db_sync import _parse_item_row, _parse_receipt_row, _parse_tx_row
from finance.db_writer import DualWriteError, save_receipt_for_existing_transaction
from finance.models import Receipt, Transaction, User
from finance.sheets_client import (
    RECEIPT_COLUMNS,
    RECEIPT_ITEM_COLUMNS,
    SheetsClient,
    SheetsError,
)


class BackfillWriteError(Exception):
    """A sheet or database write failed after some rows may already exist."""

    status = 500

    def __init__(self, message: str, summary: dict):
        super().__init__(message)
        self.summary = summary


def _empty_summary(*, dry_run: bool) -> dict:
    return {
        'dry_run': bool(dry_run),
        'created': 0,
        'repaired_from_sheet': 0,
        'placeholders': 0,
        'skipped_has_receipt': 0,
        'skipped_exchange': 0,
        'skipped_zero': 0,
        'skipped_not_on_sheet': 0,
        'skipped_sheet_duplicate': 0,
        'skipped_sheet_receipt_without_items': 0,
        'failed': 0,
    }


def _index_sheet(source: dict) -> tuple[dict[uuid.UUID, dict], dict[uuid.UUID, dict], set[uuid.UUID]]:
    transactions: dict[uuid.UUID, dict] = {}
    for index, row in enumerate(source.get('transactions') or []):
        transaction_id, row_number, tx_date, change, comment, sub_category = _parse_tx_row(
            row, index
        )
        transactions[transaction_id] = {
            'row_number': row_number,
            'date': tx_date,
            'change': change,
            'comment': comment,
            'sub_category': sub_category,
        }

    items_by_receipt: dict[uuid.UUID, list[dict]] = {}
    for index, row in enumerate(source.get('receipt_items') or []):
        item_id, receipt_id, name, amount, unit, money = _parse_item_row(row, index)
        items_by_receipt.setdefault(receipt_id, []).append(
            {
                'id': str(item_id),
                'name': name,
                'amount': amount,
                'unit': unit,
                'money': money,
            }
        )

    receipts: dict[uuid.UUID, dict] = {}
    duplicates: set[uuid.UUID] = set()
    for index, row in enumerate(source.get('receipts') or []):
        receipt_id, transaction_id, receipt_date, total = _parse_receipt_row(row, index)
        if transaction_id in receipts or transaction_id in duplicates:
            duplicates.add(transaction_id)
            receipts.pop(transaction_id, None)
            continue
        receipts[transaction_id] = {
            'receipt_id': str(receipt_id),
            'date': receipt_date.isoformat(),
            'total': total,
            'items': items_by_receipt.get(receipt_id, []),
        }
    return transactions, receipts, duplicates


def _fill_blank_sheet_comment(
    client: SheetsClient, sheet_tx: dict, chosen: str
) -> None:
    if str(sheet_tx.get('comment') or '').strip():
        return
    client.update_table_cell_at_row(
        settings.TRANSACTIONS_TABLE,
        sheet_row=int(sheet_tx['row_number']),
        update_column='Comment',
        new_value=chosen,
    )
    sheet_tx['comment'] = chosen


def _fail(summary: dict, transaction_id: uuid.UUID, exc: Exception) -> None:
    summary['failed'] = 1
    summary['failed_transaction_id'] = str(transaction_id)
    if isinstance(exc, DualWriteError):
        message = (
            f'{exc} Transaction {transaction_id} may already have receipt rows on the '
            'sheet. Run this backfill again to mirror them, or open Management and run Sync.'
        )
    else:
        message = f'{exc} Stopped at transaction {transaction_id}. Run the backfill again to continue.'
    raise BackfillWriteError(message, summary) from exc


def backfill_missing_receipts(
    *,
    user: User,
    client: SheetsClient,
    dry_run: bool = False,
) -> dict:
    """Add one receipt line for this user's transactions that do not have one.

    ``dry_run`` reads the sheet and reports counts without writing. Exchange
    (self) rows and zero-change rows are skipped. A blank description becomes
    ``(no description)`` on the sheet and in Postgres.
    """
    summary = _empty_summary(dry_run=dry_run)
    sheet_txs, sheet_receipts, duplicates = _index_sheet(client.get_mirror_source_rows())
    has_receipt = set(
        Receipt.objects.filter(user=user).values_list('transaction_id', flat=True)
    )
    transactions = (
        Transaction.objects.filter(user=user)
        .select_related('category')
        .order_by('row_number', 'id')
    )

    for tx in transactions:
        if tx.id in has_receipt:
            summary['skipped_has_receipt'] += 1
            continue
        sheet_tx = sheet_txs.get(tx.id)
        if sheet_tx is None:
            summary['skipped_not_on_sheet'] += 1
            continue
        sub_category = tx.category.sub_category if tx.category_id else ''
        if not should_attach_auto_receipt(sub_category) or not should_attach_auto_receipt(
            sheet_tx['sub_category']
        ):
            summary['skipped_exchange'] += 1
            continue
        if money_amount(sheet_tx['change']) <= 0:
            summary['skipped_zero'] += 1
            continue
        if tx.id in duplicates:
            summary['skipped_sheet_duplicate'] += 1
            continue

        sheet_comment = str(sheet_tx.get('comment') or '').strip()
        pg_comment = str(tx.comment or '').strip()
        chosen = sheet_comment or pg_comment or MISSING_DESCRIPTION
        if chosen == MISSING_DESCRIPTION:
            summary['placeholders'] += 1
        comment_for_db = None if pg_comment else chosen

        existing = sheet_receipts.get(tx.id)
        if existing is not None:
            if not existing['items']:
                summary['skipped_sheet_receipt_without_items'] += 1
                continue
            summary['repaired_from_sheet'] += 1
            if dry_run:
                continue
            try:
                _fill_blank_sheet_comment(client, sheet_tx, chosen)
                save_receipt_for_existing_transaction(
                    user=user,
                    transaction=tx,
                    receipt=existing,
                    comment=comment_for_db,
                )
            except (DualWriteError, SheetsError) as exc:
                summary['repaired_from_sheet'] -= 1
                _fail(summary, tx.id, exc)
            continue

        summary['created'] += 1
        if dry_run:
            continue
        try:
            _fill_blank_sheet_comment(client, sheet_tx, chosen)
            payload = build_auto_receipt(
                description=chosen,
                money=sheet_tx['change'],
                date=sheet_tx['date'].isoformat(),
            )
            receipt_row, item_row = auto_receipt_sheet_rows(
                payload, transaction_id=str(tx.id)
            )
            client.append_rows(settings.RECEIPT_TABLE, RECEIPT_COLUMNS, [receipt_row])
            client.append_rows(
                settings.RECEIPT_ITEMS_TABLE, RECEIPT_ITEM_COLUMNS, [item_row]
            )
            save_receipt_for_existing_transaction(
                user=user,
                transaction=tx,
                receipt=payload,
                comment=comment_for_db,
            )
        except (DualWriteError, SheetsError, ValueError) as exc:
            summary['created'] -= 1
            _fail(summary, tx.id, exc)

    return summary
