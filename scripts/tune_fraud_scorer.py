"""Offline tuning helper for Fraud Hunter challenge CSV."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fraud_detector.baseline import build_baselines
from fraud_detector.scorer import score_transactions, DEFAULT_THRESHOLD


def proxy_fraud_ids(df: pd.DataFrame) -> set[str]:
    fraud_ids: set[str] = set()
    baselines = build_baselines(df)

    for card in df["card_id"].unique():
        g = df[df["card_id"] == card].sort_values("timestamp")
        times = g["timestamp"].tolist()
        ids = g["transaction_id"].tolist()
        for i, t in enumerate(times):
            window = [
                ids[j]
                for j, t2 in enumerate(times)
                if abs((t2 - t).total_seconds()) <= 3600
            ]
            if len(window) >= 6:
                fraud_ids.update(window)

    qp = df[df["merchant_name"] == "QuickPay Online"]
    for _, row in qp.iterrows():
        ts = row["timestamp"]
        window = qp[
            (qp["timestamp"] >= ts - pd.Timedelta(hours=24))
            & (qp["timestamp"] <= ts + pd.Timedelta(hours=24))
        ]
        if window["card_id"].nunique() >= 5:
            med = baselines.get(row["card_id"], {}).get("median_amount", 0)
            if med > 0 and row["amount"] / med >= 3:
                fraud_ids.add(row["transaction_id"])

    for _, row in df.iterrows():
        if row["merchant_category"] not in ("electronics", "gift_card"):
            continue
        med = baselines.get(row["card_id"], {}).get("median_amount", 0)
        if med > 0 and row["amount"] / med >= 10 and row["amount"] >= 400:
            fraud_ids.add(row["transaction_id"])

    return fraud_ids


def main() -> None:
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "fraud_hunter" / "transactions.csv"
    df = pd.read_csv(csv_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    fraud_ids = proxy_fraud_ids(df)
    scored = score_transactions(df, threshold=DEFAULT_THRESHOLD)
    flagged = set(scored.loc[scored["flagged"], "transaction_id"])

    tp = len(flagged & fraud_ids)
    fp = len(flagged - fraud_ids)
    fn = len(fraud_ids - flagged)
    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0

    print(f"CSV: {csv_path}")
    print(f"Threshold: {DEFAULT_THRESHOLD}")
    print(f"Flagged: {len(flagged)} / {len(df)} ({100 * len(flagged) / len(df):.1f}%)")
    print(f"Proxy labels: {len(fraud_ids)} ({100 * len(fraud_ids) / len(df):.1f}%)")
    print(f"Precision: {precision:.3f}  Recall: {recall:.3f}  F1: {f1:.3f}")
    print(f"Score range: {scored['fraud_score'].min():.3f} - {scored['fraud_score'].max():.3f}")


if __name__ == "__main__":
    main()
