"""
Fraud detection rules. Each rule returns a (score, reason) tuple.
score is 0.0 (clean) to 1.0 (very suspicious).
"""

import pandas as pd
from datetime import timedelta

_SUSPICIOUS_MERCHANT_KEYWORDS = (
    "quickpay",
    "cryptopay",
    "wire transfer",
    "verify account",
)


def rule_amount_anomaly(row, baseline: dict) -> tuple[float, str]:
    card = baseline.get(row["card_id"], {})
    median = card.get("median_amount", 0)
    iqr = max(card.get("iqr", 1), 1)
    p95 = card.get("p95", 0)
    amount = row["amount"]

    if median == 0:
        return 0.0, ""

    ratio = amount / median
    z = (amount - median) / iqr

    if amount > p95 * 2 and ratio >= 5:
        return (
            0.9,
            f"Amount ${amount:.2f} is {ratio:.1f}× this card's median (${median:.2f})",
        )
    if amount > p95 and ratio >= 3:
        return (
            0.6,
            f"Amount ${amount:.2f} is {ratio:.1f}× this card's median (${median:.2f})",
        )
    if z > 3:
        return 0.4, f"Amount ${amount:.2f} is unusually high for this card"
    return 0.0, ""


def rule_foreign_merchant(row, baseline: dict) -> tuple[float, str]:
    card = baseline.get(row["card_id"], {})
    home = card.get("home_country", "")
    merchant_country = row.get("merchant_country", "")
    if home and merchant_country and home != merchant_country:
        return 0.5, f"Card is from {home} but transaction in {merchant_country}"
    return 0.0, ""


def rule_new_device(row, baseline: dict) -> tuple[float, str]:
    """Flag a transaction where the device_id has not been seen on this card before. Note: in the main scoring pipeline this rule is bypassed; pre-computed new_device_flags from _first_seen_devices() are used instead. This function is kept for standalone/testing use."""
    if pd.isna(row.get("device_id")) or not row.get("device_id"):
        return 0.0, ""
    card = baseline.get(row["card_id"], {})
    known = card.get("known_devices", set())
    if row["device_id"] not in known:
        return 0.5, f"New device {row['device_id']} never seen on this card before"
    return 0.0, ""


def rule_atypical_category(row, baseline: dict) -> tuple[float, str]:
    card = baseline.get(row["card_id"], {})
    typical = card.get("typical_categories", set())
    cat = row.get("merchant_category", "")
    if typical and cat and cat not in typical:
        return (
            0.3,
            f"Category '{cat}' is unusual for this card (typically: {', '.join(typical)})",
        )
    return 0.0, ""


def rule_cross_card_device(row, cross_card: dict) -> tuple[float, str]:
    device = row.get("device_id")
    if pd.isna(device) or not device:
        return 0.0, ""
    cards = cross_card.get("device_to_cards", {}).get(device, set())
    if len(cards) > 1:
        return (
            0.8,
            f"Device {device} used across {len(cards)} different cards. Possible account takeover.",
        )
    return 0.0, ""


def rule_cross_card_ip(row, cross_card: dict) -> tuple[float, str]:
    ip = row.get("ip_address")
    if pd.isna(ip) or not ip:
        return 0.0, ""
    cards = cross_card.get("ip_to_cards", {}).get(ip, set())
    if len(cards) > 1:
        return 0.7, f"IP {ip} used across {len(cards)} different cards"
    return 0.0, ""


def rule_velocity(
    row, df: pd.DataFrame, *, velocity_count: int | None = None
) -> tuple[float, str]:
    if velocity_count is None:
        card_txns = df[df["card_id"] == row["card_id"]].copy()
        card_txns["timestamp"] = pd.to_datetime(card_txns["timestamp"])
        ts = pd.to_datetime(row["timestamp"])
        window = card_txns[
            (card_txns["timestamp"] >= ts - timedelta(hours=1))
            & (card_txns["timestamp"] <= ts + timedelta(hours=1))
        ]
        count = len(window)
    else:
        count = velocity_count
    if count >= 6:
        return 0.8, f"{count} transactions on this card within 1 hour"
    if count >= 4:
        return 0.5, f"{count} transactions on this card within 1 hour"
    return 0.0, ""


def rule_odd_hours(row, baseline: dict) -> tuple[float, str]:
    ts = pd.to_datetime(row["timestamp"])
    hour = ts.hour
    if 2 <= hour <= 5:
        return 0.3, f"Transaction at {ts.strftime('%H:%M')} (unusual hours)"
    return 0.0, ""


def rule_gift_card_electronics(row) -> tuple[float, str]:
    cat = row.get("merchant_category", "")
    if cat in ("gift_card", "electronics") and row.get("channel") == "online":
        return 0.4, f"High-risk category '{cat}' via online channel"
    return 0.0, ""


def rule_merchant_burst(
    row, df: pd.DataFrame, *, unique_cards: int | None = None
) -> tuple[float, str]:
    merchant = row.get("merchant_name", "")
    if not merchant:
        return 0.0, ""

    if unique_cards is None:
        ts = pd.to_datetime(row["timestamp"])
        merchant_txns = df[df["merchant_name"] == merchant].copy()
        merchant_txns["timestamp"] = pd.to_datetime(merchant_txns["timestamp"])

        window = merchant_txns[
            (merchant_txns["timestamp"] >= ts - pd.Timedelta(hours=24))
            & (merchant_txns["timestamp"] <= ts + pd.Timedelta(hours=24))
        ]
        unique_cards = window["card_id"].nunique()

    merchant_lower = str(merchant).lower()
    suspicious = any(k in merchant_lower for k in _SUSPICIOUS_MERCHANT_KEYWORDS)

    if suspicious and unique_cards >= 5:
        return (
            0.95,
            f"Merchant '{merchant}' hit {unique_cards} different cards within 24 hours: possible merchant scam",
        )
    if unique_cards >= 8:
        return (
            0.75,
            f"Merchant '{merchant}' hit {unique_cards} different cards within 24 hours: possible merchant scam",
        )
    if unique_cards >= 7 and not suspicious:
        return (
            0.45,
            f"Merchant '{merchant}' hit {unique_cards} different cards within 24 hours",
        )
    return 0.0, ""


def rule_duplicate_charge(row, df: pd.DataFrame) -> tuple[float, str]:
    """Same card, merchant, and amount within 48 hours."""
    ts = pd.to_datetime(row.get("timestamp"))
    card = row.get("card_id")
    merchant = row.get("merchant_name") or row.get("merchant")
    amount = float(row.get("amount") or 0)
    if pd.isna(ts) or not card or not merchant or amount <= 0:
        return 0.0, ""
    window = df[
        (df["card_id"] == card)
        & (df["merchant_name"] == merchant)
        & (df["amount"].astype(float).round(2) == round(amount, 2))
    ].copy()
    window["timestamp"] = pd.to_datetime(window["timestamp"])
    dupes = window[
        (window["timestamp"] >= ts - pd.Timedelta(hours=48))
        & (window["timestamp"] <= ts + pd.Timedelta(hours=48))
    ]
    if len(dupes) >= 2:
        return (
            0.75,
            f"Duplicate ${amount:,.2f} charge at {merchant} within 48h on same card",
        )
    return 0.0, ""


def rule_round_number(row, baseline: dict) -> tuple[float, str]:
    """Suspiciously round amounts on high-value purchases."""
    amount = float(row.get("amount") or 0)
    if amount < 100:
        return 0.0, ""
    if amount % 100 == 0:
        return (
            0.35,
            f"Round-number amount ${amount:,.0f}. Common in fraud and split-charge patterns.",
        )
    if amount % 50 == 0 and amount >= 250:
        return 0.2, f"Round ${amount:,.0f} charge. Review for threshold splitting."
    return 0.0, ""


def rule_suspicious_merchant(
    row, baseline: dict, *, burst_cards: int = 0
) -> tuple[float, str]:
    """Known scam merchant names, especially when paired with cross-card bursts."""
    merchant = str(row.get("merchant_name") or "")
    merchant_lower = merchant.lower()
    if not merchant_lower:
        return 0.0, ""

    card = baseline.get(row["card_id"], {})
    median = float(card.get("median_amount") or 0)
    amount = float(row.get("amount") or 0)
    ratio = amount / median if median > 0 else 0

    for keyword in _SUSPICIOUS_MERCHANT_KEYWORDS:
        if keyword not in merchant_lower:
            continue
        if burst_cards >= 5 and ratio >= 2.5:
            return (
                0.95,
                f"Suspicious merchant '{merchant}' charged {burst_cards} cards within 24h at {ratio:.0f}x this card's median",
            )
        if burst_cards >= 5 and amount >= 250:
            return (
                0.9,
                f"Suspicious merchant '{merchant}' with ${amount:,.2f} charge across {burst_cards} cards in 24h",
            )
        if burst_cards >= 5:
            return 0.55, f"High-risk merchant '{merchant}' with multi-card activity"
        return 0.45, f"High-risk merchant name '{merchant}'"

    return 0.0, ""


def rule_card_testing(
    row, baseline: dict, *, velocity_count: int = 0
) -> tuple[float, str]:
    """Rapid small charges on a low-spend card. Common card-testing fraud pattern."""
    if velocity_count < 6:
        return 0.0, ""

    card = baseline.get(row["card_id"], {})
    median = float(card.get("median_amount") or 0)
    amount = float(row.get("amount") or 0)

    if median <= 60 and amount <= 200:
        return (
            0.9,
            f"Card testing: {velocity_count} charges within 1h on a low-spend card "
            f"(median ${median:.2f})",
        )
    if velocity_count >= 8:
        return 0.85, f"{velocity_count} transactions on this card within 1 hour"
    return 0.0, ""


def rule_foreign_high_amount(row, baseline: dict) -> tuple[float, str]:
    """Cross-border charge far above this card's normal spend."""
    card = baseline.get(row["card_id"], {})
    home = card.get("home_country", "")
    merchant_country = row.get("merchant_country", "")
    if not home or not merchant_country or home == merchant_country:
        return 0.0, ""

    median = float(card.get("median_amount") or 0)
    amount = float(row.get("amount") or 0)
    if median <= 0:
        return 0.0, ""

    ratio = amount / median
    if ratio >= 8 and amount >= 300:
        return (
            0.75,
            f"Foreign charge ${amount:,.2f} ({ratio:.0f}x median). Card from {home}, merchant in {merchant_country}.",
        )
    if ratio >= 4 and amount >= 500:
        return (
            0.55,
            f"Cross-border purchase ${amount:,.2f} well above this card's typical spend",
        )
    return 0.0, ""


def rule_atm_anomaly(row, baseline: dict) -> tuple[float, str]:
    """Large or unusual ATM withdrawals relative to card baseline."""
    if row.get("channel") != "atm" and row.get("merchant_category") != "atm":
        return 0.0, ""

    card = baseline.get(row["card_id"], {})
    median = float(card.get("median_amount") or 0)
    amount = float(row.get("amount") or 0)
    if median <= 0:
        return 0.0, ""

    ratio = amount / median
    if amount >= 500 or ratio >= 15:
        return 0.65, f"Unusual ATM withdrawal ${amount:,.2f} ({ratio:.1f}x card median)"
    return 0.0, ""
