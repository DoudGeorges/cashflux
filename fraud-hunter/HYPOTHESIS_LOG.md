# Hypothesis Log

What we tried, what worked, what we dropped, and why.

---

## Data exploration

**Hypothesis:** The dataset contains distinct fraud clusters, not random noise.

**Finding:** Yes — four clear patterns emerged from EDA:
1. `card_023`, `card_038`, `card_042`, `card_049` — each with 8–11 transactions within 1 hour
2. `QuickPay Online` — hit 5 different cards within 24 hours, all at 10–40× median amounts
3. `Apple Store`, `Newegg`, `Apple Gift Card`, `AliExpress`, `Best Buy` — high-value electronics/gift cards across multiple cards at amounts far above baseline
4. 262 cross-country transactions (cardholder country ≠ merchant country)

**Decision:** Build rules targeting each pattern specifically rather than a generic anomaly detector.

---

## Rule: Amount anomaly

**Hypothesis:** Fraudsters spend more than a card's typical amount.

**Implementation:** Per-card median + IQR baseline. Flag if amount > p95 × 2 and ratio ≥ 5× (score 0.9), or > p95 and ratio ≥ 3× (score 0.6).

**Result:** Catches pattern 3 (high-value electronics) cleanly. Also fires on some legitimate large purchases — mitigated by requiring other signals to also fire for high confidence.

**Kept.**

---

## Rule: Merchant burst

**Hypothesis:** A fraudulent merchant will hit many cards in a short window — a signal invisible to per-card rules.

**Implementation:** Count unique cards per merchant in a ±24-hour window. Score 0.9 if 5+ cards, 0.5 if 3+ cards.

**Result:** Directly catches the QuickPay Online cluster (5 cards, sequential transaction IDs tx_000995–tx_000999). This was the hardest pattern to find — required cross-card aggregation.

**Kept. Highest-weight rule alongside amount anomaly.**

---

## Rule: Cross-card device reuse

**Hypothesis:** Account takeover attacks reuse the same device across stolen cards.

**Implementation:** Build a device→cards map. Flag if device appears on 2+ cards (score 0.8).

**Result:** Only 0 devices shared across cards in this dataset. Rule exists and works correctly but doesn't fire much on this data. Still valuable — would catch account takeover in production.

**Kept (future-proof).**

---

## Rule: Cross-card IP reuse

**Hypothesis:** Same IP used across multiple cards signals a coordinated attack.

**Implementation:** Same as device reuse but for IP addresses.

**Result:** One IP (99.225.114.61) shared across 2 cards. Small signal but meaningful.

**Kept.**

---

## Rule: Velocity

**Hypothesis:** Rapid card testing — many small transactions in a short window before a big purchase.

**Implementation:** Count transactions per card in a rolling 1-hour window. Flag if 4+ (score 0.5) or 6+ (score 0.8).

**Result:** Directly catches cards 023, 038, 042, 049. Strong signal, low false positive rate.

**Kept.**

---

## Rule: Foreign merchant

**Hypothesis:** Card used in a different country than the cardholder is suspicious.

**Implementation:** Compare `cardholder_country` vs `merchant_country`. Score 0.5 on mismatch.

**Result:** 262 transactions — too many to be all fraud. Works best combined with other signals (amount anomaly + foreign = high confidence). Alone it's noisy.

**Kept but given moderate weight (0.10).**

---

## Rule: New device

**Hypothesis:** Online transaction from a device never seen on this card is suspicious.

**Implementation:** Build per-card set of known devices. Flag if current device not in set.

**Result:** Fires correctly but baseline is built from all transactions including current one — slightly optimistic. In production, baseline should be built from historical data only.

**Kept. Known limitation documented.**

---

## Rule: Odd hours

**Hypothesis:** Fraud often happens at unusual hours (2am–5am).

**Result:** Low signal in this dataset. Fires on a few transactions but rarely in combination with other high-weight rules. Low weight (0.02).

**Kept as a tiebreaker.**

---

## What we dropped

**Absolute amount threshold (e.g. flag everything over $500):** Too many false positives. A card that regularly buys $800 flights shouldn't be flagged for a $500 charge. Per-card baseline is strictly better.

**Merchant category alone as a signal:** `gift_card` and `electronics` are suspicious in isolation, but only when online. Combined with channel filter and kept as a low-weight signal.

**Round number detection:** Considered flagging amounts like $500.00 or $1,000.00 as possible fabricated receipts. Not enough signal in this dataset to justify the false positive cost.
