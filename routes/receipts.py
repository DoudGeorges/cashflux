"""Receipt routes to scan, confirm, and list receipts."""

from __future__ import annotations

import time

from flask import Blueprint, jsonify, request

from core.auth import get_current_user, can_see_all, login_required
from core.extensions import db
from models import Conversation, Message, ProjectProposal
from routes.helpers import (
    chat_user_id,
    receipt_employee_context,
    receipt_mime_type,
    run_receipt_scan,
    user_can_use_project,
)

receipts_bp = Blueprint("receipts", __name__)
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


def _validate_uploaded_file(file):
    """Validate an uploaded receipt file; return (bytes, mime_type) or (None, error_msg).

    Returns a tuple of (file_bytes, mime_type) on success, or (None, error_message)
    when validation fails. The caller builds the JSON error response.
    """
    if not file:
        return None, "file is required"
    file_bytes = file.read()
    if len(file_bytes) > _MAX_UPLOAD_BYTES:
        return None, "File too large (max 10 MB)"
    mime_type = receipt_mime_type(file.filename or "", file.content_type)
    if not (mime_type.startswith("image/") or mime_type == "application/pdf"):
        return None, "File must be an image or PDF"
    return file_bytes, mime_type


@receipts_bp.route("/scan_receipt", methods=["POST"])
@login_required
def scan_receipt():
    start = time.perf_counter()
    conv_id = request.form.get("conversation_id")
    user_message = request.form.get("message", "Scan this receipt")
    file = request.files.get("file")
    user = get_current_user()

    uid = chat_user_id()
    conv = (
        Conversation.query.filter_by(id=conv_id, user_id=uid).first()
        if conv_id
        else None
    )
    if not conv or not file:
        return jsonify({"reply": "Pick a chat and attach a receipt."}), 400

    file_bytes, _err = _validate_uploaded_file(file)
    if file_bytes is None:
        return jsonify({"reply": _err + "."}), 400

    mime_type = receipt_mime_type(file.filename or "", file.content_type)

    payload, err = run_receipt_scan(file_bytes, mime_type, user)
    if err:
        return jsonify({"reply": err}), 400

    filename = file.filename or "receipt"
    attachment_note = f" [attached: {filename}]"
    db.session.add(
        Message(
            conversation_id=conv.id, is_user=True, text=user_message + attachment_note
        )
    )
    db.session.add(
        Message(conversation_id=conv.id, is_user=False, text=payload["reply"])
    )
    db.session.commit()

    end = time.perf_counter()
    return jsonify(
        {
            "reply": payload["reply"],
            "receipt": payload["receipt"],
            "scan": payload["scan"],
            "time": f"{end: start:.2f}",
        }
    )


@receipts_bp.route("/api/receipts/colleagues")
@login_required
def api_receipts_colleagues():
    """Company roster for tagging meal companions on receipts."""
    from services.guardian import employees_by_name

    user = get_current_user()
    roster = []
    for name, info in sorted(
        employees_by_name().items(), key=lambda item: item[0].lower()
    ):
        if user.employee_name and name == user.employee_name:
            continue
        roster.append({"name": name, "department": str(info.get("department") or "-")})
    return jsonify(roster)


@receipts_bp.route("/api/receipts/scan", methods=["POST"])
@login_required
def api_receipts_scan():
    user = get_current_user()
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "file is required"}), 400

    file_bytes, _err = _validate_uploaded_file(file)
    if file_bytes is None:
        return jsonify({"error": _err}), 400

    mime_type = receipt_mime_type(file.filename or "", file.content_type)

    payload, err = run_receipt_scan(file_bytes, mime_type, user)
    if err:
        return jsonify({"error": err}), 400
    return jsonify(payload["scan"])


@receipts_bp.route("/api/receipts/confirm", methods=["POST"])
@login_required
def api_receipts_confirm():
    from services.receipts import confirm_receipt

    user = get_current_user()
    data = request.get_json(silent=True) or {}
    employee_id, employee_name, _ = receipt_employee_context(user)
    if not employee_name:
        return jsonify({"error": "Employee profile required to save receipts"}), 400

    try:
        amount = float(data.get("amount") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid receipt amount"}), 400
    payload = {
        "merchant": (data.get("merchant") or data.get("merchant_name") or "").strip(),
        "date": (data.get("date") or data.get("transaction_date") or "").strip(),
        "amount": amount,
        "category": (
            data.get("category") or data.get("expense_category") or ""
        ).strip(),
        "subtotal": data.get("subtotal"),
        "tax": data.get("tax"),
        "tip": data.get("tip"),
        "description": data.get("transaction_description") or data.get("description"),
        "mcc": data.get("mcc"),
        "type": data.get("type"),
        "merchant_city": data.get("merchant_city"),
        "merchant_state": data.get("merchant_state"),
        "merchant_country": data.get("merchant_country"),
        "merchant_postal_code": data.get("merchant_postal_code"),
        "currency": data.get("currency") or "CAD",
        "conversion_rate": data.get("conversion_rate"),
    }

    spending_purpose = (data.get("spending_purpose") or "").strip().lower()
    if spending_purpose not in ("personal", "project"):
        return jsonify({"error": "Please choose personal use or project use"}), 400
    payload["spending_purpose"] = spending_purpose

    from services.receipt_ocr import is_dining_receipt

    ext_for_dining = {
        "expense_category": payload.get("category"),
        "merchant_name": payload.get("merchant"),
        "mcc": payload.get("mcc"),
    }
    is_dining = bool(data.get("is_dining")) or is_dining_receipt(
        ext_for_dining,
        {"category": payload.get("category")} if payload.get("category") else None,
    )
    if is_dining:
        try:
            party_size = int(data.get("dining_party_size") or 1)
        except (TypeError, ValueError):
            return jsonify(
                {"error": "Enter how many people were at the meal (including you)"}
            ), 400
        if party_size < 1:
            return jsonify({"error": "Party size must be at least 1"}), 400
        from services.receipts import apply_dining_context

        payload = apply_dining_context(
            payload,
            party_size=party_size,
            dining_with=data.get("dining_with"),
            employee_name=employee_name,
        )

    project_id = None
    project_title = None
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
        project_title = proposal.title
        payload["project_id"] = project_id
        payload["project_title"] = project_title

    record = confirm_receipt(
        user_id=user.id,
        employee_name=employee_name,
        employee_id=employee_id or "",
        payload=payload,
        matched_transaction_id=data.get("matched_transaction_id"),
        spending_purpose=spending_purpose,
        project_id=project_id,
        project_title=project_title,
    )
    response = {
        "status": "saved",
        "receipt_id": record["receipt_id"],
        **record,
    }
    if record.get("csv_action") == "appended":
        response["message"] = "Receipt saved and added to your transaction history."
    elif record.get("csv_action") == "linked":
        response["message"] = "Receipt linked to your existing card transaction."
    elif record.get("csv_error"):
        response["csv_warning"] = record["csv_error"]
    return jsonify(response)


@receipts_bp.route("/api/receipts", methods=["GET"])
@login_required
def api_receipts_list():
    from services.receipts import list_receipts

    user = get_current_user()
    if can_see_all(user):
        records = list_receipts()
    else:
        records = list_receipts(employee_name=user.employee_name)
    return jsonify(records)

