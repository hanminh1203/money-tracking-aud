"""Validate transaction funding (payments + giftcard payments)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

FUNDING_TOLERANCE = Decimal('0.009')


def _to_decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def funding_total(
    payments: list[dict],
    giftcard_payments: list[dict] | None = None,
) -> Decimal:
    total = Decimal('0')
    for row in payments:
        total += abs(_to_decimal(row.get('amount')))
    for row in giftcard_payments or []:
        total += abs(_to_decimal(row.get('amount')))
    return total


def validate_funding(change: Any, payments: list[dict], giftcard_payments: list[dict] | None = None) -> None:
    """Raise ValueError when funding does not match abs(change)."""
    if not payments and not giftcard_payments:
        raise ValueError('At least one payment or giftcard payment is required')
    expected = abs(_to_decimal(change))
    actual = funding_total(payments, giftcard_payments)
    if abs(expected - actual) > FUNDING_TOLERANCE:
        raise ValueError(
            f'Payment amounts ({actual}) must equal transaction amount ({expected})'
        )


def aggregate_giftcard_debits(giftcard_payments: list[dict] | None) -> dict[str, Decimal]:
    """Sum debit amounts by giftcard id (accepts giftcard_id or giftcardId keys)."""
    totals: dict[str, Decimal] = {}
    for row in giftcard_payments or []:
        gid = str(row.get('giftcard_id') or row.get('giftcardId') or '').strip()
        if not gid:
            raise ValueError('Giftcard payment is missing giftcard id')
        amount = abs(_to_decimal(row.get('amount')))
        if amount <= 0:
            raise ValueError('Giftcard payment amount must be greater than zero')
        totals[gid] = totals.get(gid, Decimal('0')) + amount
    return totals


def validate_giftcard_debit(balance: Any, amount: Any) -> Decimal:
    """Return new balance after debit, or raise ValueError if amount exceeds balance."""
    current = _to_decimal(balance)
    debit = abs(_to_decimal(amount))
    if debit > current + FUNDING_TOLERANCE:
        raise ValueError(f'Amount ({debit}) exceeds giftcard balance ({current})')
    new_balance = current - debit
    if new_balance < 0:
        new_balance = Decimal('0')
    return new_balance.quantize(Decimal('0.01'))
