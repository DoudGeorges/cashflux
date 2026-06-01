"""
Per-card behavioral baseline.
Computed once from the full transaction history.
"""

from __future__ import annotations

import pandas as pd


def build_baselines(df: pd.DataFrame) -> dict[str, dict]:
    """
    Returns a dict keyed by card_id with each card's normal behavior profile.
    """
    baselines = {}
    for card_id, group in df.groupby("card_id"):
        debits = group[group["amount"] > 0]
        amounts = debits["amount"]

        baselines[card_id] = {
            "median_amount": float(amounts.median()) if len(amounts) else 0,
            "iqr": float(amounts.quantile(0.75) - amounts.quantile(0.25))
            if len(amounts)
            else 1,
            "p95": float(amounts.quantile(0.95)) if len(amounts) else 0,
            "typical_categories": set(
                debits["merchant_category"].value_counts().head(3).index
            ),
            "typical_channels": set(debits["channel"].unique()),
            "home_country": group["cardholder_country"].iloc[0],
            "known_devices": set(debits["device_id"].dropna().unique()),
            "known_ips": set(debits["ip_address"].dropna().unique()),
            "transaction_count": len(debits),
        }
    return baselines


def build_cross_card_maps(df: pd.DataFrame) -> dict[str, dict]:
    """
    Maps device_id and ip_address to sets of card_ids that used them.
    Used to detect cross-card device/IP reuse (account takeover signal).
    """
    device_to_cards = (
        df[df["device_id"].notna()].groupby("device_id")["card_id"].apply(set).to_dict()
    )
    ip_to_cards = (
        df[df["ip_address"].notna()]
        .groupby("ip_address")["card_id"]
        .apply(set)
        .to_dict()
    )
    return {"device_to_cards": device_to_cards, "ip_to_cards": ip_to_cards}
