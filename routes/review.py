"""Review routes for unified review queue, approvals, and flags."""

from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request

from core.auth import get_current_user, login_required, admin_required
from core.extensions import db
from models import WorkflowDecision, ProjectProposal
import services.expenses as expense_data
from routes.helpers import (
    decided_keys,
    fraud_status_overrides,
    report_status_overrides,
    invalidate_nav_cache,
    pending_proposal_items,
    submitted_trip_report_dicts,
    persist_fraud_decision,
    apply_trip_report_decision,
)

review_bp = Blueprint("review", __name__)


@review_bp.route("/api/review/queue")
@login_required
@admin_required
def api_review_queue():
    from services.review import build_review_queue

    overrides = report_status_overrides()
    submitted = submitted_trip_report_dicts(overrides)
    return jsonify(
        build_review_queue(
            approval_exclude=decided_keys("approval"),
            fraud_status_overrides=fraud_status_overrides(),
            proposal_items=pending_proposal_items(),
            flag_exclude=decided_keys("flag"),
            report_status_overrides=overrides,
            submitted_trip_reports=submitted,
        )
    )


@review_bp.route("/api/review/stats")
@login_required
@admin_required
def api_review_stats():
    from services.review import build_review_stats

    overrides = report_status_overrides()
    submitted = submitted_trip_report_dicts(overrides)
    return jsonify(
        build_review_stats(
            approval_exclude=decided_keys("approval"),
            fraud_status_overrides=fraud_status_overrides(),
            proposal_items=pending_proposal_items(),
            flag_exclude=decided_keys("flag"),
            report_status_overrides=overrides,
            submitted_trip_reports=submitted,
        )
    )


@review_bp.route("/api/review/action", methods=["POST"])
@login_required
@admin_required
def api_review_action():
    from services.fraud import review_transaction

    data = request.get_json(silent=True) or {}
    item_id = data.get("id") or ""
    action = (data.get("action") or "").lower()

    if item_id.startswith("approval:"):
        item_key = item_id.split(":", 1)[1]
        if action not in ("approve", "deny"):
            return jsonify({"error": "Invalid action for approval"}), 400
        existing = WorkflowDecision.query.filter_by(
            item_key=item_key, item_type="approval"
        ).first()
        if existing:
            return jsonify({"error": "Already decided", "status": existing.status}), 409
        status = "approved" if action == "approve" else "denied"
        db.session.add(
            WorkflowDecision(
                item_key=item_key,
                item_type="approval",
                status=status,
                note=data.get("note"),
            )
        )
        db.session.commit()
        invalidate_nav_cache()
        return jsonify({"status": status, "id": item_id})

    if item_id.startswith("flag:"):
        item_key = item_id.split(":", 1)[1]
        if action not in ("approve", "deny"):
            return jsonify({"error": "Invalid action for flagged purchase"}), 400
        existing = WorkflowDecision.query.filter_by(
            item_key=item_key, item_type="flag"
        ).first()
        if existing:
            return jsonify({"error": "Already decided", "status": existing.status}), 409
        status = "approved" if action == "approve" else "denied"
        db.session.add(
            WorkflowDecision(
                item_key=item_key,
                item_type="flag",
                status=status,
                note=data.get("note"),
            )
        )
        db.session.commit()
        expense_data.reload_expense_cache()
        invalidate_nav_cache()
        return jsonify({"status": status, "id": item_id})

    if item_id.startswith("fraud:"):
        txn_id = item_id.split(":", 1)[1]
        fraud_action = {
            "approve": "approved",
            "dismiss": "dismissed",
            "deny": "dismissed",
            "escalate": "escalated",
        }.get(action)
        if not fraud_action:
            return jsonify({"error": "Invalid action for fraud item"}), 400
        result = review_transaction(txn_id, fraud_action)
        if result.get("error"):
            return jsonify(result), 404
        persist_fraud_decision(txn_id, fraud_action, data.get("note"))
        invalidate_nav_cache()
        return jsonify({"status": fraud_action, "id": item_id})

    if item_id.startswith("proposal:"):
        try:
            proposal_id = int(item_id.split(":", 1)[1])
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid proposal id"}), 400
        if action not in ("approve", "deny"):
            return jsonify({"error": "Invalid action for proposal"}), 400
        proposal = db.session.get(ProjectProposal, proposal_id)
        if not proposal:
            return jsonify({"error": "Proposal not found"}), 404
        if proposal.status != "pending":
            return jsonify({"error": "Already decided", "status": proposal.status}), 409
        admin = get_current_user()
        budget_update = None
        if action == "approve" and (proposal.budget_source or "") == "extra":
            from services.budgets import apply_extra_budget_approval

            budget_update = apply_extra_budget_approval(
                proposal.department,
                proposal.quarter,
                proposal.requested_amount,
            )
        proposal.status = "approved" if action == "approve" else "denied"
        proposal.decided_at = datetime.now()
        proposal.decided_by_user_id = admin.id if admin else None
        proposal.decision_note = (data.get("note") or "").strip() or None
        db.session.commit()
        invalidate_nav_cache()
        payload = {"status": proposal.status, "id": item_id}
        if budget_update:
            payload["budget_update"] = budget_update
        return jsonify(payload)

    if item_id.startswith("report:"):
        report_key = item_id.split(":", 1)[1]
        if action not in ("approve", "deny"):
            return jsonify({"error": "Invalid action for trip report"}), 400
        existing = WorkflowDecision.query.filter_by(
            item_key=report_key, item_type="report"
        ).first()
        if existing:
            return jsonify({"error": "Already decided", "status": existing.status}), 409
        try:
            status = apply_trip_report_decision(
                report_key, action == "approve", data.get("note")
            )
        except ValueError:
            return jsonify({"error": "Already decided"}), 409
        invalidate_nav_cache()
        return jsonify({"status": status, "id": item_id})

    return jsonify({"error": "Unknown review item"}), 400


@review_bp.route("/api/approvals")
@login_required
@admin_required
def api_approvals():
    from services.guardian import get_approvals_list

    return jsonify(get_approvals_list(exclude_keys=decided_keys("approval")))


@review_bp.route("/api/approvals/<path:item_key>/decide", methods=["POST"])
@login_required
@admin_required
def api_approval_decide(item_key):
    data = request.json or {}
    approved = bool(data.get("approved"))
    existing = WorkflowDecision.query.filter_by(
        item_key=item_key, item_type="approval"
    ).first()
    if existing:
        return jsonify({"error": "Already decided", "status": existing.status}), 409
    status = "approved" if approved else "denied"
    db.session.add(
        WorkflowDecision(
            item_key=item_key,
            item_type="approval",
            status=status,
            note=data.get("note"),
        )
    )
    db.session.commit()
    invalidate_nav_cache()
    return jsonify({"status": status, "item_key": item_key})


@review_bp.route("/api/flags")
@login_required
@admin_required
def api_flags():
    from services.guardian import get_flags_list

    return jsonify(get_flags_list(exclude_keys=decided_keys("flag")))

