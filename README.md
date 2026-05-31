# CashFlux

AI-powered expense intelligence for finance teams  built for the Brim Financial ù MPC Hacks hackathon.

## Quick start

```bash
pip install -r requirements.txt
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000)

**Demo admin:** `e001@northwind-analytics.local` / `1234`

Set `GEMINI_API_KEY` in `.env` for chat, voice, OCR, and policy import.

## Project layout

| Path | Purpose |
|------|---------|
| `app.py` | Flask app, routes, auth |
| `policy_engine.py` | Spending policy rules & violation scanning |
| `workflow_data.py` | Pre-approval queue & trip expense reports |
| `friday_agent.py` / `voice_assistant.py` | Friday AI assistant |
| `guardian_data.py` | Transaction CSV loading & caches |
| `data/companies/<slug>/` | Per-company transactions, budgets, receipts |
| `static/` / `templates/` | Frontend |
| `docs/` | Hackathon brief & capability mapping |
| `mpc-hacks/brim-guardian/` | Optional Brim Guardian agent integration |
| `seed_users.py` | CLI to seed employee login accounts from CSV roster |

## Utilities

```bash
python seed_users.py          # Create employee accounts for Northwind demo
```

See [docs/CAPABILITIES.md](docs/CAPABILITIES.md) for hackathon requirement coverage.

## Fraud Hunter (Valsoft challenge)

The app includes a Fraud Hunter-compatible detector for `data/fraud_hunter/transactions.csv`:

```bash
python scripts/tune_fraud_scorer.py          # Offline precision/recall check
python -m unittest tests.test_fraud_detector -v
```

Flags appear in **Review queue** with keyboard triage (A/D/E/U) and a threshold slider. Export reviewed CSV via the admin UI or `GET /api/fraud/export`.

See [docs/FRAUD_HUNTER.md](docs/FRAUD_HUNTER.md) for detection strategy and hypothesis log.
