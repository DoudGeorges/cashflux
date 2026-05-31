# CashFlux — Hackathon Capability Map

This document maps the **Brim Financial × MPC Hacks** brief to implemented features in CashFlux.

See also: [hackathon-brief.md](./hackathon-brief.md)

---

## Required Capabilities (4/4)

### 1. Talk to Your Data — Conversational Data Explorer

| What judges want | CashFlux implementation |
|---|---|
| Plain-English Q&A with charts/tables | **Friday** chat (`/api/chat`, `spending_query.py`) — bar, line, doughnut charts via Chart.js when a visual helps |
| Follow-ups across departments, time, categories | Conversation history in `spending_query.py` + `build_gemini_context()` in `expense_data.py` |
| Agentic actions (navigate, approve, budgets) | `friday_agent.py` + `friday_tools.py` — Gemini function calling |

**Try it:** Home → **Ask Friday** — e.g. *"What did Marketing spend on software last quarter?"* then *"How does that compare to Engineering?"*

---

### 2. Policy Compliance Engine

| What judges want | CashFlux implementation |
|---|---|
| Digitized policy rules (dept + role) | **Settings → Spending rules** (`policy_engine.py`, `POLICY_SCHEMA`) |
| Auto-scan transactions | Policy rescan on load; flags in **See problems** (`/api/flags`) |
| Context-aware rules (team vs solo meals) | Team-meal co-charge detection, receipt party size, role overrides |
| Split-transaction / threshold evasion | `split_transaction` rule in policy engine |
| Repeat offenders + severity ranking | Guardian credit scores, risk labels (Severe/High/Medium/Low) |

**Try it:** Settings → edit `solo_meal_limit` / `approval_threshold` → **See problems** for flagged purchases.

---

### 3. AI Pre-Approval Workflow

| What judges want | CashFlux implementation |
|---|---|
| Approver notification | Home **approver inbox** banner + nav badges (`/api/nav`) |
| Full decision package | **Review queue** — employee history, budget context, policy problems |
| AI approve/deny + reasoning | `workflow_data.build_ai_recommendation()` on expense requests |
| One-touch decision | Approve/Deny in Review (`/api/review/action`) — keyboard shortcuts A/D |

**Try it:** **Review queue** → filter **Requests** → read AI brief → Approve or Deny.

---

### 4. Automated Expense Report Generation

| What judges want | CashFlux implementation |
|---|---|
| Group related transactions | Trip reports auto-built from travel clusters (`workflow_data.py`) |
| Real-time policy checks | Per-report violations + policy summary |
| Built-in approval workflow | Reports in **Review queue** (filter **Reports**) + **Trip reports** page |
| AI recommendation for CFO | `build_trip_report_recommendation()` — `ai_brief`, `ai_recommendation`, `ai_context` |

**Try it:** **Review queue** → **Reports** → CFO Approve, or **Trip reports** → View report.

---

## Optional Capabilities

| Brief item | Status | Where |
|---|---|---|
| Anomaly & fraud detection | ✅ | **Review → Fraud**; duplicate charges, round-number patterns, geo/channel rules (`fraud_detector/`) |
| Department budget tracking + overrun alerts | ✅ | **Check budgets** — caps, burn rate, projection chart (`budget_data.py`) |
| Receipt matching + policy | ✅ | **Receipts** (employees) — OCR upload, dining party size, colleague attribution |
| Vendor consolidation | ✅ | **Check budgets → Vendor consolidation**; Friday Q&A; `/api/vendor-consolidation` |
| Employee profiles + peer benchmarking | ✅ | **People** → click employee → peer benchmark panel (`peer_benchmark.py`) |
| Forecasting | ✅ | Budget projections + Friday *"At this burn rate…"* queries |
| Surprise us | ✅ | **Spending Oracle** — type *"surprise me"* in Friday, Konami code, or 7× logo click |

---

## Judging Criteria Alignment

| Criterion | How CashFlux addresses it |
|---|---|
| **Required features (/6)** | All four pillars wired end-to-end with real transaction data |
| **Optional / creativity (/6)** | Fraud engine, forecasts, vendor consolidation, peer benchmarks, Spending Oracle |
| **AI depth (/4)** | Multi-tool Friday agent, contextual policy reasoning, trip report + approval recommendations |
| **UI / UX (/4)** | Finance-manager-first nav, Review queue, inbox banner, charts only when useful |

---

## Key Routes & Files

| Area | API / UI | Backend |
|---|---|---|
| Friday chat | `#insight-chat` | `app.py`, `spending_query.py`, `friday_agent.py` |
| Review queue | `#insight-approvals` | `review_data.py`, `/api/review/queue` |
| Policy | Settings → Rules | `policy_engine.py` |
| Budgets & forecast | `#insight-budget` | `budget_data.py` |
| Trip reports | `#insight-reports` | `workflow_data.py` |
| Fraud | Review → Fraud | `fraud_detector/` |
| Vendor consolidation | Budget page | `vendor_consolidation.py` |
| Peer benchmark | People modal | `peer_benchmark.py` |

---

## Demo Login

- **Admin (CFO):** `e001@northwind-analytics.local` / `1234`
- **Run:** `python app.py` → http://localhost:5000
