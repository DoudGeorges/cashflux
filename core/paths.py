"""Shared paths for CashFlux data and policy configuration."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

# Default demo company (CLI scripts); runtime reads use company_data.get_company_paths().
_DEFAULT_COMPANY = DATA_DIR / "companies" / "northwind-analytics"
ORIGINAL_TX_PATH = _DEFAULT_COMPANY / "transactions_original.csv"
SCORED_TX_PATH = _DEFAULT_COMPANY / "transactions_scored.csv"
EMPLOYEE_SCORES_PATH = _DEFAULT_COMPANY / "employee_scores_summary.csv"
FLAGGED_TX_PATH = _DEFAULT_COMPANY / "flagged_transactions.csv"
DEPARTMENT_SUMMARY_PATH = _DEFAULT_COMPANY / "department_summary.csv"
CSV_NAME = SCORED_TX_PATH.name

# Map geocoding caches (shared across companies)
LOCATION_COORDS_PATH = DATA_DIR / "location_coords.json"
POSTAL_COORDS_PATH = DATA_DIR / "postal_coords.json"
STREET_COORDS_PATH = DATA_DIR / "street_coords.json"

# Policy & budgets (app-level config)
RULES_PATH = ROOT / "policy" / "policy_rules.json"
POLICY_DOC_PATH = ROOT / "policy" / "policy_document.md"
