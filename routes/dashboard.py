"""Dashboard and navigation routes."""

from __future__ import annotations

import time

from flask import Blueprint, jsonify, render_template, session

from core.auth import login_required
from services.expenses import get_dashboard
from routes.helpers import (
    employee_scope_name,
    get_nav_cache,
    decided_keys,
    fraud_status_overrides,
    report_status_overrides,
    pending_proposal_items,
)

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@login_required
def index():
    session.pop("error_rotation_index", None)
    return render_template("index.html")


@dashboard_bp.route("/api/health")
def api_health():
    return jsonify({"ok": True, "service": "cashflux"})


@dashboard_bp.route("/api/nav")
@login_required
def api_nav():
    from services.guardian import (
        employee_summary,
        flagged_transactions,
        get_approvals_list,
        get_reports_list,
        transactions,
    )

    scope = employee_scope_name()
    if scope:
        from services.expenses import scoped_expenses

        rows = scoped_expenses(scope)
        return jsonify(
            {
                "flags": sum(1 for r in rows if r.get("flagged") == "yes"),
                "approvals": 0,
                "reports_pending": 0,
                "employees": 1,
                "transactions": len(rows),
                "review_pending": 0,
                "fraud_pending": 0,
            }
        )

    nav_cache = get_nav_cache()
    now = time.time()
    if nav_cache["data"] and now - nav_cache["at"] < 30:
        return jsonify(nav_cache["data"])

    approvals = get_approvals_list(limit=20)
    reports = get_reports_list(limit=30)
    payload = {
        "flags": int(len(flagged_transactions())),
        "approvals": len(approvals),
        "reports_pending": sum(1 for r in reports if r.get("status") == "pending_cfo"),
        "employees": int(len(employee_summary())),
        "transactions": int(len(transactions())),
    }
    try:
        from services.review import build_review_stats

        review = build_review_stats(
            approval_exclude=decided_keys("approval"),
            fraud_status_overrides=fraud_status_overrides(),
            proposal_items=pending_proposal_items(),
            flag_exclude=decided_keys("flag"),
            report_status_overrides=report_status_overrides(),
        )
        payload["approvals"] = review.get("approvals_pending", 0)
        payload["fraud_pending"] = review.get("fraud_pending", 0)
        payload["review_pending"] = review.get("total_pending", 0)
        payload["flags_pending"] = review.get("flags_pending", 0)
        payload["proposals_pending"] = review.get("proposals_pending", 0)
        payload["reports_pending"] = review.get(
            "reports_pending", payload.get("reports_pending", 0)
        )
    except Exception:
        import logging

        logging.debug("Review stats unavailable, using fallback counts", exc_info=True)
        payload["approvals"] = len(approvals)
        payload["fraud_pending"] = 0
        payload["review_pending"] = len(approvals)
    nav_cache["data"] = payload
    nav_cache["at"] = now
    return jsonify(payload)


@dashboard_bp.route("/api/dashboard")
@login_required
def api_dashboard():
    return jsonify(get_dashboard(employee_name=employee_scope_name()))


@dashboard_bp.route("/api/surprise")
@login_required
def api_surprise():
    from services.surprise import build_spending_oracle

    return jsonify(build_spending_oracle(employee_name=employee_scope_name()))


@dashboard_bp.route("/api/vendor-consolidation")
@login_required
def api_vendor_consolidation():
    from services.vendors import analyze_vendor_consolidation

    return jsonify(analyze_vendor_consolidation(employee_name=employee_scope_name()))
