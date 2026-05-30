"""
Fraud detection rules. Each rule returns a (score, reason) tuple.
score is 0.0 (clean) to 1.0 (very suspicious).
"""
import pandas as pd
from datetime import timedelta


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
        return 0.9, f"Amount ${amount:.2f} is {ratio:.1f}× this card's median (${median:.2f})"
    if amount > p95 and ratio >= 3:
        return 0.6, f"Amount ${amount:.2f} is {ratio:.1f}× this card's median (${median:.2f})"
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
        return 0.3, f"Category '{cat}' is unusual for this card (typically: {', '.join(typical)})"
    return 0.0, ""


def rule_cross_card_device(row, cross_card: dict) -> tuple[float, str]:
    device = row.get("device_id")
    if pd.isna(device) or not device:
        return 0.0, ""
    cards = cross_card.get("device_to_cards", {}).get(device, set())
    if len(cards) > 1:
        return 0.8, f"Device {device} used across {len(cards)} different cards — possible account takeover"
    return 0.0, ""


def rule_cross_card_ip(row, cross_card: dict) -> tuple[float, str]:
    ip = row.get("ip_address")
    if pd.isna(ip) or not ip:
        return 0.0, ""
    cards = cross_card.get("ip_to_cards", {}).get(ip, set())
    if len(cards) > 1:
        return 0.7, f"IP {ip} used across {len(cards)} different cards"
    return 0.0, ""


def rule_velocity(row, df: pd.DataFrame) -> tuple[float, str]:
    card_txns = df[df["card_id"] == row["card_id"]].copy()
    card_txns["timestamp"] = pd.to_datetime(card_txns["timestamp"])
    ts = pd.to_datetime(row["timestamp"])
    window = card_txns[
        (card_txns["timestamp"] >= ts - timedelta(hours=1)) &
        (card_txns["timestamp"] <= ts + timedelta(hours=1))
    ]
    count = len(window)
    if count >= 6:
        return 0.8, f"{count} transactions on this card within 1 hour"
    if count >= 4:
        return 0.5, f"{count} transactions on this card within 1 hour"
    return 0.0, ""


def rule_odd_hours(row, baseline: dict) -> tuple[float, str]:
    ts = pd.to_datetime(row["timestamp"])
    hour = ts.hour
    if 2 <= hour <= 5:
        return 0.3, f"Transaction at {ts.strftime('%H:%M')} — unusual hours"
    return 0.0, ""


def rule_gift_card_electronics(row) -> tuple[float, str]:
    cat = row.get("merchant_category", "")
    if cat in ("gift_card", "electronics") and row.get("channel") == "online":
        return 0.4, f"High-risk category '{cat}' via online channel"
    return 0.0, ""


def rule_merchant_burst(row, df: pd.DataFrame) -> tuple[float, str]:
    """
    Detects when the same merchant hits multiple different cards in a short window.
    This is the cross-card merchant scam pattern — invisible without looking across cards.
    """
    merchant = row.get("merchant_name", "")
    if not merchant:
        return 0.0, ""

    ts = pd.to_datetime(row["timestamp"])
    merchant_txns = df[df["merchant_name"] == merchant].copy()
    merchant_txns["timestamp"] = pd.to_datetime(merchant_txns["timestamp"])

    window = merchant_txns[
        (merchant_txns["timestamp"] >= ts - pd.Timedelta(hours=24)) &
        (merchant_txns["timestamp"] <= ts + pd.Timedelta(hours=24))
    ]
    unique_cards = window["card_id"].nunique()

    if unique_cards >= 5:
        return 0.9, f"Merchant '{merchant}' hit {unique_cards} different cards within 24 hours — possible merchant scam"
    if unique_cards >= 3:
        return 0.5, f"Merchant '{merchant}' hit {unique_cards} different cards within 24 hours"
    return 0.0, ""
