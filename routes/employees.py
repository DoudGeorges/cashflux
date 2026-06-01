"""Employee routes."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from config import Config

from core.auth import login_required
from services.expenses import (
    compare_employees,
    get_employee_detail,
    get_map_locations,
    get_map_merchants,
    list_employees,
    list_purchases,
)
from routes.helpers import employee_scope_name

employees_bp = Blueprint("employees", __name__)



@employees_bp.route("/api/employees")
@login_required
def api_employees():
    return jsonify(list_employees(employee_name=employee_scope_name()))


@employees_bp.route("/api/employee")
@login_required
def api_employee():
    name = request.args.get("name", "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    detail = get_employee_detail(name, employee_name=employee_scope_name())
    if not detail:
        return jsonify({"error": "employee not found"}), 404
    try:
        from services.benchmarks import peer_benchmark_for_employee

        bench = peer_benchmark_for_employee(name)
        if bench:
            detail["peer_benchmark"] = bench
    except ImportError:
        current_app.logger.debug("peer_benchmark module not available")
    return jsonify(detail)


@employees_bp.route("/api/purchases")
@login_required
def api_purchases():
    return jsonify(list_purchases(employee_name=employee_scope_name()))


@employees_bp.route("/api/map-locations")
@login_required
def api_map_locations():
    limit = request.args.get("limit", 40, type=int)
    limit = max(1, min(limit, 60))
    return jsonify(
        get_map_locations(
            api_key=Config.GOOGLE_MAPS_API_KEY,
            limit=limit,
            employee_name=employee_scope_name(),
        )
    )


@employees_bp.route("/api/map-merchants")
@login_required
def api_map_merchants():
    limit = request.args.get("limit", 250, type=int)
    limit = max(1, min(limit, 800))
    north = request.args.get("north", type=float)
    south = request.args.get("south", type=float)
    east = request.args.get("east", type=float)
    west = request.args.get("west", type=float)
    return jsonify(
        get_map_merchants(
            api_key=_google_maps_api_key(),
            north=north,
            south=south,
            east=east,
            west=west,
            limit=limit,
            geocode_budget=60,
            employee_name=employee_scope_name(),
        )
    )


@employees_bp.route("/api/compare", methods=["POST"])
@login_required
def api_compare():
    data = request.json or {}
    names = data.get("names") or []
    result = compare_employees(names, employee_name=employee_scope_name())
    if not result:
        return jsonify({"error": "no matching employees"}), 404
    return jsonify(result)
