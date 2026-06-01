"""Budget routes."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from core.auth import login_required, admin_required
from routes.helpers import invalidate_nav_cache

budget_bp = Blueprint("budget", __name__)


@budget_bp.route("/api/budget")
@login_required
@admin_required
def api_budget():
    from services.budgets import get_budget_overview

    try:
        resp = jsonify(get_budget_overview())
        resp.headers["Cache-Control"] = "no-store"
        return resp
    except Exception:
        current_app.logger.exception("Failed to build budget overview")
        return jsonify({"error": "Could not load budget data."}), 500


@budget_bp.route("/api/budget/forecast")
@login_required
@admin_required
def api_budget_forecast():
    from services.budgets import forecast_department, get_forecast_for_query

    dept = request.args.get("department", "").strip()
    q = request.args.get("q", "").strip()
    if dept:
        return jsonify(forecast_department(dept))
    if q:
        result = get_forecast_for_query(q)
        if result:
            return jsonify(result)
        return jsonify({"error": "No forecast matched query"}), 404
    from services.budgets import get_department_forecasts

    return jsonify(get_department_forecasts())


@budget_bp.route("/api/settings/budgets", methods=["GET", "PUT"])
@login_required
@admin_required
def api_settings_budgets():
    from services.budgets import get_budget_settings, save_quarter_budgets

    if request.method == "GET":
        resp = jsonify(get_budget_settings())
        resp.headers["Cache-Control"] = "no-store"
        return resp

    data = request.json or {}
    quarter = (data.get("quarter") or "").strip()
    budgets = data.get("budgets") or data.get("departments") or {}
    if not quarter:
        return jsonify({"error": "quarter is required"}), 400
    if not isinstance(budgets, dict):
        return jsonify({"error": "budgets must be an object"}), 400
    save_quarter_budgets(quarter, budgets)
    invalidate_nav_cache()
    return jsonify({**get_budget_settings(), "status": "saved"})
