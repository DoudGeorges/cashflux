"""Trip report and expense report routes."""

from __future__ import annotations

import json

from flask import Blueprint, jsonify, request

from core.auth import get_current_user, can_see_all, login_required, admin_required
from core.extensions import db
from models import WorkflowDecision, ProjectProposal, EmployeeTripReport
from routes.helpers import (
    invalidate_nav_cache,
    report_status_overrides,
    submitted_trip_report_dicts,
    resolve_submitted_report,
    apply_trip_report_decision,
    claimed_trip_transaction_keys,
    trip_report_project_title,
    user_can_use_project,
)

reports_bp = Blueprint("reports", __name__)


@reports_bp.route("/api/reports")
@login_required
@admin_required
def api_reports():
    from services.guardian import get_reports_list
    from services.trip_reports import merge_trip_report_lists

    overrides = {
        r.item_key: r.status
        for r in WorkflowDecision.query.filter_by(item_type="report").all()
    }
    submitted = submitted_trip_report_dicts(overrides)
    auto = get_reports_list(status_overrides=overrides, include_submitted=False)
    return jsonify(merge_trip_report_lists(auto, submitted))


@reports_bp.route("/api/reports/<path:report_key>")
@login_required
@admin_required
def api_report_detail(report_key):
    from services.guardian import get_report_detail

    detail = resolve_submitted_report(report_key) or get_report_detail(report_key)
    if not detail:
        return jsonify({"error": "Report not found"}), 404
    row = WorkflowDecision.query.filter_by(
        item_key=report_key, item_type="report"
    ).first()
    detail["status"] = row.status if row else detail.get("status", "pending_cfo")
    return jsonify(detail)


@reports_bp.route("/api/reports/<path:report_key>/decide", methods=["POST"])
@login_required
@admin_required
def api_report_decide(report_key):
    data = request.json or {}
    approved = bool(data.get("approved"))
    existing = WorkflowDecision.query.filter_by(
        item_key=report_key, item_type="report"
    ).first()
    if existing:
        return jsonify({"error": "Already decided", "status": existing.status}), 409
    try:
        status = apply_trip_report_decision(report_key, approved, data.get("note"))
    except ValueError:
        return jsonify({"error": "Already decided"}), 409
    invalidate_nav_cache()
    return jsonify({"status": status, "report_key": report_key})


@reports_bp.route("/api/trip-reports/transactions")
@login_required
def api_trip_report_transactions():
    from services.trip_reports import eligible_transactions

    user = get_current_user()
    if can_see_all(user):
        return jsonify({"error": "Only employees submit trip reports"}), 403
    if not user.employee_name:
        return jsonify(
            {"error": "Your account is not linked to an employee profile"}
        ), 400
    claimed = claimed_trip_transaction_keys(user.company_id, user.employee_name)
    return jsonify(eligible_transactions(user.employee_name, claimed))


@reports_bp.route("/api/trip-reports/mine")
@login_required
def api_trip_reports_mine():
    from services.trip_reports import serialize_submission

    user = get_current_user()
    if can_see_all(user):
        return jsonify({"error": "Only employees view their trip reports here"}), 403
    overrides = report_status_overrides()
    rows = (
        EmployeeTripReport.query.filter_by(user_id=user.id)
        .order_by(EmployeeTripReport.submitted_at.desc())
        .all()
    )
    return jsonify(
        [
            serialize_submission(
                row,
                overrides.get(f"submitted:{row.id}"),
                trip_report_project_title(row.project_id),
            )
            for row in rows
        ]
    )


@reports_bp.route("/api/trip-reports", methods=["POST"])
@login_required
def api_trip_reports_create():
    from services.trip_reports import (
        resolve_department,
        serialize_submission,
        transaction_key,
    )
    from services.expenses import scoped_expenses

    user = get_current_user()
    if can_see_all(user):
        return jsonify({"error": "Only employees submit trip reports"}), 403
    if not user.employee_name:
        return jsonify(
            {"error": "Your account is not linked to an employee profile"}
        ), 400

    data = request.get_json(silent=True) or {}
    trip_name = (data.get("trip_name") or "").strip()
    purpose = (data.get("purpose") or "").strip()
    raw_keys = data.get("transaction_keys") or []

    if not trip_name:
        return jsonify({"error": "Trip name is required"}), 400
    if not isinstance(raw_keys, list) or len(raw_keys) < 1:
        return jsonify(
            {"error": "Select at least one purchase for this trip report"}
        ), 400

    claimed = claimed_trip_transaction_keys(user.company_id, user.employee_name)
    owned_keys = {
        transaction_key(r)
        for r in scoped_expenses(user.employee_name)
        if r.get("is_debit")
    }
    selected: list[str] = []
    seen: set[str] = set()
    for raw in raw_keys:
        key = str(raw).strip()
        if not key or key in seen:
            continue
        if key not in owned_keys:
            return jsonify({"error": f"Purchase not found or not yours: {key}"}), 400
        if key in claimed:
            return jsonify(
                {"error": "One or more purchases are already on another trip report"}
            ), 409
        seen.add(key)
        selected.append(key)

    if not selected:
        return jsonify({"error": "Select at least one valid purchase"}), 400

    spending_purpose = (data.get("spending_purpose") or "").strip().lower()
    if spending_purpose not in ("personal", "project"):
        return jsonify({"error": "Please choose personal use or project use"}), 400

    project_id = None
    if spending_purpose == "project":
        try:
            project_id = int(data.get("project_id"))
        except (TypeError, ValueError):
            return jsonify(
                {"error": "Please select which approved project this is for"}
            ), 400
        proposal = ProjectProposal.query.filter_by(
            id=project_id, status="approved"
        ).first()
        if not proposal or not user_can_use_project(user, proposal):
            return jsonify(
                {"error": "That project is not approved or does not belong to you"}
            ), 400

    report = EmployeeTripReport(
        user_id=user.id,
        company_id=user.company_id,
        employee_name=user.employee_name,
        department=resolve_department(user.employee_name),
        trip_name=trip_name[:200],
        purpose=purpose or None,
        transaction_keys=json.dumps(selected),
        status="pending_cfo",
        spending_purpose=spending_purpose,
        project_id=project_id,
    )
    db.session.add(report)
    db.session.commit()
    invalidate_nav_cache()
    return jsonify(
        serialize_submission(
            report, project_title=trip_report_project_title(report.project_id)
        )
    ), 201


@reports_bp.route("/api/trip-reports/<int:report_id>")
@login_required
def api_trip_report_detail(report_id):
    from services.trip_reports import build_report_dict, parse_transaction_keys

    user = get_current_user()
    model = db.session.get(EmployeeTripReport, report_id)
    if not model:
        return jsonify({"error": "Report not found"}), 404
    if model.user_id != user.id and not can_see_all(user):
        return jsonify({"error": "Forbidden"}), 403
    overrides = report_status_overrides()
    key = f"submitted:{model.id}"
    status = overrides.get(key, model.status or "pending_cfo")
    detail = build_report_dict(
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
    if not detail:
        return jsonify({"error": "Report not found"}), 404
    return jsonify(detail)

