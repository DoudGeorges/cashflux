"""Fraud detection routes."""

from __future__ import annotations

from flask import Blueprint, jsonify, request, send_file

from core.auth import login_required, admin_required
from routes.helpers import invalidate_nav_cache, persist_fraud_decision

fraud_bp = Blueprint("fraud", __name__)


@fraud_bp.route("/api/fraud/flagged")
@login_required
@admin_required
def api_fraud_flagged():
    from services.fraud import flagged_records

    return jsonify(flagged_records())


@fraud_bp.route("/api/fraud/stats")
@login_required
@admin_required
def api_fraud_stats():
    from services.fraud import fraud_stats

    return jsonify(fraud_stats())


@fraud_bp.route("/api/fraud/review", methods=["POST"])
@login_required
@admin_required
def api_fraud_review():
    from services.fraud import review_transaction

    data = request.get_json(silent=True) or {}
    txn_id = data.get("transaction_id")
    action = data.get("action")
    if not txn_id or action not in ("approved", "dismissed", "escalated"):
        return jsonify({"error": "Invalid review payload"}), 400
    result = review_transaction(txn_id, action)
    if result.get("error"):
        return jsonify(result), 404
    persist_fraud_decision(txn_id, action, data.get("note"))
    invalidate_nav_cache()
    return jsonify(result)


@fraud_bp.route("/api/fraud/undo", methods=["POST"])
@login_required
@admin_required
def api_fraud_undo():
    from services.fraud import undo_review

    result = undo_review()
    if result.get("error"):
        return jsonify(result), 400
    invalidate_nav_cache()
    return jsonify(result)


@fraud_bp.route("/api/fraud/threshold", methods=["POST"])
@login_required
@admin_required
def api_fraud_threshold():
    from services.fraud import set_threshold

    data = request.get_json(silent=True) or {}
    try:
        value = float(data.get("threshold", 0.4))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid threshold"}), 400
    invalidate_nav_cache()
    return jsonify({"threshold": set_threshold(value)})


@fraud_bp.route("/api/fraud/export")
@login_required
@admin_required
def api_fraud_export():
    from services.fraud import export_reviewed_csv

    buf, filename = export_reviewed_csv()
    return send_file(
        buf, mimetype="text/csv", as_attachment=True, download_name=filename
    )
