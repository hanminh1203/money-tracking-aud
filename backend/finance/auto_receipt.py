"""Synthetic one-line receipts for transactions that were not itemised.

The sheet column ``Comment`` is the transaction description. A synthetic receipt
has one Receipt_Items row: name = description, amount = 1, unit = piece, money
= abs(transaction change). Receipt total is that same absolute amount.

Dashboard income and expense sum ``Transaction.change`` by category type. They
do not add receipt totals, so the extra row is not a second spend.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

# Cash transfers and giftcard purchases. Not a purchase, so no synthetic receipt.
EXCHANGE_SUB_CATEGORY = 'Exchange (self)'
AUTO_RECEIPT_UNIT = 'piece'
# Blank historical comments cannot be a receipt item name. Written onto the
# transaction as well so the line stays recognisable as synthetic.
MISSING_DESCRIPTION = '(no description)'


class DescriptionRequired(ValueError):
    """Create/edit was submitted without a description."""


def require_description(comment: Any) -> str:
    note = str(comment or '').strip()
    if not note:
        raise DescriptionRequired('Description is required.')
    return note


def should_attach_auto_receipt(sub_category: Any) -> bool:
    """Exchange (self) moves money between holdings; it is not a purchase."""
    return str(sub_category or '').strip() != EXCHANGE_SUB_CATEGORY


def money_amount(value: Any) -> Decimal:
    """Absolute money rounded to cents. Zero means there is nothing to receipt."""
    amount = abs(Decimal(str(value))).quantize(Decimal('0.01'))
    return amount


def _item_fields(item: Any) -> tuple[str, Decimal, str, Decimal]:
    if isinstance(item, dict):
        name = item.get('name')
        amount = item.get('amount')
        unit = item.get('unit')
        money = item.get('money')
    else:
        name = item.name
        amount = item.amount
        unit = item.unit
        money = item.money
    return (
        str(name or '').strip(),
        Decimal(str(amount)),
        str(unit or '').strip(),
        Decimal(str(money)),
    )


def _is_piece_line(item: Any, *, name: str, money: Any) -> bool:
    item_name, amount, unit, item_money = _item_fields(item)
    target = money_amount(money)
    if target <= 0 or not name:
        return False
    return (
        item_name == name
        and unit.lower() == AUTO_RECEIPT_UNIT
        and abs(amount - Decimal('1')) <= Decimal('0.0001')
        and abs(item_money - target) <= Decimal('0.009')
    )


def is_auto_receipt(*, comment: Any, change: Any, receipt_total: Any, items: Any) -> bool:
    """True when the linked receipt is still the single synthetic line.

    Compared to the transaction as stored, not to an in-progress edit. A second
    line, a different unit, a renamed item, or money that no longer matches
    abs(change) means the user has edited the receipt.
    """
    rows = list(items or [])
    if len(rows) != 1:
        return False
    expected = str(comment or '').strip()
    if not _is_piece_line(rows[0], name=expected, money=change):
        return False
    return abs(Decimal(str(receipt_total)) - money_amount(change)) <= Decimal('0.009')


def incoming_matches_line(items: Any, *, description: str, money: Any) -> bool:
    rows = list(items or [])
    if len(rows) != 1:
        return False
    return _is_piece_line(rows[0], name=str(description or '').strip(), money=money)


def build_auto_receipt(*, description: str, money: Any, date: str) -> dict:
    """Payload stored on the sheet and in Postgres for one synthetic receipt."""
    total = money_amount(money)
    if total <= 0:
        raise ValueError('Invalid amount')
    note = str(description or '').strip()
    if not note:
        raise DescriptionRequired('Description is required.')
    return {
        'receipt_id': str(uuid.uuid4()),
        'date': date,
        'total': total,
        'items': [
            {
                'id': str(uuid.uuid4()),
                'name': note,
                'amount': Decimal('1'),
                'unit': AUTO_RECEIPT_UNIT,
                'money': total,
            }
        ],
    }


def auto_receipt_sheet_rows(
    payload: dict, *, transaction_id: str
) -> tuple[list[list], list[list]]:
    """Receipt table row, then Receipt_Items row, using the same ids as Postgres."""
    item = payload['items'][0]
    total = float(payload['total'])
    receipt_row = [payload['receipt_id'], str(transaction_id), payload['date'], total]
    item_row = [
        item['id'],
        payload['receipt_id'],
        item['name'],
        1,
        AUTO_RECEIPT_UNIT,
        float(item['money']),
    ]
    return receipt_row, item_row
