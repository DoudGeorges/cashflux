"""Shared formatting utilities for display text, currency, and dates."""

from __future__ import annotations

import math

EMPTY_LABEL = "N/A"


def sanitize_display_text(value: object) -> str:
    """Normalize user-visible copy."""
    if value is None:
        return EMPTY_LABEL
    s = str(value).strip()
    if not s:
        return EMPTY_LABEL
    return s


def fmt_money(amount: float) -> str:
    try:
        n = float(amount)
    except (TypeError, ValueError):
        return "CA$0.00"
    return f"CA${n:,.2f}"


def fmt_date(value: object) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return EMPTY_LABEL
    if hasattr(value, "strftime"):
        return value.strftime("%b %d, %Y")
    return str(value)


format_cad = fmt_money
