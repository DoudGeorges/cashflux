"""Employee-submitted trip expense reports: build report payloads for review."""

from __future__ import annotations

import json

import pandas as pd

from services.expenses import scoped_expenses
from core.formatting import fmt_date, fmt_money
from services.expenses.guardian import transactions
from services.policy import scan_all_policy_violations
from services.workflow.proposals import employee_department
from services.workflow.engine import build_trip_report_recommendation


def transaction_key(row: dict) -> str:
    """Stable id for matching expense rows to a submitted report."""
    emp = str(row.get("employee") or "").strip()
    vend = str(row.get("vendor") or "").strip()
    date_part = fmt_date(row.get("date"))
    amt = round(float(row.get("amount") or 0), 2)
    return f"{emp}|{vend}|{date_part}|{amt}"


def guardian_row_key(row) -> str:
    emp = str(row.get("Employee Name") or "").strip()
    vend = str(row.get("Merchant Info DBA Name") or "").strip()
    date_part = fmt_date(row.get("Transaction Date"))
    amt = round(float(row.get("Amount Clean") or 0), 2)
    return f"{emp}|{vend}|{date_part}|{amt}"


def parse_transaction_keys(raw) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        keys = raw
    else:
        try:
            keys = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return []
    return [str(k).strip() for k in keys if str(k).strip()]


def submission_report_key(report_id: int) -> str:
    return f"submitted:{report_id}"


def _trip_city_from_row(row) -> str:
    city = str(row.get("city") or row.get("Merchant City") or "").strip()
    if city:
        return city
    loc = str(row.get("location") or "").strip()
    return loc.split(",")[0].strip() if loc else "Travel"


def _rows_for_keys(keys: list[str], employee_name: str) -> list[dict]:
    key_set = set(keys)
    return [r for r in scoped_expenses(employee_name) if transaction_key(r) in key_set]


def _guardian_df_for_keys(keys: list[str], employee_name: str) -> pd.DataFrame:
    key_set = set(keys)
    df = transactions()
    if df.empty:
        return pd.DataFrame()
    mask = df.apply(
        lambda row: (
            guardian_row_key(row) in key_set
            and str(row.get("Employee Name") or "").strip() == employee_name
        ),
        axis=1,
    )
    subset = df.loc[mask].copy()
    if subset.empty:
        return subset
    subset["Transaction Date"] = pd.to_datetime(
        subset["Transaction Date"], errors="coerce"
    )
    return subset.sort_values("Transaction Date")


def eligible_transactions(employee_name: str, claimed_keys: set[str]) -> list[dict]:
    """Debit purchases the employee can attach to a new trip report."""
    out = []
    for row in scoped_expenses(employee_name):
        if not row.get("is_debit") or float(row.get("amount") or 0) <= 0:
            continue
        key = transaction_key(row)
        if key in claimed_keys:
            continue
        out.append(
            {
                "key": key,
                "date": fmt_date(row["date"]),
                "date_sort": row["date"].strftime("%Y-%m-%d"),
                "vendor": row.get("vendor") or "-",
                "category": row.get("category") or "-",
                "amount": fmt_money(row["amount"]),
                "amount_raw": round(float(row["amount"]), 2),
                "location": row.get("location") or "-",
                "flagged": row.get("flagged") == "yes",
            }
        )
    out.sort(key=lambda item: item["date_sort"], reverse=True)
    return out


def build_report_dict(
    *,
    report_id: int,
    employee_name: str,
    department: str,
    trip_name: str,
    purpose: str,
    transaction_keys: list[str],
    status: str = "pending_cfo",
    source: str = "employee",
    spending_purpose: str = "personal",
    project_id: int | None = None,
    project_title: str | None = None,
) -> dict | None:
    """Build a trip report payload matching auto-clustered report shape."""
    keys = [k for k in transaction_keys if k]
    if not keys:
        return None

    expense_rows = _rows_for_keys(keys, employee_name)
    gdf = _guardian_df_for_keys(keys, employee_name)

    if expense_rows:
        expense_rows.sort(key=lambda r: r["date"])
        total = sum(float(r.get("amount") or 0) for r in expense_rows)
        start = expense_rows[0]["date"]
        end = expense_rows[-1]["date"]
        city = _trip_city_from_row(expense_rows[0])
        tx_list = [
            {
                "date": fmt_date(r["date"]),
                "vendor": r.get("vendor"),
                "amount": fmt_money(float(r.get("amount") or 0)),
                "category": r.get("category") or r.get("transaction_category"),
            }
            for r in expense_rows
        ]
        categories: dict[str, float] = {}
        for r in expense_rows:
            cat = str(r.get("transaction_category") or r.get("category") or "Other")
            categories[cat] = categories.get(cat, 0) + float(r.get("amount") or 0)
    elif not gdf.empty:
        gdf = gdf.sort_values("Transaction Date")
        total = float(gdf["Amount Clean"].sum())
        start = gdf.iloc[0]["Transaction Date"]
        end = gdf.iloc[-1]["Transaction Date"]
        city = _trip_city_from_row(gdf.iloc[0])
        tx_list = [
            {
                "date": fmt_date(r.get("Transaction Date")),
                "vendor": r.get("Merchant Info DBA Name"),
                "amount": fmt_money(float(r.get("Amount Clean") or 0)),
                "category": r.get("Transaction Category"),
            }
            for _, r in gdf.iterrows()
        ]
        categories = {}
        for _, r in gdf.iterrows():
            cat = str(r.get("Transaction Category") or "Other")
            categories[cat] = categories.get(cat, 0) + float(r.get("Amount Clean") or 0)
    else:
        return None

    date_label = fmt_date(start)
    if len(keys) > 1 and start != end:
        date_label = f"{fmt_date(start)} – {fmt_date(end)}"

    violations: list[str] = []
    if not gdf.empty:
        for _, r in gdf.iterrows():
            if (
                str(r.get("flagged", "")).lower() in ("true", "1")
                or r.get("flagged") is True
            ):
                violations.append(str(r.get("flag_reason") or "Guardian flag"))
        for hit in scan_all_policy_violations(gdf):
            reason = hit.get("reason", "Policy violation")
            if reason not in violations:
                violations.append(reason)
    else:
        for r in expense_rows:
            if r.get("flagged") == "yes":
                violations.append(str(r.get("flag_reason") or "Flagged purchase"))

    tags = list(categories.keys())[:4]
    if violations:
        tags.append(f"{len(violations)} policy issue(s)")
    if source == "employee":
        tags.insert(0, "Employee submitted")
    purpose_kind = (spending_purpose or "personal").lower()
    if purpose_kind == "project" and project_title:
        tags.insert(0, f"Project: {project_title}")
    elif purpose_kind == "personal":
        tags.insert(0, "Personal")

    rec, brief, ai_context = build_trip_report_recommendation(
        {
            "employee": employee_name,
            "department": department,
            "total": total,
            "txs": len(keys),
            "trip_name": trip_name,
            "date_range": date_label,
            "violations": violations,
        }
    )

    if purpose:
        brief = f"{brief} Employee notes: {purpose[:240]}"

    title = f"{employee_name}: {city} {trip_name.replace(' Trip', '').replace(' Travel', '')}"
    report_key = submission_report_key(report_id)

    return {
        "id": f"sub-{report_id}",
        "report_key": report_key,
        "title": title,
        "employee": employee_name,
        "department": department,
        "trip_name": trip_name,
        "city": city,
        "txs": len(keys),
        "total": total,
        "total_formatted": fmt_money(total),
        "tags": tags or ["Business travel"],
        "violation": bool(violations),
        "violation_count": len(violations),
        "violations": violations[:5],
        "dup": False,
        "date_range": date_label,
        "categories": {k: round(v, 2) for k, v in categories.items()},
        "status": status,
        "policy_summary": (
            f"{len(violations)} policy issue(s) detected across {len(keys)} transactions."
            if violations
            else "All transactions pass automated policy checks."
        ),
        "ai_recommendation": rec,
        "ai_brief": brief,
        "ai_context": ai_context,
        "transactions": tx_list,
        "purpose": purpose or "",
        "source": source,
        "submitted_report_id": report_id,
        "spending_purpose": purpose_kind,
        "project_id": project_id,
        "project_title": project_title or "",
    }


def serialize_submission(
    model,
    status_override: str | None = None,
    project_title: str | None = None,
) -> dict:
    keys = parse_transaction_keys(model.transaction_keys)
    status = status_override or model.status or "pending_cfo"
    spending_purpose = getattr(model, "spending_purpose", None) or "personal"
    project_id = getattr(model, "project_id", None)
    report = build_report_dict(
        report_id=model.id,
        employee_name=model.employee_name,
        department=model.department,
        trip_name=model.trip_name,
        purpose=model.purpose or "",
        transaction_keys=keys,
        status=status,
        spending_purpose=spending_purpose,
        project_id=project_id,
        project_title=project_title,
    )
    total = float(report["total"]) if report else 0.0
    return {
        "id": model.id,
        "report_key": submission_report_key(model.id),
        "trip_name": model.trip_name,
        "purpose": model.purpose or "",
        "employee_name": model.employee_name,
        "department": model.department,
        "transaction_count": len(keys),
        "total": round(total, 2),
        "total_formatted": fmt_money(total) if report else fmt_money(0),
        "status": status,
        "submitted_at": model.submitted_at.isoformat() if model.submitted_at else None,
        "decided_at": model.decided_at.isoformat() if model.decided_at else None,
        "decision_note": model.decision_note,
        "date_range": report.get("date_range") if report else "",
        "tags": report.get("tags", []) if report else [],
        "spending_purpose": spending_purpose,
        "project_id": project_id,
        "project_title": project_title
        or (report.get("project_title") if report else "")
        or "",
    }


def merge_trip_report_lists(
    auto_reports: list[dict],
    submitted_reports: list[dict],
    limit: int = 20,
) -> list[dict]:
    merged = submitted_reports + auto_reports
    merged.sort(
        key=lambda r: (r.get("violation_count", 0), r.get("txs", 0), r.get("total", 0)),
        reverse=True,
    )
    return merged[:limit]


def resolve_department(employee_name: str) -> str:
    return employee_department(employee_name)


