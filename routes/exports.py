"""Export routes: PDF reports and chat chart images."""

from __future__ import annotations

from flask import Blueprint, jsonify, request, send_file

from core.auth import login_required
from routes.helpers import employee_scope_name

exports_bp = Blueprint("exports", __name__)


@exports_bp.route("/api/report/pdf", methods=["POST"])
@login_required
def api_report_pdf():
    from services.pdf_report import build_pdf_filename, build_spending_pdf

    data = request.json or {}
    names = data.get("names") or []
    scope = employee_scope_name()
    if scope:
        names = [n for n in names if n == scope]
        if not names:
            names = [scope]
    try:
        pdf_buffer = build_spending_pdf(names)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=build_pdf_filename(names),
    )


@exports_bp.route("/api/chat/chart/<filename>")
@login_required
def api_chat_chart(filename):
    from ai.charts import chat_chart_path

    path = chat_chart_path(filename)
    if not path.is_file():
        return jsonify({"error": "Chart not found"}), 404
    return send_file(path, mimetype="image/png")

