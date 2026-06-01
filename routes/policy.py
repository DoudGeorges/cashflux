"""Policy routes: rules management and document import."""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from core.auth import login_required, admin_required
from services.guardian import clear_cache
import services.expenses as expense_data
from routes.helpers import invalidate_nav_cache, receipt_mime_type

policy_bp = Blueprint("policy", __name__)


@policy_bp.route("/api/policy/rules", methods=["GET", "PUT"])
@login_required
@admin_required
def api_policy_rules():
    from services.policy import (
        DEPT_OVERRIDE_FIELDS,
        get_policy_schema,
        list_policy_departments,
        load_policy_document,
        load_policy_rules,
        policy_summary_text,
        save_policy_document,
        save_policy_rules,
    )

    if request.method == "GET":
        return jsonify(
            {
                "rules": load_policy_rules(),
                "document": load_policy_document(),
                "summary": policy_summary_text(),
                "schema": get_policy_schema(),
                "departments": list_policy_departments(),
                "dept_override_fields": DEPT_OVERRIDE_FIELDS,
            }
        )
    data = request.json or {}
    rules = save_policy_rules(data.get("rules") or data)
    document = data.get("document")
    if document is not None:
        save_policy_document(document)
    clear_cache()
    invalidate_nav_cache()

    return jsonify(
        {
            "rules": rules,
            "document": load_policy_document(),
            "summary": policy_summary_text(),
            "status": "saved",
        }
    )


@policy_bp.route("/api/policy/offenders")
@login_required
@admin_required
def api_policy_offenders():
    from services.policy import get_repeat_offenders

    return jsonify(get_repeat_offenders(limit=12))


@policy_bp.route("/api/policy/import", methods=["POST"])
@login_required
@admin_required
def api_policy_import():
    from services.policy_import import (
        apply_imported_policy,
        extract_policy_from_document,
    )

    file = request.files.get("file")
    if not file:
        return jsonify({"error": "file is required"}), 400

    file_bytes = file.read()
    if len(file_bytes) > 15 * 1024 * 1024:
        return jsonify({"error": "File too large (max 15 MB)"}), 400

    mime_type = receipt_mime_type(file.filename or "", file.content_type)
    if mime_type != "application/pdf" and not mime_type.startswith("text/"):
        return jsonify({"error": "Upload a PDF or text policy document"}), 400

    extracted = extract_policy_from_document(file_bytes, mime_type)
    if extracted.get("error"):
        return jsonify({"error": extracted["error"]}), 400

    try:
        result = apply_imported_policy(extracted)
    except Exception:
        logging.exception("Policy import failed")
        return jsonify({"error": "Policy import failed"}), 500

    clear_cache()
    invalidate_nav_cache()
    expense_data.reload_expense_cache()

    result["summary"] = policy_summary_text()
    return jsonify(result)

