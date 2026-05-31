# Fraud Hunter — Detection Strategy

CashFlux embeds a **Fraud Hunter**-compatible detector for the Valsoft MPC Hacks challenge. It scores `data/fraud_hunter/transactions.csv` (1,000 rows, 50 cards) and surfaces flags in the **Review queue** with keyboard triage.

## How to run

```bash
python app.py
# Admin login → Review queue → filter Fraud alerts
# Adjust threshold slider → Export reviewed CSV via /api/fraud/export
```

Offline evaluation:

```bash
python scripts/tune_fraud_scorer.py
python -m unittest tests.test_fraud_detector -v
```

## Detection strategy

### Per-card baselines (`fraud_detector/baseline.py`)

For each `card_id` we compute median amount, IQR, p95, typical categories/channels, home country, and known devices/IPs. Anomalies are measured **relative to the card**, not absolute dollar thresholds.

### Cross-card signals

| Pattern | Rule | Why it matters |
|---------|------|----------------|
| Merchant scam | `rule_merchant_burst` + `rule_suspicious_merchant` | QuickPay Online hits 8 cards in 24h — invisible per-card |
| Account takeover | `rule_cross_card_device`, `rule_cross_card_ip` | Same device/IP across cards |
| Card testing | `rule_card_testing` + `rule_velocity` | 6–11 rapid small charges (cards 023, 038, 042, 049) |
| High-value fraud | `rule_amount_anomaly` + category rules | Apple Store / Newegg / gift cards at 10–50× median |

### Scoring (`fraud_detector/scorer.py`)

Rules return `(score, human-readable reason)` pairs. We combine them with a **hybrid scorer**:

- Strong critical signals (≥0.80) flag on their own — e.g. card testing, QuickPay burst.
- Supporting signals (foreign country, odd hours) boost confidence without dominating.
- Default threshold: **0.45** (~7% flagged, tuned for precision/recall balance).

Every flagged row includes an `explanation` like:

> Amount $735.44 is 36.8× this card's median ($19.99) | Merchant 'QuickPay Online' hit 8 different cards within 24 hours

### Reviewer workflow

- One-at-a-time queue with **A** approve, **D** dismiss, **E** escalate, **U** undo
- Threshold slider retunes flag volume (cost of false positive vs missed fraud)
- Dismissals suppress similar pending flags within the session (feedback loop)

### Deliverables

- **Flagged CSV export**: `GET /api/fraud/export` adds `fraud_flagged` and `fraud_review_status` columns
- **Tests**: `tests/test_fraud_detector.py` — QuickPay burst, velocity card testing, grocery baseline
- **Hypothesis log**: see below

## Hypothesis log (summary)

| Rule | Tried | Result |
|------|-------|--------|
| Weighted sum only | Initial | Max score 0.37 — **zero flags** at threshold 0.40 |
| Hybrid critical-or scorer | v2 | Strong signals flag alone; F1 ~0.92 on proxy labels |
| Merchant burst ≥3 cards | v1 | Too many FPs on Starbucks, Disney+, etc. |
| Merchant burst ≥8 (≥5 for QuickPay) | v3 | Keeps QuickPay scam, drops chain-restaurant noise |
| Foreign country alone | v1 | 262 txns — too noisy; kept as low-weight booster |
| Absolute $500 threshold | Rejected | False positives on legitimate large purchases |

## If we had another week

- Temporal baselines (train on days 1–20, score days 21–30) to fix new-device leakage
- Learn dismissed patterns into rule weights persistently (SQLite audit log)
- SHAP-style feature attribution per flag for demo polish
- Separate Fraud Hunter tab with 1,000-row filter/search instead of mixed review queue
