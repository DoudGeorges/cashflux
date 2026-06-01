"""
Combines all rule scores into a final fraud score per transaction.
Returns an enriched DataFrame with score + explanation columns.
"""

from __future__ import annotations

import pandas as pd
from core.formatting import sanitize_display_text
from services.fraud.baseline import build_baselines, build_cross_card_maps
from services.fraud.rules import (
    rule_amount_anomaly,
    rule_foreign_merchant,
    rule_atypical_category,
    rule_cross_card_device,
    rule_cross_card_ip,
    rule_velocity,
    rule_odd_hours,
    rule_gift_card_electronics,
    rule_merchant_burst,
    rule_duplicate_charge,
    rule_round_number,
    rule_suspicious_merchant,
    rule_card_testing,
    rule_foreign_high_amount,
    rule_atm_anomaly,
)

# Relative importance when combining supporting signals.
RULE_WEIGHTS = {
    "amount_anomaly": 0.20,
    "merchant_burst": 0.20,
    "suspicious_merchant": 0.18,
    "card_testing": 0.16,
    "cross_card_device": 0.14,
    "velocity": 0.12,
    "foreign_high_amount": 0.10,
    "duplicate_charge": 0.10,
    "cross_card_ip": 0.08,
    "foreign_merchant": 0.06,
    "atm_anomaly": 0.06,
    "new_device": 0.05,
    "gift_card_electronics": 0.05,
    "round_number": 0.04,
    "atypical_category": 0.03,
    "odd_hours": 0.02,
}
# Note: weights intentionally do not sum to 1.0; the scorer applies a 1.20 multiplier before capping.

CRITICAL_RULES = frozenset(
    {
        "amount_anomaly",
        "merchant_burst",
        "suspicious_merchant",
        "card_testing",
        "velocity",
        "cross_card_device",
        "cross_card_ip",
        "foreign_high_amount",
    }
)

DEFAULT_THRESHOLD = 0.58


def combine_rule_scores(hits: dict[str, tuple[float, str]]) -> float:
    """
    Hybrid scorer tuned for Fraud Hunter challenge patterns.

    Strong signals should flag on their own, but final scores stay in a realistic
    band (roughly 50 to 92%) so reviewers see differentiated risk, not piles of 100%.
    """
    weighted = sum(hits[name][0] * RULE_WEIGHTS.get(name, 0.05) for name in hits)
    critical_scores = [hits[name][0] for name in CRITICAL_RULES if hits[name][0] > 0]
    top_critical = max(critical_scores) if critical_scores else 0.0
    n_critical = sum(1 for s in critical_scores if s >= 0.55)
    strong_critical = sum(1 for s in critical_scores if s >= 0.75)

    base = weighted * 1.20
    if top_critical >= 0.85:
        base = max(base, 0.52 + top_critical * 0.30)
    elif top_critical >= 0.65:
        base = max(base, 0.42 + top_critical * 0.34)
    elif top_critical >= 0.45:
        base = max(base, 0.35 + top_critical * 0.38)

    if strong_critical >= 3:
        base += 0.08
    elif strong_critical >= 2:
        base += 0.05
    elif n_critical >= 2:
        base += 0.03

    # Hard cap: reserve 93%+ for rare multi-signal cases only
    if strong_critical >= 3 and top_critical >= 0.90:
        cap = 0.93
    elif strong_critical >= 2 and top_critical >= 0.85:
        cap = 0.90
    else:
        cap = 0.87

    return min(round(base, 4), cap)


def _velocity_counts(df: pd.DataFrame) -> dict:
    counts = {}
    for _, group in df.groupby("card_id", sort=False):
        group = group.sort_values("timestamp")
        times = pd.to_datetime(group["timestamp"]).tolist()
        for idx, ts in zip(group.index, times):
            lo = ts - pd.Timedelta(hours=1)
            hi = ts + pd.Timedelta(hours=1)
            counts[idx] = sum(1 for t in times if lo <= t <= hi)
    return counts


def _merchant_burst_counts(df: pd.DataFrame) -> dict:
    counts = {}
    for merchant, group in df.groupby("merchant_name", sort=False):
        if not merchant:
            continue
        group = group.sort_values("timestamp")
        times = pd.to_datetime(group["timestamp"]).tolist()
        cards = group["card_id"].tolist()
        for idx, ts in zip(group.index, times):
            lo = ts - pd.Timedelta(hours=24)
            hi = ts + pd.Timedelta(hours=24)
            window_cards = {cards[i] for i, t in enumerate(times) if lo <= t <= hi}
            counts[idx] = len(window_cards)
    return counts


def _first_seen_devices(df: pd.DataFrame) -> dict:
    """Per-row: device is new if first online use on this card (chronological)."""
    is_new: dict = {}
    seen: dict[str, set[str]] = {}

    ordered = df.sort_values(["card_id", "timestamp"])
    for idx, row in ordered.iterrows():
        card = row["card_id"]
        device = row.get("device_id")
        known = seen.setdefault(card, set())
        if pd.isna(device) or not device:
            is_new[idx] = False
            continue
        is_new[idx] = device not in known
        known.add(device)
    return is_new


def score_transactions(
    df: pd.DataFrame, threshold: float = DEFAULT_THRESHOLD
) -> pd.DataFrame:
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    baselines = build_baselines(df)
    cross_card = build_cross_card_maps(df)
    velocity_counts = _velocity_counts(df)
    merchant_burst_counts = _merchant_burst_counts(df)
    new_device_flags = _first_seen_devices(df)

    scores = []
    reasons_list = []

    for idx, row in df.iterrows():
        burst_cards = merchant_burst_counts.get(idx, 0)
        velocity_count = velocity_counts.get(idx, 0)

        hits = {
            "amount_anomaly": rule_amount_anomaly(row, baselines),
            "merchant_burst": rule_merchant_burst(row, df, unique_cards=burst_cards),
            "suspicious_merchant": rule_suspicious_merchant(
                row, baselines, burst_cards=burst_cards
            ),
            "card_testing": rule_card_testing(
                row, baselines, velocity_count=velocity_count
            ),
            "cross_card_device": rule_cross_card_device(row, cross_card),
            "cross_card_ip": rule_cross_card_ip(row, cross_card),
            "foreign_merchant": rule_foreign_merchant(row, baselines),
            "foreign_high_amount": rule_foreign_high_amount(row, baselines),
            "velocity": rule_velocity(row, df, velocity_count=velocity_count),
            "new_device": (
                (
                    0.25,
                    sanitize_display_text(
                        f"New device {row['device_id']} first use on this card"
                    ),
                )
                if new_device_flags.get(idx)
                else (0.0, "")
            ),
            "atypical_category": rule_atypical_category(row, baselines),
            "odd_hours": rule_odd_hours(row, baselines),
            "gift_card_electronics": rule_gift_card_electronics(row),
            "duplicate_charge": rule_duplicate_charge(row, df),
            "round_number": rule_round_number(row, baselines),
            "atm_anomaly": rule_atm_anomaly(row, baselines),
        }

        total_score = combine_rule_scores(hits)
        reasons = [
            sanitize_display_text(reason)
            for raw_score, reason in hits.values()
            if raw_score > 0 and reason
        ]

        scores.append(round(total_score, 4))
        reasons_list.append(". ".join(reasons) if reasons else "No anomalies detected")

    df["fraud_score"] = scores
    df["explanation"] = reasons_list
    df["flagged"] = df["fraud_score"] >= threshold
    df["review_status"] = "pending"

    return df
