# Implementation Plan — Fraud Hunter

## Architecture

```
transactions.csv
      │
      ▼
detector/baseline.py    ← per-card behavioral profiles
detector/rules.py       ← 10 independent scoring rules
detector/scorer.py      ← combines rules into final score + explanation
      │
      ▼
api/routes.py           ← FastAPI: /api/flagged, /api/review, /api/threshold, /api/export
      │
      ▼
frontend/index.html     ← single-page reviewer UI (vanilla JS, no framework)
```

No database. All state lives in a single in-memory Pandas DataFrame for the session. Fast, simple, zero infrastructure.

---

## Tech choices

| Choice | Reason |
|---|---|
| **Python + Pandas** | Fast data analysis, rich statistical functions for baselines |
| **FastAPI** | Async, automatic docs, minimal boilerplate |
| **Vanilla JS** | No build step, no npm, judges can read the source directly |
| **No ML model** | No labeled data, rules are interpretable, faster to build and explain |
| **No database** | Session-only state, one-command run, no setup friction |

---

## How the pieces fit together

**1. Baseline building (`baseline.py`)**
On first request, we profile every card: median spend, IQR, top-3 categories, known devices, known IPs, home country. These become the reference point for every anomaly rule.

**2. Rule evaluation (`rules.py`)**
10 functions, each taking a row + context (baselines or full DataFrame) and returning a `(score, reason)` tuple. Rules are independent — adding or removing one doesn't break the others.

**3. Score combination (`scorer.py`)**
Weighted sum of rule scores, capped at 1.0. Threshold applied to produce a boolean `flagged` column. The threshold is tunable at runtime via the API without re-reading the CSV.

**4. API (`routes.py`)**
Five endpoints:
- `GET /api/flagged` — returns flagged transactions sorted by score
- `GET /api/stats` — aggregate counts for the header
- `POST /api/review` — records approve/dismiss/escalate, runs feedback loop on dismiss
- `POST /api/undo` — pops the undo stack and restores previous status
- `POST /api/threshold` — re-scores with new threshold, resets DataFrame
- `GET /api/export` — writes updated CSV and serves it

**5. Frontend (`frontend/index.html`)**
Single HTML file, no build step. Fetches from the API on load, renders the queue and detail panel, handles keyboard events. State lives in the API — the frontend is stateless.

---

## Detection strategy — the 4 patterns

| Pattern | Rule | Signal |
|---|---|---|
| Velocity attack | `rule_velocity` | 4+ transactions per card within 1 hour |
| Merchant burst | `rule_merchant_burst` | Same merchant hits 3+ cards within 24 hours |
| High-value purchases | `rule_amount_anomaly` | Amount > 10× per-card median |
| Geographic anomaly | `rule_foreign_merchant` | Cardholder country ≠ merchant country |

The merchant burst pattern is only detectable with cross-card aggregation — no per-card rule would surface it.

---

## What we decided to skip and why

| Skipped | Reason |
|---|---|
| ML classifier | No labeled training data; rules are more interpretable for a 24h demo |
| Database persistence | Adds setup friction; in-memory is fine for session-based review |
| Authentication | Single reviewer, single session — out of scope |
| Real-time streaming | Batch CSV ingestion is sufficient for the dataset size |
| Card network graph | Would improve fraud ring detection but takes more time than it's worth at 24h |

---

## Work division

| Area | Owner |
|---|---|
| Detection rules + scoring | Backend |
| FastAPI routes + feedback loop | Backend |
| Reviewer UI + keyboard nav | Frontend |
| Data analysis + pattern discovery | Data |
| README + PRD + implementation plan | All |

---

## Reproducibility

```bash
pip install -r requirements.txt
uvicorn main:app --port 8001
# open http://localhost:8001
```

No environment variables. No database. No secrets. Works from a clean clone in under 2 minutes.
