# Fraud Hunter

A real-time fraud detection and review tool for credit card transactions. Built for MCP Hacks 2026 — Valsoft challenge.

---

## How to run

```bash
# 1. Clone and enter the project
cd fraud-hunter

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the server
uvicorn main:app --reload --port 8001

# 4. Open the reviewer UI
# http://localhost:8001
```

One command from a clean clone — no database, no config, no environment variables needed.

---

## What it does

Fraud Hunter ingests `transactions.csv` (1,000 transactions across 50 cards), scores every transaction for fraud using 10 detection rules, and presents flagged transactions in a keyboard-driven reviewer queue.

---

## Detection strategy

We identified 4 fraud patterns in the dataset through data analysis:

### Pattern 1 — Velocity attacks
Cards making 8–11 transactions within a single hour. Detected by counting transactions per card in a rolling 1-hour window. Cards flagged: card_023, card_038, card_042, card_049.

### Pattern 2 — Merchant burst (cross-card scam)
The same merchant (QuickPay Online) hitting 5 different cards within 24 hours, all at amounts 10–40× those cards' medians. This pattern is **invisible without cross-card aggregation** — no single-card rule would catch it. Detected by counting unique cards per merchant per time window.

### Pattern 3 — High-value electronics and gift cards
Stolen cards used to buy Apple Store, Newegg, AliExpress, Apple Gift Card, and Best Buy at amounts far above each card's baseline. Detected by per-card median + IQR baseline and flagging amounts above 10× median.

### Pattern 4 — Geographic anomaly
Transactions where the cardholder's country does not match the merchant's country. 262 cross-country transactions in the dataset — a subset are fraudulent, especially when combined with other signals.

### Scoring model

Every transaction is scored 0–1 by 10 rules. Scores are weighted and summed. Default threshold is 0.10.

| Rule | Signal | Weight |
|---|---|---|
| Amount anomaly | Amount vs. per-card median + IQR | 0.22 |
| Merchant burst | Same merchant hits 3+ cards in 24h | 0.22 |
| Cross-card device | Device ID reused across multiple cards | 0.18 |
| Cross-card IP | IP address reused across multiple cards | 0.12 |
| Foreign merchant | Cardholder country ≠ merchant country | 0.10 |
| Velocity | 4+ transactions on one card within 1 hour | 0.08 |
| New device | Online transaction from unknown device | 0.05 |
| Gift card / electronics | High-risk category via online channel | 0.03 |
| Atypical category | Category unusual for this card | 0.02 |
| Odd hours | Transaction between 2am–5am | 0.02 |

Every flagged transaction includes a plain-English explanation listing exactly which rules fired and why.

---

## Reviewer UI

- **Left panel** — flagged queue sorted by fraud score (highest risk first)
- **Right panel** — full transaction detail + explanation
- **Sensitivity slider** — drag to tune precision vs. recall in real time
- **Keyboard shortcuts:**
  - `A` — Approve (legitimate)
  - `D` — Dismiss (false positive — suppresses similar flags on same card)
  - `E` — Escalate (needs investigation)
  - `Z` — Undo last action
  - `↑ ↓` — Navigate queue
- **Export CSV** — downloads updated transaction file with fraud scores and review decisions

### Feedback loop
When a reviewer dismisses a flag, the system reduces scores of similar transactions on the same card by 15%, suppressing false positives without a full re-run.

---

## Tests

```bash
pytest tests/test_detector.py -v
```

Tests cover a known fraud case (new device, foreign merchant, high amount, odd hours) and a known legitimate case (small in-person restaurant charge).

---

## What we'd do with another week

1. **Train a proper model.** With labeled data (from reviewer decisions), we'd train a gradient boosting classifier on the rule scores as features. The rules become features, not the final decision.
2. **Time-series baselines.** Current baselines are static (whole history). Better: rolling 30-day window so the model adapts to changing spending patterns.
3. **Merchant risk registry.** Track which merchants have historically generated fraud across all cards. QuickPay Online would be permanently high-risk.
4. **Persistent audit trail.** Every reviewer decision logged with timestamp, reviewer ID, and reasoning — exportable for compliance.
5. **Real-time streaming.** Move from batch CSV to a Kafka stream so flags fire within seconds of a transaction.
6. **Card network graph.** Build a graph of cards connected by shared devices/IPs. Community detection on this graph would surface fraud rings invisible to per-card rules.
