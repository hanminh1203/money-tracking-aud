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
        raise ValueError('At least one payment is required')
    expected = abs(_to_decimal(change))
    actual = funding_total(payments, giftcard_payments)
    if abs(expected - actual) > FUNDING_TOLERANCE:
        raise ValueError(
            f'Payment amounts ({actual}) must equal transaction amount ({expected})'
        )
