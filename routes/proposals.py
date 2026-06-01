"""Proposal routes for project proposals for employees."""

from __future__ import annotations

import json

from flask import Blueprint, jsonify, request

from core.auth import get_current_user, can_see_all, login_required
from core.extensions import db
from models import ProjectProposal
from routes.helpers import (
    invalidate_nav_cache,
    approved_proposals_for_user,
)

proposals_bp = Blueprint("proposals", __name__)


@proposals_bp.route("/api/proposals/colleagues")
@login_required
def api_proposals_colleagues():
    """Company roster for adding teammates to a project (excludes the current user)."""
    from services.guardian import employees_by_name

    user = get_current_user()
    if can_see_all(user):
        return jsonify({"error": "Only employees add colleagues to projects"}), 403
    roster = []
    for name, info in sorted(
        employees_by_name().items(), key=lambda item: item[0].lower()
    ):
        if name == user.employee_name:
            continue
        roster.append(
            {
                "name": name,
                "department": str(info.get("department") or "-"),
            }
        )
    return jsonify(roster)


@proposals_bp.route("/api/proposals/mine")
@login_required
def api_proposals_mine():
    from services.proposals import serialize_proposal
    from services.receipts import project_spend_by_user

    user = get_current_user()
    spend = project_spend_by_user(user.id)
    rows = (
        ProjectProposal.query.filter_by(user_id=user.id)
        .order_by(ProjectProposal.submitted_at.desc())
        .all()
    )
    return jsonify([serialize_proposal(p, spent=spend.get(p.id, 0)) for p in rows])


@proposals_bp.route("/api/proposals/approved")
@login_required
def api_proposals_approved():
    from services.proposals import approved_project_option
    from services.receipts import project_spend_by_user

    user = get_current_user()
    spend = project_spend_by_user(user.id)
    rows = approved_proposals_for_user(user)
    return jsonify([approved_project_option(p, spent=spend.get(p.id, 0)) for p in rows])


@proposals_bp.route("/api/proposals/budget-hint")
@login_required
def api_proposals_budget_hint():
    from services.proposals import build_budget_snapshot, employee_department

    user = get_current_user()
    if not user.employee_name:
        return jsonify({"error": "No employee profile linked to this account"}), 400
    dept = employee_department(user.employee_name)
    snapshot = build_budget_snapshot(dept)
    return jsonify(
        {
            "employee_name": user.employee_name,
            "department": dept,
            **snapshot,
        }
    )


@proposals_bp.route("/api/proposals", methods=["POST"])
@login_required
def api_proposals_create():
    from services.proposals import (
        build_budget_snapshot,
        employee_department,
        normalize_colleagues,
        serialize_proposal,
    )

    user = get_current_user()
    if can_see_all(user):
        return jsonify({"error": "Only employees submit project proposals"}), 403
    if not user.employee_name:
        return jsonify(
            {"error": "Your account is not linked to an employee profile"}
        ), 400

    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()
    try:
        amount = float(data.get("requested_amount", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid budget amount"}), 400

    if len(title) < 3:
        return jsonify(
            {"error": "Project title is required (at least 3 characters)"}
        ), 400
    if len(description) < 10:
        return jsonify(
            {"error": "Please describe the project (at least 10 characters)"}
        ), 400
    if amount <= 0:
        return jsonify({"error": "Budget amount must be greater than zero"}), 400

    budget_source = (data.get("budget_source") or "").strip().lower()
    if budget_source not in ("existing", "extra"):
        return jsonify(
            {
                "error": "Please choose whether this uses existing budget or requests extra budget"
            }
        ), 400

    dept = employee_department(user.employee_name)
    snapshot = build_budget_snapshot(dept)
    from services.guardian import employees_by_name

    colleagues = normalize_colleagues(
        data.get("colleagues"),
        roster=set(employees_by_name().keys()),
        exclude=user.employee_name,
    )

    proposal = ProjectProposal(
        user_id=user.id,
        company_id=user.company_id,
        employee_name=user.employee_name,
        department=dept,
        title=title,
        description=description,
        requested_amount=round(amount, 2),
        quarter=data.get("quarter") or snapshot.get("quarter"),
        status="pending",
        budget_snapshot=json.dumps(snapshot),
        budget_source=budget_source,
        colleagues=json.dumps(colleagues) if colleagues else None,
    )
    db.session.add(proposal)
    db.session.commit()
    invalidate_nav_cache()
    return jsonify(serialize_proposal(proposal)), 201

