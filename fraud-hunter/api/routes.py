"""
FastAPI routes for the fraud reviewer tool.
State is in-memory for the session (no DB needed).
"""
import json
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
import pandas as pd
from detector.scorer import score_transactions, DEFAULT_THRESHOLD

router = APIRouter()
DATA_PATH = Path(__file__).parent.parent / "transactions.csv"

# ── Session state ─────────────────────────────────────────────────────────────
_df: pd.DataFrame | None = None
_threshold: float = DEFAULT_THRESHOLD
_undo_stack: list[dict] = []


def get_df() -> pd.DataFrame:
    global _df
    if _df is None:
        raw = pd.read_csv(DATA_PATH)
        _df = score_transactions(raw, _threshold)
    return _df


# ── Models ────────────────────────────────────────────────────────────────────

class ReviewAction(BaseModel):
    transaction_id: str
    action: str   # "approved" | "dismissed" | "escalated"


class ThresholdUpdate(BaseModel):
    threshold: float


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def serve_ui():
    html_path = Path(__file__).parent.parent / "frontend" / "index.html"
    return HTMLResponse(html_path.read_text())


@router.get("/api/flagged")
async def get_flagged():
    df = get_df()
    flagged = df[df["flagged"]].sort_values("fraud_score", ascending=False)
    cols = ["transaction_id", "timestamp", "card_id", "amount",
            "merchant_name", "merchant_category", "channel",
            "cardholder_country", "merchant_country", "device_id", "ip_address",
            "fraud_score", "explanation", "review_status"]
    subset = flagged[cols].copy()
    subset = subset.where(pd.notnull(subset), None)
    records = []
    for row in subset.to_dict(orient="records"):
        records.append({k: (None if isinstance(v, float) and (v != v) else v) for k, v in row.items()})
    return records


@router.get("/api/stats")
async def get_stats():
    df = get_df()
    flagged = df[df["flagged"]]
    return {
        "total": len(df),
        "flagged": len(flagged),
        "pending": len(flagged[flagged["review_status"] == "pending"]),
        "approved": len(flagged[flagged["review_status"] == "approved"]),
        "dismissed": len(flagged[flagged["review_status"] == "dismissed"]),
        "escalated": len(flagged[flagged["review_status"] == "escalated"]),
        "threshold": _threshold,
    }


@router.post("/api/review")
async def review_transaction(action: ReviewAction):
    global _undo_stack
    df = get_df()
    idx = df.index[df["transaction_id"] == action.transaction_id]
    if len(idx) == 0:
        return {"error": "Transaction not found"}

    i = idx[0]
    prev_status = df.at[i, "review_status"]
    _undo_stack.append({"transaction_id": action.transaction_id, "prev_status": prev_status})

    df.at[i, "review_status"] = action.action

    # Feedback loop: if dismissed, suppress similar flags (same card + same top reason)
    if action.action == "dismissed":
        dismissed_row = df.loc[i]
        similar = df[
            (df["card_id"] == dismissed_row["card_id"]) &
            (df["review_status"] == "pending") &
            (df["fraud_score"] < dismissed_row["fraud_score"])
        ]
        df.loc[similar.index, "fraud_score"] *= 0.85

    return {"status": "ok", "action": action.action}


@router.post("/api/undo")
async def undo():
    global _undo_stack
    df = get_df()
    if not _undo_stack:
        return {"error": "Nothing to undo"}
    last = _undo_stack.pop()
    idx = df.index[df["transaction_id"] == last["transaction_id"]]
    if len(idx):
        df.at[idx[0], "review_status"] = last["prev_status"]
    return {"status": "ok", "restored": last}


@router.post("/api/threshold")
async def set_threshold(body: ThresholdUpdate):
    global _df, _threshold
    _threshold = body.threshold
    _df = None   # force re-score
    return {"threshold": _threshold}


@router.get("/api/export")
async def export_csv():
    df = get_df()
    out_path = Path(__file__).parent.parent / "transactions_reviewed.csv"
    df.to_csv(out_path, index=False)
    return FileResponse(out_path, filename="transactions_reviewed.csv", media_type="text/csv")
