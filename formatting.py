"""Shared money and date formatting for CashFlux."""

from __future__ import annotations

import pandas as pd

EMPTY_LABEL = "N/A"


def sanitize_display_text(value) -> str:
    """Normalize user-visible copy."""
    if value is None:
        return EMPTY_LABEL
    s = str(value).strip()
    if not s:
        return EMPTY_LABEL
    return s


def format_cad(amount: float) -> str:
    try:
        n = float(amount)
    except (TypeError, ValueError):
        return "CA$0.00"
    return f"CA${n:,.2f}"


def fmt_money(amount: float) -> str:
    return format_cad(amount)


def fmt_date(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return EMPTY_LABEL
    if hasattr(value, "strftime"):
        return value.strftime("%b %d, %Y")
    return str(value)
