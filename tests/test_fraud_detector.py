"""Fraud Hunter detector tests — known fraud patterns + legitimate baselines."""

from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from fraud_detector.scorer import DEFAULT_THRESHOLD, score_transactions

CHALLENGE_CSV = Path(__file__).resolve().parents[1] / "data" / "fraud_hunter" / "transactions.csv"


def _challenge_df() -> pd.DataFrame:
    if not CHALLENGE_CSV.is_file():
        raise unittest.SkipTest("Challenge transactions.csv not found")
    return pd.read_csv(CHALLENGE_CSV)


def _proxy_fraud_ids(df: pd.DataFrame) -> set[str]:
    """Approximate ground truth from the four documented fraud patterns."""
    from fraud_detector.baseline import build_baselines

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


class FraudDetectorTests(unittest.TestCase):
    def test_quickpay_burst_is_flagged(self):
        df = _challenge_df()
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        scored = score_transactions(df, threshold=DEFAULT_THRESHOLD)
        hits = scored[scored["transaction_id"].isin({"tx_000995", "tx_000996", "tx_000999"})]
        self.assertTrue(hits["flagged"].all(), "QuickPay burst cluster should be flagged")

    def test_velocity_card_testing_is_flagged(self):
        df = _challenge_df()
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        scored = score_transactions(df, threshold=DEFAULT_THRESHOLD)
        card023 = scored[
            (scored["card_id"] == "card_023")
            & (scored["explanation"].str.contains("1 hour", na=False))
        ]
        self.assertGreaterEqual(len(card023), 6, "Velocity burst on card_023 should produce flags")

    def test_legitimate_grocery_not_over_flagged(self):
        df = _challenge_df()
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        scored = score_transactions(df, threshold=DEFAULT_THRESHOLD)
        provigo = scored[
            (scored["merchant_name"] == "Provigo")
            & (scored["merchant_category"] == "grocery")
            & (scored["amount"] < 80)
        ]
        flagged_rate = provigo["flagged"].mean() if len(provigo) else 0
        self.assertLess(flagged_rate, 0.15, "Routine grocery purchases should rarely flag")

    def test_detection_quality_on_proxy_labels(self):
        df = _challenge_df()
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        fraud_ids = _proxy_fraud_ids(df)
        scored = score_transactions(df, threshold=DEFAULT_THRESHOLD)
        flagged = set(scored.loc[scored["flagged"], "transaction_id"])

        tp = len(flagged & fraud_ids)
        fp = len(flagged - fraud_ids)
        fn = len(fraud_ids - flagged)
        precision = tp / (tp + fp) if tp + fp else 0
        recall = tp / (tp + fn) if tp + fn else 0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0

        self.assertGreaterEqual(len(flagged), 40)
        self.assertGreaterEqual(recall, 0.85)
        self.assertGreaterEqual(precision, 0.75)
        self.assertGreaterEqual(f1, 0.80)


if __name__ == "__main__":
    unittest.main()
