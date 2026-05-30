# Brim Guardian — Expense Intelligence Agent

Feature 2 chatbot: answers any question about company spending, generates charts, and reports employee credit scores. Powered by **Gemini 2.0 Flash** (function calling) + **MongoDB Atlas** + **ElevenLabs** TTS.

---

## Folder structure

```
brim-guardian/
├── main.py              FastAPI entry point  →  uvicorn main:app --reload
├── requirements.txt
├── .env.example         Copy to .env and fill in keys
│
├── agent/
│   ├── core.py          BrimAgent — multi-turn Gemini chat + tool loop
│   └── tools.py         Tool declarations + async dispatcher
│
├── db/
│   ├── connection.py    Motor async MongoDB client
│   ├── models.py        Pydantic schemas for all collections
│   ├── queries.py       MongoDB aggregation queries
│   └── seed.py          Dev seed — 300 fake transactions, 8 employees
│
├── charts/
│   ├── generator.py     matplotlib → PNG (bar, comparison, line, table)
│   └── output/          Generated PNGs (gitignored)
│
├── voice/
│   ├── narrator.py      ElevenLabs TTS → MP3
│   └── output/          Generated audio (gitignored)
│
└── api/
    └── routes.py        POST /api/chat · GET /api/chart/{file} · GET /api/health
```

---

## Quick start

```bash
# 1. Copy and fill in API keys
cp .env.example .env

# 2. Virtual env + install
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Seed the database (dev only)
python -m db.seed

# 4. Run
uvicorn main:app --reload
# → http://localhost:8000
```

---

## API

### POST /api/chat
```json
{ "message": "What did Marketing spend on software last quarter?", "narrate": false }
```
Response:
```json
{
  "text": "Marketing spent $12,400 on software in Q1...",
  "chart_paths": ["./charts/output/abc123.png"],
  "audio_path": null,
  "tool_calls": ["get_spending_by_department", "generate_bar_chart"]
}
```
Set `"narrate": true` to also get an ElevenLabs MP3.

### GET /api/chart/{filename}
Serves a generated PNG.

### GET /api/chat/reset
Clears conversation history.

---

## How the agent works

```
User message
    │
    ▼
BrimAgent (Gemini 2.0 Flash + function calling)
    │
    ├─► get_spending_by_department  → MongoDB aggregation
    ├─► get_top_vendors             → MongoDB aggregation
    ├─► get_employee_credit_score   → MongoDB employee doc
    ├─► get_monthly_trend           → MongoDB aggregation
    ├─► get_department_budget       → MongoDB budget doc
    ├─► generate_bar_chart          → matplotlib PNG
    ├─► generate_comparison_chart   → matplotlib PNG
    └─► generate_ranked_table       → matplotlib PNG
    │
    ▼
Text reply + chart PNG paths + optional MP3
```

**Multi-turn**: history is kept per `BrimAgent` instance, so "how does that compare to Engineering?" works after "what did Marketing spend on software?".

---

## Example questions

| Question | Tools called |
|---|---|
| "What did Marketing spend on software last quarter?" | `get_spending_by_department` → `generate_bar_chart` |
| "How does that compare to Engineering?" | `get_spending_by_department` → `generate_comparison_chart` |
| "Who are our top 5 vendors this month?" | `get_top_vendors` → `generate_ranked_table` |
| "What's Sarah Chen's credit score?" | `get_employee_credit_score` |
| "Show me Sales spending trends over 6 months" | `get_monthly_trend` → `generate_bar_chart` |
| "How much budget does Marketing have left in Q2?" | `get_department_budget` |

---

## MongoDB collections

| Collection | Purpose |
|---|---|
| `transactions` | One doc per expense charge |
| `employees` | Profile + credit score (0–100) |
| `flags` | Policy violations, geofencing, fraud alerts |
| `budgets` | Dept quarterly budget vs. spent |

## Credit score model

Starts at **100**, deducted per violation:

| Violation | Deduction |
|---|---|
| Meal > $75/person | -12 |
| Split purchase | -15 |
| Geofencing alert | -20 |

---

## Connecting to other features

This module is **read-only** against shared MongoDB collections. Feature 6 (receipt OCR) writes to `transactions`; this agent can immediately answer questions about those receipts. Feature 1 (flagging) writes to `flags`; this agent can surface them via `get_employee_credit_score`.
