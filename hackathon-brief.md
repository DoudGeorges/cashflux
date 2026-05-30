# Brim Financial × MPC Hacks — Hackathon Brief

> **Challenge:** Build an AI-powered expense intelligence platform for small & medium businesses (SMBs) using real, anonymized transaction data.

---

## Problem

SMBs generate thousands of card transactions monthly but lack the tools to understand their own spending. Brim wants to change that.

## Mission

Build an AI-powered platform on top of real SMB transaction data. **Make the data talk.**

## Provided Data

| Asset | Description |
|---|---|
| Transaction data | 6 months of anonymized transactions from a real SMB client (~50 employees, multiple departments, thousands of transactions) |
| Expense policy document | Defines spend limits, approval thresholds, allowed categories, and restricted merchants |

---

## Required Capabilities

All four capabilities below must be implemented.

### 1. Conversational Data Explorer

A natural-language interface that lets a finance manager query company spending and receive contextual answers with appropriate visualizations (charts, tables, summaries). Must support multi-turn conversations that reason across departments, time periods, and categories.

> **Examples:**
> - *"What did marketing spend on software last quarter?"* → bar chart + summary
> - *"How does that compare to engineering?"* → updated comparison, preserving conversational context

### 2. Policy Compliance Engine

A digitized expense-policy management system where the finance team defines spending rules per department and role. The system automatically scans transactions against active policies and flags violations. The AI must understand **context, not just rules** — a $200 team dinner differs from a $200 solo dinner. It should surface repeat offenders and rank violations by severity.

> **Example:**
> Flag an employee splitting a $600 purchase into two $300 charges to circumvent a $500 approval threshold.

### 3. AI Pre-Approval Workflow

When a transaction requires approval, the system notifies the designated approver with a complete decision package: the request details, the employee's spending history, department budget status, and an AI-generated approve/deny recommendation with reasoning. One-touch decision — no back-and-forth.

> **Example:**
> *"Sarah from Marketing is requesting $1,200 for a conference registration. Her department has $3,400 remaining in Q2 budget. She attended 2 conferences this year. **Recommendation: Approve** — within policy, aligns with past pattern."*

### 4. Automated Expense Report Generation

Automatically group related transactions into intelligent expense reports with real-time policy checks and built-in approval workflows.

> **Example:**
> Sarah's San Diego conference generated 10 transactions, all auto-grouped into a single expense report — linked to spend categories and ready for CFO approval alongside policy compliance recommendations.

---

## Optional Capabilities

Implement any of the following, or invent your own:

| Capability | Description |
|---|---|
| Anomaly & fraud detection | Duplicate charges, round-number patterns, unusual merchant activity |
| Budget tracking | Department-level tracking with projected overrun alerts |
| Receipt matching | Automated receipt-to-transaction matching with policy compliance checks |
| Vendor consolidation | *"You're paying 4 coffee vendors — here's what you'd save consolidating"* |
| Spending profiles | Employee spending profiles and peer benchmarking |
| Forecasting | *"At this burn rate, marketing will exceed Q3 budget by week 8"* |
| Surprise us | If you see something in the data we didn't think of — build it |

---

## Judging Criteria

> **Quality over quantity.** Two features that work beautifully beat six that half-work. Depth and polish win over breadth.

| Criterion | Points | What Judges Are Looking For |
|---|---|---|
| Required features | /6 | Do all four work? Are they genuinely useful? |
| Optional features / creativity | /6 | Did the team go beyond the brief? Discover something unexpected in the data? |
| AI depth | /4 | Multi-step reasoning, agentic workflows, contextual understanding — not single-prompt wrappers |
| UI / UX | /4 | Does the platform make a non-technical finance manager smarter? Visualizations that clarify, not decorate |
| **Total** | **/20** | |
