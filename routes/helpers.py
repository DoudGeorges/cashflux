"""Shared helpers used across multiple route blueprints."""

from __future__ import annotations

from datetime import datetime

from core.extensions import db
from models import (
    WorkflowDecision,
    ProjectProposal,
    EmployeeTripReport,
)
from core.auth import get_current_user, employee_scope

# nav cache

_nav_cache: dict = {"data": None, "at": 0.0}


def invalidate_nav_cache() -> None:
    _nav_cache["data"] = None
    _nav_cache["at"] = 0.0


def get_nav_cache() -> dict:
    return _nav_cache


# employee scope


def employee_scope_name() -> str | None:
    """Return the employee name for data scoping, or None for admin users."""
    user = get_current_user()
    return employee_scope(user)


def chat_user_id() -> int | None:
    user = get_current_user()
    return user.id if user else None


# workflow decision helpers


def decided_keys(item_type: str) -> set[str]:
    rows = WorkflowDecision.query.filter_by(item_type=item_type).all()
    return {r.item_key for r in rows}


def fraud_status_overrides() -> dict[str, str]:
    rows = WorkflowDecision.query.filter_by(item_type="fraud").all()
    return {r.item_key: r.status for r in rows}


def report_status_overrides() -> dict[str, str]:
    rows = WorkflowDecision.query.filter_by(item_type="report").all()
    return {r.item_key: r.status for r in rows}


def persist_fraud_decision(txn_id: str, action: str, note: str | None = None) -> None:
    existing = WorkflowDecision.query.filter_by(
        item_key=txn_id, item_type="fraud"
    ).first()
    if existing:
        existing.status = action
        if note is not None:
            existing.note = note
    else:
        db.session.add(
            WorkflowDecision(
                item_key=txn_id,
                item_type="fraud",
                status=action,
                note=note,
            )
        )
    db.session.commit()


# proposal helpers


def pending_proposal_items():
    from services.proposals import proposal_to_review_item, serialize_proposal

    rows = (
        ProjectProposal.query.filter_by(status="pending")
        .order_by(ProjectProposal.submitted_at.asc())
        .all()
    )
    return [proposal_to_review_item(serialize_proposal(p)) for p in rows]


def approved_proposals_for_user(user):
    """Approved projects the user owns or was invited to as a colleague."""
    from services.proposals import parse_colleagues

    own = (
        ProjectProposal.query.filter_by(user_id=user.id, status="approved")
        .order_by(ProjectProposal.title.asc())
        .all()
    )
    if not user.employee_name:
        return own
    seen = {p.id for p in own}
    shared = []
    for proposal in ProjectProposal.query.filter_by(
        company_id=user.company_id, status="approved"
    ).all():
        if proposal.id in seen:
            continue
        if user.employee_name in parse_colleagues(proposal.colleagues):
            shared.append(proposal)
    return own + sorted(shared, key=lambda p: p.title.lower())


def user_can_use_project(user, proposal) -> bool:
    from services.proposals import parse_colleagues

    if not proposal or proposal.status != "approved":
        return False
    if proposal.user_id == user.id:
        return True
    return bool(
        user.employee_name
        and user.employee_name in parse_colleagues(proposal.colleagues)
    )


def trip_report_project_title(project_id: int | None) -> str | None:
    if not project_id:
        return None
    proposal = db.session.get(ProjectProposal, project_id)
    return proposal.title if proposal else None


# trip report helpers


def claimed_trip_transaction_keys(
    company_id: int, employee_name: str | None = None
) -> set[str]:
    from services.trip_reports import parse_transaction_keys

    query = EmployeeTripReport.query.filter_by(company_id=company_id).filter(
        EmployeeTripReport.status.in_(("pending_cfo", "approved"))
    )
    if employee_name:
        query = query.filter_by(employee_name=employee_name)
    claimed: set[str] = set()
    for row in query.all():
        claimed.update(parse_transaction_keys(row.transaction_keys))
    return claimed


def submitted_trip_report_dicts(status_overrides: dict | None = None) -> list[dict]:
    from services.trip_reports import (
        build_report_dict,
        parse_transaction_keys,
        submission_report_key,
    )

    user = get_current_user()
    if not user or not user.company_id:
        return []
    status_overrides = status_overrides or {}
    reports: list[dict] = []
    rows = (
        EmployeeTripReport.query.filter_by(company_id=user.company_id)
        .order_by(EmployeeTripReport.submitted_at.desc())
        .all()
    )
    for model in rows:
        key = submission_report_key(model.id)
        status = status_overrides.get(key, model.status or "pending_cfo")
        report = build_report_dict(
            report_id=model.id,
            employee_name=model.employee_name,
            department=model.department,
            trip_name=model.trip_name,
            purpose=model.purpose or "",
            transaction_keys=parse_transaction_keys(model.transaction_keys),
            status=status,
            spending_purpose=model.spending_purpose or "personal",
            project_id=model.project_id,
            project_title=trip_report_project_title(model.project_id),
        )
        if report:
            reports.append(report)
    return reports


def resolve_submitted_report(report_key: str) -> dict | None:
    from services.trip_reports import build_report_dict, parse_transaction_keys

    if not report_key.startswith("submitted:"):
        return None
    try:
        report_id = int(report_key.split(":", 1)[1])
    except (TypeError, ValueError):
        return None
    model = db.session.get(EmployeeTripReport, report_id)
    if not model:
        return None
    override = WorkflowDecision.query.filter_by(
        item_key=report_key, item_type="report"
    ).first()
    status = override.status if override else (model.status or "pending_cfo")
    return build_report_dict(
        report_id=model.id,
        employee_name=model.employee_name,
        department=model.department,
        trip_name=model.trip_name,
        purpose=model.purpose or "",
        transaction_keys=parse_transaction_keys(model.transaction_keys),
        status=status,
        spending_purpose=model.spending_purpose or "personal",
        project_id=model.project_id,
        project_title=trip_report_project_title(model.project_id),
    )


def apply_trip_report_decision(
    report_key: str, approved: bool, note: str | None = None
) -> str:
    status = "approved" if approved else "rejected"
    existing = WorkflowDecision.query.filter_by(
        item_key=report_key, item_type="report"
    ).first()
    if existing:
        raise ValueError("Already decided")
    db.session.add(
        WorkflowDecision(
            item_key=report_key,
            item_type="report",
            status=status,
            note=note,
        )
    )
    if report_key.startswith("submitted:"):
        try:
            report_id = int(report_key.split(":", 1)[1])
        except (TypeError, ValueError):
            report_id = None
        if report_id:
            model = db.session.get(EmployeeTripReport, report_id)
            if model:
                model.status = status
                model.decided_at = datetime.now()
                model.decision_note = (note or "").strip() or None
                admin = get_current_user()
                if admin:
                    model.decided_by_user_id = admin.id
    db.session.commit()
    return status


# receipt helpers


def receipt_employee_context(user):
    """Resolve employee id/name for receipt scan (employees use their profile)."""
    scope_name = employee_scope(user)
    employee_name = scope_name or user.employee_name
    employee_id = None
    if employee_name:
        from services.guardian import employees_by_name

        meta = employees_by_name().get(employee_name, {})
        employee_id = meta.get("employee_id") or ""
    return employee_id, employee_name, scope_name


def receipt_mime_type(filename: str, content_type: str | None) -> str:
    if content_type and content_type != "application/octet-stream":
        return content_type.split(";")[0].strip()
    lower = (filename or "").lower()
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".pdf"):
        return "application/pdf"
    if lower.endswith(".md"):
        return "text/markdown"
    if lower.endswith(".txt"):
        return "text/plain"
    return "image/jpeg"


def run_receipt_scan(file_bytes: bytes, mime_type: str, user):
    from services.receipt_ocr import (
        build_receipt_card,
        build_scan_reply,
        process_receipt,
    )

    employee_id, employee_name, scope_name = receipt_employee_context(user)
    from core.auth import can_see_all

    if not employee_name and not can_see_all(user):
        return None, "Your account is not linked to an employee profile."

    result = process_receipt(
        file_bytes,
        mime_type,
        employee_id=employee_id if scope_name else None,
        employee_name=scope_name,
    )
    card = build_receipt_card(result)
    card["scan_result"] = result
    return {
        "reply": build_scan_reply(result),
        "receipt": card,
        "scan": result,
    }, None

