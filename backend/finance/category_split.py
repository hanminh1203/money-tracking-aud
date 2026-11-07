"""Split one transaction's signed change across receipt-item subcategories.

Homepage income and expense cards still sum ``Transaction.change``. This module
only splits that same signed amount for the monthly subcategory breakdown, so
the pieces always add back to ``change``.

Receipt item ``money`` is a positive weight. It is not added on top of the
transaction, and giftcard funding is not a second spend.

- No receipt items (including a receipt with no lines): the whole change stays
  on the transaction subcategory.
- Item money sums to ``abs(change)``: each item keeps its money, signed with
  the transaction, on its subcategory.
- Item money sums to less (a fee, tip, or line that was not itemised): each
  item keeps its money, and the remainder stays on the transaction subcategory.
- Item money sums to more (a discount or rounding): items are scaled down in
  proportion to their money, rounded down to cents. Leftover cents stay on the
  transaction subcategory.
- A blank item subcategory, or one whose category type is not the
  transaction's type, is labelled with the transaction subcategory. Income and
  expense totals therefore stay on the transaction's type.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Any

CENT = Decimal('0.01')


def _money(value: Any) -> Decimal:
    return abs(Decimal(str(value or 0))).quantize(CENT, rounding=ROUND_HALF_UP)


def allocate_change(
    *,
    change: Decimal,
    transaction_sub_category: str,
    transaction_type: str,
    items: list[dict] | None,
) -> list[tuple[str, str, Decimal]]:
    """Return ``(category type, subcategory, signed amount)`` pieces.

    The pieces sum to ``change`` for an Income or Expense transaction that has
    a subcategory. Anything else returns an empty list (transfers, blank
    category), matching the homepage cards, which ignore those rows.
    """
    if transaction_type not in ('Income', 'Expense'):
        return []
    label = str(transaction_sub_category or '').strip()
    if not label:
        return []
    signed = Decimal(change)
    if signed == 0:
        return []

    sign = Decimal('1') if signed > 0 else Decimal('-1')
    target = abs(signed)
    weights: list[Decimal] = []
    labels: list[str] = []
    for item in items or []:
        weight = _money(item.get('money'))
        if weight <= 0:
            continue
        item_sub = str(item.get('sub_category') or '').strip()
        item_type = str(item.get('category_type') or '').strip()
        if item_sub and item_type == transaction_type:
            labels.append(item_sub)
        else:
            labels.append(label)
        weights.append(weight)

    if not weights:
        return [(transaction_type, label, signed)]

    weight_sum = sum(weights, Decimal('0'))
    if weight_sum <= 0:
        return [(transaction_type, label, signed)]

    if weight_sum <= target:
        allocated = list(weights)
        residual = target - weight_sum
    else:
        allocated = [
            (target * weight / weight_sum).quantize(CENT, rounding=ROUND_DOWN)
            for weight in weights
        ]
        residual = target - sum(allocated, Decimal('0'))

    parts: dict[str, Decimal] = {}
    for item_label, amount in zip(labels, allocated):
        if amount == 0:
            continue
        parts[item_label] = parts.get(item_label, Decimal('0')) + amount
    if residual != 0:
        parts[label] = parts.get(label, Decimal('0')) + residual

    return [
        (transaction_type, name, sign * amount)
        for name, amount in parts.items()
        if amount != 0
    ]
