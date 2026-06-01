"""Per-company CSV and JSON data paths with request-scoped context."""

from __future__ import annotations

import contextvars
import csv
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from core.paths import DATA_DIR

DEFAULT_COMPANY_SLUG = "northwind-analytics"

_company_id: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "company_id", default=None
)
_company_slug: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "company_slug", default=None
)

LEGACY_FILES = (
    "transactions_original.csv",
    "transactions_scored.csv",
    "employee_scores_summary.csv",
    "flagged_transactions.csv",
    "department_summary.csv",
    "receipts.json",
    "department_budgets.json",
)


@dataclass(frozen=True)
class CompanyPaths:
    company_id: int
    slug: str
    root: Path
    original_tx: Path
    scored_tx: Path
    employee_scores: Path
    flagged_tx: Path
    department_summary: Path
    receipts: Path
    budgets: Path

    @property
    def csv_name(self) -> str:
        return self.scored_tx.name


def companies_root() -> Path:
    return DATA_DIR / "companies"


def company_dir(slug: str) -> Path:
    return companies_root() / slug


def paths_for_company(company_id: int, slug: str) -> CompanyPaths:
    root = company_dir(slug)
    return CompanyPaths(
        company_id=company_id,
        slug=slug,
        root=root,
        original_tx=root / "transactions_original.csv",
        scored_tx=root / "transactions_scored.csv",
        employee_scores=root / "employee_scores_summary.csv",
        flagged_tx=root / "flagged_transactions.csv",
        department_summary=root / "department_summary.csv",
        receipts=root / "receipts.json",
        budgets=root / "department_budgets.json",
    )


def set_company_context(company_id: int, slug: str) -> None:
    _company_id.set(company_id)
    _company_slug.set(slug)


def clear_company_context() -> None:
    _company_id.set(None)
    _company_slug.set(None)


def get_company_key() -> tuple[int, str]:
    cid = _company_id.get()
    slug = _company_slug.get() or DEFAULT_COMPANY_SLUG
    return (cid or 0, slug)


def get_company_paths(
    company_id: int | None = None, slug: str | None = None
) -> CompanyPaths:
    if company_id is not None and slug:
        return paths_for_company(company_id, slug)
    cid, company_slug = get_company_key()
    return paths_for_company(cid, company_slug)


def _read_header(path: Path) -> list[str]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        row = next(csv.reader(handle), [])
    return list(row)


def _template_headers() -> dict[str, list[str]]:
    """Use the default company folder as column templates."""
    template = paths_for_company(0, DEFAULT_COMPANY_SLUG)
    return {
        "original_tx": _read_header(template.original_tx),
        "scored_tx": _read_header(template.scored_tx),
        "employee_scores": _read_header(template.employee_scores),
        "flagged_tx": _read_header(template.flagged_tx),
        "department_summary": _read_header(template.department_summary),
    }


def _write_header_csv(path: Path, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)


def init_empty_company_data(company_id: int, slug: str) -> CompanyPaths:
    """Create a new company folder with empty data files (headers only)."""
    paths = paths_for_company(company_id, slug)
    if paths.scored_tx.is_file():
        return paths

    headers = _template_headers()
    _write_header_csv(
        paths.original_tx,
        headers.get("original_tx")
        or [
            "Employee ID",
            "Employee Name",
            "Department",
            "Transaction Amount",
            "Debit or Credit",
        ],
    )
    _write_header_csv(
        paths.scored_tx, headers.get("scored_tx") or headers.get("original_tx") or []
    )
    _write_header_csv(
        paths.employee_scores,
        headers.get("employee_scores")
        or [
            "employee_id",
            "employee_name",
            "department",
            "starting_score",
            "final_score",
            "total_score_change",
            "total_spent",
            "reasonable_transactions",
            "flagged_transactions",
            "geofence_flags",
            "one_sentence_summary",
        ],
    )
    _write_header_csv(
        paths.flagged_tx, headers.get("flagged_tx") or headers.get("scored_tx") or []
    )
    _write_header_csv(
        paths.department_summary,
        headers.get("department_summary")
        or [
            "department",
            "total_spent",
            "transaction_count",
            "reasonable_transactions",
            "flagged_transactions",
            "geofence_flags",
            "average_score_after_transactions",
        ],
    )
    paths.receipts.write_text(json.dumps({"records": []}, indent=2), encoding="utf-8")
    paths.budgets.write_text(json.dumps({"quarters": {}}, indent=2), encoding="utf-8")
    return paths


def migrate_legacy_data_to_default_company() -> CompanyPaths | None:
    """
    One-time copy of legacy root data/ CSVs into data/companies/northwind-analytics/.
    """
    target = paths_for_company(0, DEFAULT_COMPANY_SLUG)
    if target.scored_tx.is_file():
        return target

    legacy_scored = DATA_DIR / "transactions_scored.csv"
    if not legacy_scored.is_file():
        return None

    target.root.mkdir(parents=True, exist_ok=True)
    for name in LEGACY_FILES:
        src = DATA_DIR / name
        dst = target.root / name
        if src.is_file() and not dst.exists():
            shutil.copy2(src, dst)
    return target


def ensure_company_data(company_id: int, slug: str) -> CompanyPaths:
    paths = paths_for_company(company_id, slug)
    if not paths.scored_tx.is_file():
        if slug == DEFAULT_COMPANY_SLUG:
            migrated = migrate_legacy_data_to_default_company()
            if migrated and migrated.scored_tx.is_file():
                return migrated
        init_empty_company_data(company_id, slug)
    return paths


