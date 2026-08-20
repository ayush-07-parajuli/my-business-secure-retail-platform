"""Formatting helpers for dashboard and report templates."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation


def as_decimal(value) -> Decimal:
    """Convert arbitrary numeric-like values into a Decimal."""

    if value is None:
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")


def format_currency(value, symbol: str = "Rs.") -> str:
    """Return a consistently formatted currency string."""

    amount = as_decimal(value).quantize(Decimal("0.01"))
    return f"{symbol}{amount:,.2f}"
