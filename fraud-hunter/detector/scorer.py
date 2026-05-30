"""
Combines all rule scores into a final fraud score per transaction.
Returns an enriched DataFrame with score + explanation columns.
"""
import pandas as pd
from detector.baseline import build_baselines, build_cross_card_maps
from detector.rules import (
    rule_amount_anomaly, rule_foreign_merchant, rule_new_device,
    rule_atypical_category, rule_cross_card_device, rule_cross_card_ip,
    rule_velocity, rule_odd_hours, rule_gift_card_electronics,
    rule_merchant_burst,
)

# Weight for each rule (must sum to <= 1.0 combined max contribution)
RULE_WEIGHTS = {
    "amount_anomaly":        0.22,
    "merchant_burst":        0.22,
    "cross_card_device":     0.18,
    "cross_card_ip":         0.12,
    "foreign_merchant":      0.10,
    "velocity":              0.08,
    "new_device":            0.05,
    "atypical_category":     0.02,
    "odd_hours":             0.02,
    "gift_card_electronics": 0.03,
}

DEFAULT_THRESHOLD = 0.40


def score_transactions(df: pd.DataFrame, threshold: float = DEFAULT_THRESHOLD) -> pd.DataFrame:
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    baselines = build_baselines(df)
    cross_card = build_cross_card_maps(df)

    scores = []
    reasons_list = []
    rule_hits = []

    for _, row in df.iterrows():
        hits = {}

        hits["amount_anomaly"] = rule_amount_anomaly(row, baselines)
        hits["foreign_merchant"] = rule_foreign_merchant(row, baselines)
        hits["new_device"] = rule_new_device(row, baselines)
        hits["atypical_category"] = rule_atypical_category(row, baselines)
        hits["cross_card_device"] = rule_cross_card_device(row, cross_card)
        hits["cross_card_ip"] = rule_cross_card_ip(row, cross_card)
        hits["velocity"] = rule_velocity(row, df)
        hits["odd_hours"] = rule_odd_hours(row, baselines)
        hits["gift_card_electronics"] = rule_gift_card_electronics(row)
        hits["merchant_burst"] = rule_merchant_burst(row, df)

        total_score = 0.0
        reasons = []

        for rule_name, (raw_score, reason) in hits.items():
            weight = RULE_WEIGHTS.get(rule_name, 0.05)
            contribution = raw_score * weight
            total_score += contribution
            if raw_score > 0 and reason:
                reasons.append(reason)

        # Cap at 1.0
        total_score = min(round(total_score, 4), 1.0)

        scores.append(total_score)
        reasons_list.append(" | ".join(reasons) if reasons else "No anomalies detected")
        rule_hits.append({k: v[0] for k, v in hits.items()})

    df["fraud_score"] = scores
    df["explanation"] = reasons_list
    df["flagged"] = df["fraud_score"] >= threshold
    df["review_status"] = "pending"  # pending | approved | dismissed | escalated

    return df
