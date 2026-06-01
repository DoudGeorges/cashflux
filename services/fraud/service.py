"""Fraud Hunter scoring wired to CashFlux expense transactions."""

from __future__ import annotations

import io
import math
from pathlib import Path

import pandas as pd
from typing import Any

from services.company import get_company_paths
from core.formatting import sanitize_display_text
from services.fraud.scorer import DEFAULT_THRESHOLD, score_transactions
from core.paths import DATA_DIR

_threshold: float = DEFAULT_THRESHOLD
_df: pd.DataFrame | None = None
_undo_stack: list[dict] = []
_dismissed_patterns: list[dict] = []

CHALLENGE_CSV = DATA_DIR / "fraud_hunter" / "transactions.csv"
_ONLINE_HINTS = (
    "amazon",
    "online",
    "paypal",
    "stripe",
    "quickpay",
    "aliexpress",
    "newegg",
    "ebay",
    "shopify",
    "digital",
)

_ELECTRONICS_HINTS = (
    "electronic",
    "software",
    "computer",
    "apple",
    "newegg",
    "best buy",
)


def _infer_channel(row: dict) -> str:
    vendor = str(row.get("Merchant Info DBA Name") or "").lower()
    desc = str(row.get("Transaction Description") or "").lower()
    if any(k in vendor or k in desc for k in _ONLINE_HINTS):
        return "online"
    return "in_person"


def _normalize_category(row: dict) -> str:
    cat = str(row.get("Transaction Category") or "").lower()
    desc = str(row.get("Transaction Description") or "").lower()
    blob = f"{cat} {desc}"
    if "gift" in blob:
        return "gift_card"
    if any(k in blob for k in _ELECTRONICS_HINTS):
        return "electronics"
    return cat or "other"


def _country_code(val) -> str:
    s = str(val or "").strip().upper()
    return s[:3] if s else ""


def _parse_timestamp(row) -> pd.Timestamp | None:
    for key in ("Transaction Date", "Posting date of transaction"):
        raw = row.get(key)
        if pd.isna(raw) or raw == "":
            continue
        ts = pd.to_datetime(raw, errors="coerce")
        if pd.notna(ts):
            return ts
    return None


def load_challenge_fraud_df(path: Path | None = None) -> pd.DataFrame:
    """Load native Fraud Hunter challenge CSV (transactions.csv schema)."""
    csv_path = path or CHALLENGE_CSV
    if not csv_path.is_file():
        return pd.DataFrame()
    df = pd.read_csv(csv_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def load_expenses_as_fraud_df() -> pd.DataFrame:
    """Map scored expense rows into the Fraud Hunter schema (employee = card)."""
    path = get_company_paths().scored_tx
    if not path.is_file():
        return pd.DataFrame()
    raw = pd.read_csv(path)
    if "Debit or Credit" in raw.columns:
        raw = raw[raw["Debit or Credit"].astype(str).str.lower() != "credit"]

    rows = []
    for idx, row in raw.iterrows():
        amount = float(row.get("Amount Clean") or row.get("Transaction Amount") or 0)
        if amount <= 0:
            continue
        ts = _parse_timestamp(row)
        if ts is None:
            continue

        street = str(row.get("Merchant Street Address") or "").strip()
        city = str(row.get("Merchant City") or "").strip()
        postal = str(row.get("Merchant Postal Code") or "").strip()
        employee_id = str(
            row.get("Employee ID") or row.get("Employee Name") or "unknown"
        )

        rows.append(
            {
                "transaction_id": f"tx_{idx}",
                "timestamp": ts,
                "card_id": employee_id,
                "employee_name": str(row.get("Employee Name") or ""),
                "department": str(row.get("Department") or ""),
                "amount": amount,
                "merchant_name": str(row.get("Merchant Info DBA Name") or "Unknown"),
                "merchant_category": _normalize_category(row),
                "channel": _infer_channel(row),
                "cardholder_country": _country_code(row.get("Approved Country")),
                "merchant_country": _country_code(row.get("Merchant Country")),
                "device_id": street or None,
                "ip_address": f"{city}|{postal}" if city or postal else None,
            }
        )

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def load_fraud_source_df() -> pd.DataFrame:
    """Prefer challenge CSV when present; otherwise map company expense rows."""
    challenge = load_challenge_fraud_df()
    if not challenge.empty:
        return challenge
    return load_expenses_as_fraud_df()


def get_fraud_df() -> pd.DataFrame:
    global _df
    if _df is None:
        _df = score_transactions(load_fraud_source_df(), _threshold)
        # Called again after initial score load to suppress similar low-scoring flags
        _apply_dismissed_patterns()
    return _df


def _apply_dismissed_patterns() -> None:
    """Session feedback: suppress flags similar to reviewer dismissals."""
    global _df
    if _df is None or not _dismissed_patterns:
        return

    for pattern in _dismissed_patterns:
        card = pattern.get("card_id")
        merchant = pattern.get("merchant_name")
        category = pattern.get("merchant_category")
        mask = _df["review_status"] == "pending"
        if card:
            mask &= _df["card_id"] == card
        if merchant:
            mask &= _df["merchant_name"] == merchant
        if category:
            mask &= _df["merchant_category"] == category
        if pattern.get("max_score") is not None:
            mask &= _df["fraud_score"] <= float(pattern["max_score"])
        _df.loc[mask, "fraud_score"] = _df.loc[mask, "fraud_score"] * 0.75
        _df.loc[mask & (_df["fraud_score"] < _threshold), "flagged"] = False


def reset_fraud_session() -> None:
    global _df, _undo_stack, _dismissed_patterns
    _df = None
    _undo_stack = []
    _dismissed_patterns = []


def get_threshold() -> float:
    return _threshold


def set_threshold(value: float) -> float:
    global _df, _threshold
    _threshold = max(0.05, min(0.95, float(value)))
    _df = None
    return _threshold


def fraud_stats() -> dict:
    df = get_fraud_df()
    flagged = df[df["flagged"]]
    return {
        "total": int(len(df)),
        "flagged": int(len(flagged)),
        "pending": int(len(flagged[flagged["review_status"] == "pending"])),
        "approved": int(len(flagged[flagged["review_status"] == "approved"])),
        "dismissed": int(len(flagged[flagged["review_status"] == "dismissed"])),
        "escalated": int(len(flagged[flagged["review_status"] == "escalated"])),
        "threshold": _threshold,
        "source": "challenge" if CHALLENGE_CSV.is_file() else "expenses",
    }


def flagged_records() -> list[dict]:
    df = get_fraud_df()
    flagged = df[df["flagged"]].sort_values("fraud_score", ascending=False)
    cols = [
        "transaction_id",
        "timestamp",
        "card_id",
        "employee_name",
        "department",
        "amount",
        "merchant_name",
        "merchant_category",
        "channel",
        "cardholder_country",
        "merchant_country",
        "device_id",
        "ip_address",
        "fraud_score",
        "explanation",
        "review_status",
    ]
    present = [c for c in cols if c in flagged.columns]
    subset = flagged[present].copy()
    subset["timestamp"] = subset["timestamp"].astype(str)
    subset = subset.where(pd.notnull(subset), None)
    out = []
    for row in subset.to_dict(orient="records"):
        cleaned: dict[str, Any] = {}
        for k, v in row.items():
            if isinstance(v, float) and math.isnan(v):
                cleaned[k] = None
            elif k == "fraud_score" and v is not None:
                cleaned[k] = round(float(v), 4)
            elif k == "amount" and v is not None:
                cleaned[k] = round(float(v), 2)
            elif k == "explanation" and v:
                cleaned[k] = sanitize_display_text(v)
            else:
                cleaned[k] = v
        out.append(cleaned)
    return out


def review_transaction(transaction_id: str, action: str) -> dict:
    global _undo_stack
    df = get_fraud_df()
    idx = df.index[df["transaction_id"] == transaction_id]
    if len(idx) == 0:
        return {"error": "Transaction not found"}

    i = idx[0]
    prev_status = df.at[i, "review_status"]
    _undo_stack.append({"transaction_id": transaction_id, "prev_status": prev_status})
    df.at[i, "review_status"] = action

    if action == "dismissed":
        dismissed_row = df.loc[i]
        similar = df[
            (df["card_id"] == dismissed_row["card_id"])
            & (df["review_status"] == "pending")
            & (df["fraud_score"] < dismissed_row["fraud_score"])
        ]
        df.loc[similar.index, "fraud_score"] = (
            df.loc[similar.index, "fraud_score"] * 0.85
        )

        _dismissed_patterns.append(
            {
                "card_id": dismissed_row.get("card_id"),
                "merchant_name": dismissed_row.get("merchant_name"),
                "merchant_category": dismissed_row.get("merchant_category"),
                "max_score": float(dismissed_row.get("fraud_score") or 0),
            }
        )
        # Called after dismissal to immediately propagate suppression to similar pending flags
        _apply_dismissed_patterns()

    return {"status": "ok", "action": action}


def undo_review() -> dict:
    global _undo_stack
    df = get_fraud_df()
    if not _undo_stack:
        return {"error": "Nothing to undo"}
    last = _undo_stack.pop()
    idx = df.index[df["transaction_id"] == last["transaction_id"]]
    if len(idx):
        df.at[idx[0], "review_status"] = last["prev_status"]
    return {"status": "ok", "restored": last}


def fraud_pending_count() -> int:
    """Pending count without triggering a full score run."""
    if _df is None:
        return 0
    flagged = _df[_df["flagged"]]
    return int(len(flagged[flagged["review_status"] == "pending"]))


def export_reviewed_csv() -> tuple[io.BytesIO, str]:
    df = get_fraud_df()
    export = df.copy()
    export["fraud_flagged"] = export["flagged"].map({True: "yes", False: "no"})
    if "review_status" not in export.columns:
        export["fraud_review_status"] = "pending"
    else:
        export["fraud_review_status"] = export["review_status"]
    buf = io.BytesIO()
    export.to_csv(buf, index=False)
    buf.seek(0)
    return buf, "fraud_reviewed.csv"
