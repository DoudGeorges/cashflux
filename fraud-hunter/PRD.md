# Product Requirements Document — Fraud Hunter

## Who is the user?

A **fraud analyst** on the trust and safety team at a payments company. They review flagged transactions daily, making approve/dismiss/escalate decisions. They are not a data scientist — they don't read model weights or probability distributions. They need clear reasons, fast navigation, and confidence that they're seeing the highest-risk items first.

Secondary user: a **fraud operations manager** who wants aggregate visibility — how many flags today, what patterns are emerging, which cards are repeat offenders.

---

## What problem are we solving?

Every day, thousands of transactions flow through the system. A small fraction (~7%) are fraudulent. The analyst cannot review every transaction by hand. Without tooling, they either:

- **Over-block** — flag too many legitimate transactions, frustrating customers and generating chargebacks
- **Under-block** — miss fraud, costing the company money and eroding cardholder trust

The core tension: **false positives cost customers; false negatives cost money.** The tool must let the analyst tune this trade-off in real time.

---

## What does success look like?

**Detection quality:**
- F1 score above 0.85 on the hidden answer key
- Precision high enough that the reviewer isn't drowning in false positives
- All 4 fraud patterns in the dataset caught by at least one rule

**Reviewer experience:**
- A non-technical person can sit down with no instructions and complete a review session
- Median time-to-decision per transaction under 10 seconds
- Keyboard-driven — no mouse required for core workflow
- Undo available — reviewer is never afraid to make a wrong decision

**Engineering:**
- One-command run from a clean clone
- At least one meaningful automated test
- Code a teammate could read and extend

---

## What are we explicitly NOT building?

- **A machine learning model.** Rules are interpretable, fast to build, and easy to explain to a judge or regulator. An ML model would improve recall but sacrifice explainability and would require labeled training data we don't have.
- **A database.** State is in-memory per session. Persistence across restarts is out of scope.
- **Authentication or multi-user support.** Single reviewer per session.
- **Real-time streaming.** Batch CSV ingestion only. Kafka/streaming is a week-2 problem.
- **Automatic blocking.** The tool surfaces flags; humans make decisions. No automated card blocks.
- **A mobile interface.** Desktop browser only.

---

## Core requirements

| # | Requirement | Priority |
|---|---|---|
| 1 | Ingest transactions.csv and score all 1,000 rows | Must |
| 2 | Flag suspicious transactions with a 0–1 score | Must |
| 3 | Every flag includes a plain-English explanation | Must |
| 4 | Reviewer can approve, dismiss, escalate each flag | Must |
| 5 | Keyboard navigation (A/D/E/Z/arrows) | Must |
| 6 | Undo last action | Must |
| 7 | Sensitivity slider — adjust threshold in real time | Must |
| 8 | Export updated CSV with fraud scores and decisions | Must |
| 9 | Per-card behavioral baselines | Must |
| 10 | Cross-card aggregation (merchant burst, device/IP reuse) | Must |
| 11 | Feedback loop — dismissals suppress similar future flags | Should |
| 12 | Audit trail of reviewer decisions | Should |
| 13 | Hypothesis log | Nice to have |

---

## Key design decisions

**Rule-based scoring over ML.** With 24 hours and no labeled data, rules give us interpretability, speed, and the ability to explain every decision. Each flag says exactly which rule fired and why — something a black-box model cannot do.

**Weighted sum over hard rules.** No transaction is blocked on a single rule. Scores combine — a foreign merchant alone is low risk, but foreign merchant + new device + high amount + odd hours = high risk. This reduces false positives significantly.

**Threshold as a first-class control.** The sensitivity slider is not a nice-to-have — it is the primary cost lever. Moving it left reduces false positives (more precise, misses some fraud). Moving it right increases recall (catches more fraud, more false positives). The reviewer should set this based on the current business cost of each error type.
