"""Project proposal helpers — budget context and review queue items."""

from __future__ import annotations

import json

from expense_data import format_money
from guardian_data import credit_score_for_name, employees_by_name


def employee_department(employee_name: str) -> str:
    meta = employees_by_name().get(employee_name, {})
    return str(meta.get("department") or "Unknown")


def build_budget_snapshot(department: str) -> dict:
    from budget_data import forecast_department

    fc = forecast_department(department)
    return {
        "quarter": fc.get("quarter"),
        "budget": fc.get("budget"),
        "budget_fmt": fc.get("budget_fmt"),
        "spent": fc.get("spent"),
        "spent_fmt": fc.get("spent_fmt"),
        "remaining": fc.get("remaining"),
        "remaining_fmt": fc.get("remaining_fmt"),
        "status": fc.get("status"),
    }


BUDGET_SOURCE_LABELS = {
    "existing": "Use existing department budget",
    "extra": "Request extra budget",
}


def budget_source_label(source: str) -> str:
    return BUDGET_SOURCE_LABELS.get(source or "", source or "—")


def parse_colleagues(raw) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        names = raw
    else:
        try:
            names = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return []
    return [str(n).strip() for n in names if str(n).strip()]


def normalize_colleagues(raw, roster: set[str] | None = None, exclude: str | None = None) -> list[str]:
    """Validate and dedupe colleague names from API input."""
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [part.strip() for part in raw.split(",") if part.strip()]
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for name in raw:
        clean = str(name).strip()
        if not clean or clean in seen:
            continue
        if exclude and clean == exclude:
            continue
        if roster is not None and clean not in roster:
            continue
        seen.add(clean)
        out.append(clean)
    return out


def proposal_review_context(proposal: dict, snapshot: dict) -> list[str]:
    amt = float(proposal.get("requested_amount") or 0)
    remaining = float(snapshot.get("remaining") or 0)
    quarter = proposal.get("quarter") or snapshot.get("quarter") or "this quarter"
    source = proposal.get("budget_source") or "existing"
    lines = [
        f"Budget type: {budget_source_label(source)}",
        f"Requested budget: {format_money(amt)} for {quarter}",
        (
            f"{proposal.get('department', 'Department')}: "
            f"{snapshot.get('spent_fmt', '—')} spent of {snapshot.get('budget_fmt', '—')} "
            f"({snapshot.get('remaining_fmt', '—')} remaining)"
        ),
    ]
    if source == "existing" and amt > remaining:
        lines.append(f"Exceeds remaining budget by {format_money(amt - remaining)}")
    if source == "extra":
        lines.append("Requires approval for budget above the current department cap")
    score = credit_score_for_name(proposal.get("employee_name") or "")
    if score is not None:
        lines.append(f"Employee credit score: {score}/100")
    colleagues = proposal.get("colleagues") or []
    if colleagues:
        lines.append(f"Team members: {', '.join(colleagues)}")
    return lines


def proposal_brief(proposal: dict, snapshot: dict) -> str:
    amt = float(proposal.get("requested_amount") or 0)
    remaining = float(snapshot.get("remaining") or 0)
    source = proposal.get("budget_source") or "existing"
    if source == "extra":
        return "Review — employee is requesting additional budget beyond the department cap."
    if amt > remaining:
        return f"Deny — exceeds department remaining budget ({snapshot.get('remaining_fmt', '—')})."
    if remaining > 0 and amt > remaining * 0.5:
        return "Review carefully — this would use a large share of remaining budget."
    return "Approve — request fits within department budget headroom."


def _parse_snapshot(raw) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}


def serialize_proposal(model, spent: float = 0.0) -> dict:
    snapshot = _parse_snapshot(model.budget_snapshot)
    spent = float(spent or 0)
    budget = float(model.requested_amount or 0)
    remaining = max(budget - spent, 0.0)
    colleagues = parse_colleagues(getattr(model, "colleagues", None))
    data = {
        "id": model.id,
        "title": model.title,
        "description": model.description,
        "employee_name": model.employee_name,
        "department": model.department,
        "requested_amount": model.requested_amount,
        "requested_amount_fmt": format_money(model.requested_amount),
        "quarter": model.quarter,
        "status": model.status,
        "submitted_at": model.submitted_at.isoformat() if model.submitted_at else None,
        "decided_at": model.decided_at.isoformat() if model.decided_at else None,
        "decision_note": model.decision_note,
        "budget_snapshot": snapshot,
        "budget_source": model.budget_source or "existing",
        "budget_source_label": budget_source_label(model.budget_source),
        "colleagues": colleagues,
    }
    if model.status == "approved":
        data.update({
            "spent": round(spent, 2),
            "spent_fmt": format_money(spent),
            "remaining": round(remaining, 2),
            "remaining_fmt": format_money(remaining),
        })
    return data


def approved_project_option(model, spent: float = 0.0) -> dict:
    spent = float(spent or 0)
    budget = float(model.requested_amount or 0)
    remaining = max(budget - spent, 0.0)
    return {
        "id": model.id,
        "title": model.title,
        "requested_amount": budget,
        "requested_amount_fmt": format_money(budget),
        "spent": round(spent, 2),
        "spent_fmt": format_money(spent),
        "remaining": round(remaining, 2),
        "remaining_fmt": format_money(remaining),
        "quarter": model.quarter,
    }


def proposal_to_review_item(proposal_dict: dict) -> dict:
    snapshot = _parse_snapshot(proposal_dict.get("budget_snapshot"))
    amt = float(proposal_dict.get("requested_amount") or 0)
    remaining = float(snapshot.get("remaining") or 0)
    source = proposal_dict.get("budget_source") or "existing"
    over = source == "existing" and amt > remaining
    return {
        "id": f"proposal:{proposal_dict['id']}",
        "kind": "proposal",
        "status": proposal_dict.get("status", "pending"),
        "priority": 72 + min(amt / 1000.0, 20) + (18 if over else 0) + (12 if source == "extra" else 0),
        "title": proposal_dict["title"],
        "employee": proposal_dict["employee_name"],
        "department": proposal_dict["department"],
        "amount": format_money(amt),
        "amount_raw": amt,
        "risk_label": "Extra budget" if source == "extra" else ("Over budget" if over else "In budget"),
        "risk_kind": "budget",
        "brief": proposal_brief(proposal_dict, snapshot),
        "context": proposal_review_context(proposal_dict, snapshot),
        "rec": "deny" if over else "approve",
        "description": proposal_dict.get("description") or "",
        "quarter": proposal_dict.get("quarter") or snapshot.get("quarter") or "",
        "submitted_at": proposal_dict.get("submitted_at"),
        "proposal_id": proposal_dict["id"],
        "budget_source": source,
        "budget_source_label": proposal_dict.get("budget_source_label") or budget_source_label(source),
        "colleagues": proposal_dict.get("colleagues") or [],
    }
