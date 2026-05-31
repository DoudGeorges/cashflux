from flask import Flask, render_template, request, jsonify, session, send_file
from google import genai
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from dotenv import load_dotenv
from expense_data import (
    build_gemini_context,
    compare_employees,
    get_charts_for_query,
    get_dashboard,
    get_employee_detail,
    get_map_locations,
    get_map_merchants,
    list_employees,
    list_purchases,
)
import expense_data
from pdf_report import build_pdf_filename, build_spending_pdf
import os
import time

load_dotenv()

from company_data import DEFAULT_COMPANY_SLUG, migrate_legacy_data_to_default_company, set_company_context

migrate_legacy_data_to_default_company()
set_company_context(0, DEFAULT_COMPANY_SLUG)

from guardian_data import clear_cache

clear_cache()

try:
    import brim_bridge
    import brim_csv_queries
except ImportError:
    brim_bridge = None
    brim_csv_queries = None

WELCOME_MESSAGE = (
    "Hi! I'm Friday — your AI assistant for CashFlux. "
    "Ask about spending, or tell me to approve requests, change budgets, update rules, submit a project, or open any page."
)

app = Flask(__name__)

API_KEY = os.getenv("API") or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=API_KEY) if API_KEY else None
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chats.db'
db = SQLAlchemy(app)
app.secret_key = os.getenv('SECRET_KEY', 'CanWeGet100Percent?')
app.config['PERMANENT_SESSION_LIFETIME'] = 86400 * 14

from auth import (
    bind as bind_auth,
    register_auth_routes,
    get_current_user,
    can_see_all,
    employee_scope,
    login_required,
    admin_required,
    user_to_dict,
)

User, Company = bind_auth(db)
register_auth_routes(app)


@app.route("/api/health")
def api_health():
    return jsonify({"ok": True, "service": "cashflux"})


@app.errorhandler(404)
def api_not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Not found"}), 404
    return "Not found", 404


@app.errorhandler(500)
def api_server_error(e):
    if request.path.startswith("/api/"):
        app.logger.exception("API error on %s", request.path)
        return jsonify({"error": "Server error — try refreshing or restarting the app."}), 500
    return "Internal server error", 500


@app.before_request
def _set_company_data_context():
    from company_data import ensure_company_data, set_company_context, clear_company_context
    from guardian_data import clear_cache

    user = get_current_user()
    if user and user.company:
        ensure_company_data(user.company_id, user.company.slug)
        set_company_context(user.company_id, user.company.slug)
    else:
        clear_company_context()


def _scope():
    user = get_current_user()
    return employee_scope(user)


def _chat_user_id():
    user = get_current_user()
    return user.id if user else None


def _google_maps_api_key():
    return os.getenv("GOOGLE_MAPS_API_KEY") or os.getenv("API", "")


@app.context_processor
def inject_globals():
    user = get_current_user()
    return {
        "google_maps_api_key": _google_maps_api_key(),
        "current_user": user,
        "is_admin_view": can_see_all(user),
    }

class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversation.id"), nullable=False)
    is_user = db.Column(db.Boolean, nullable=False)
    text = db.Column(db.Text, nullable=False)
    lewis_structure = db.Column(db.String(500))
    vsepr = db.Column(db.String(500))


class WorkflowDecision(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_key = db.Column(db.String(300), unique=True, nullable=False)
    item_type = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    decided_at = db.Column(db.DateTime, default=datetime.now)
    note = db.Column(db.Text)


class ProjectProposal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    company_id = db.Column(db.Integer, db.ForeignKey("company.id"), nullable=False, index=True)
    employee_name = db.Column(db.String(120), nullable=False)
    department = db.Column(db.String(120), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    requested_amount = db.Column(db.Float, nullable=False)
    quarter = db.Column(db.String(32))
    status = db.Column(db.String(20), nullable=False, default="pending")
    submitted_at = db.Column(db.DateTime, default=datetime.now)
    decided_at = db.Column(db.DateTime)
    decided_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    decision_note = db.Column(db.Text)
    budget_snapshot = db.Column(db.Text)
    budget_source = db.Column(db.String(32), nullable=False, default="existing")
    colleagues = db.Column(db.Text)  # JSON list of employee names on this project


class EmployeeTripReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    company_id = db.Column(db.Integer, db.ForeignKey("company.id"), nullable=False, index=True)
    employee_name = db.Column(db.String(120), nullable=False)
    department = db.Column(db.String(120), nullable=False)
    trip_name = db.Column(db.String(200), nullable=False)
    purpose = db.Column(db.Text)
    transaction_keys = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending_cfo")
    submitted_at = db.Column(db.DateTime, default=datetime.now)
    decided_at = db.Column(db.DateTime)
    decided_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    decision_note = db.Column(db.Text)
    spending_purpose = db.Column(db.String(20), nullable=False, default="personal")
    project_id = db.Column(db.Integer, db.ForeignKey("project_proposal.id"))

@app.route("/")
@login_required
def index():
    session.pop('story', None)
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
@login_required
def chat():
    from voice_assistant import (
        _strip_for_speech,
        detect_voice_actions,
        try_instant_response,
        VOICE_VERBOSITY,
    )
    from assistant_context import build_voice_context_block
    from friday_tools import message_wants_actions as _message_wants_actions

    excuses = [
        "Gemini is temporarily unavailable. Your spending data is safe locally — try again in a moment.",
        "The Vultr backend is reconnecting. Chat queries will resume shortly.",
        "Spend Analyst is warming up. Please retry your query.",
    ]

    start = time.perf_counter()

    data = request.json
    user_message = data.get("message")
    conv_id = data.get("conversation_id")
    voice_mode = bool(data.get("voice"))
    current_view = (data.get("current_view") or "overview").strip()
    verbosity = data.get("verbosity", "less" if voice_mode else "medium")

    uid = _chat_user_id()
    conv = Conversation.query.filter_by(id=conv_id, user_id=uid).first() if conv_id else None
    if not conv or not user_message:
        return jsonify({"reply": "Pick a chat from the list or start a new one."}), 400

    verbosity_map = {
        "not at all": "Respond in 1-2 sentences with only the key number or recommendation.",
        "less": "Be extremely concise. Lead with the answer in 2-4 sentences.",
        "medium": "Provide a standard finance summary of moderate length with key figures.",
        "a lot": "Be thorough. Include breakdowns, comparisons, trends, and actionable context for the CFO.",
    }

    selected_constraint = verbosity_map.get(verbosity, verbosity_map["medium"])

    def _persist_and_reply(reply, **extra):
        db.session.add(Message(conversation_id=conv.id, is_user=True, text=user_message))
        db.session.add(Message(conversation_id=conv.id, is_user=False, text=reply))
        db.session.commit()
        end = time.perf_counter()
        actions = extra.pop("actions", None)
        if actions is None:
            actions = detect_voice_actions(user_message, current_view)
        payload = {"reply": reply, "time": f"{end - start:.2f}", "actions": actions, **extra}
        return jsonify(payload)

    instant = try_instant_response(
        user_message,
        current_view,
        employee_name=_scope(),
        is_admin=can_see_all(get_current_user()),
    )
    if instant:
        return _persist_and_reply(
            instant["reply"],
            engine=instant.get("engine", "instant"),
            chart_urls=instant.get("chart_urls", []),
            tool_calls=instant.get("tool_calls", []),
            actions=instant.get("actions", []),
        )

    past_messages = Message.query.filter_by(conversation_id=conv_id).order_by(Message.id.asc()).all()

    def _visual_payload(existing_chart_urls=None):
        """Attach Chart.js insight only when a visualization is warranted."""
        from spending_query import wants_visualization

        if voice_mode and not wants_visualization(user_message or "", past_messages):
            return {}

        insight = get_charts_for_query(
            user_message, conversation_history=past_messages, employee_name=_scope()
        )
        if not insight:
            return {}
        return {"insight": {k: v for k, v in insight.items() if not k.startswith("_")}}

    history = []
    for msg in past_messages:
        role = "user" if msg.is_user else "model"
        history.append({"role": role, "parts": [{"text": msg.text}]})

    brim_history = [{"role": "user" if m.is_user else "assistant", "text": m.text} for m in past_messages]

    history.append({"role": "user", "parts": [{"text": user_message}]})

    chat_input = user_message
    if voice_mode:
        site_block = build_voice_context_block(current_view)
        chat_input = (
            f"{VOICE_VERBOSITY}\n\n=== SITE SNAPSHOT ===\n{site_block}\n\n"
            f"User question: {user_message}"
        )

    try:
        from spending_query import get_query_figures_block, wants_visualization

        use_brim = (
            brim_bridge
            and brim_bridge.is_available()
            and not voice_mode
            and not wants_visualization(user_message, past_messages)
            and not _message_wants_actions(user_message)
        )
        if use_brim:
            try:
                result = brim_bridge.run_chat(chat_input, history=brim_history)
                reply = result.get("text", "")
                if voice_mode:
                    reply = _strip_for_speech(reply)
                chart_urls = [
                    f"/api/brim/chart/{brim_bridge.chart_filename(path)}"
                    for path in result.get("chart_paths", [])
                    if path
                ]
                tool_calls = result.get("tool_calls", [])

                return _persist_and_reply(
                    reply,
                    tool_calls=tool_calls,
                    engine="brim-guardian",
                    **_visual_payload(chart_urls),
                )
            except Exception as brim_err:
                print(f"Brim Guardian fallback: {brim_err}")

        with open("prompt.txt", "r", encoding="utf-8") as f:
            system_prompt = f.read()

        expense_context = build_gemini_context(user_message, conversation_history=past_messages, employee_name=_scope())
        from spending_query import get_query_figures_block

        insight = get_charts_for_query(user_message, conversation_history=past_messages, employee_name=_scope())
        if insight and insight.get("_context_block"):
            expense_context += (
                "\n\nCHART DATA (use these exact figures; a live chart renders below):\n"
                + insight["_context_block"]
            )
        elif insight and insight.get("summary"):
            expense_context += (
                "\n\nCHART DATA (use these exact figures; a live chart renders below):\n"
                + insight["summary"].replace("**", "")
            )
        else:
            figures = get_query_figures_block(
                user_message, conversation_history=past_messages, employee_name=_scope()
            )
            if figures:
                expense_context += (
                    "\n\nQUERY ANSWER DATA (use these exact figures; no chart for this question):\n"
                    + figures
                )
        scope = _scope()
        personal_scope = ""
        if scope:
            personal_scope = (
                f"\n\nPERSONAL DATA SCOPE: Purchases below belong to {scope} only. "
                "Never name or rank other employees. If asked who spends the most or least "
                "company-wide, answer about this user's own purchases instead (e.g. their "
                "largest or smallest transaction, or top spending category). "
                "Do not mention roles, admin access, or permissions."
            )
        voice_block = ""
        if voice_mode:
            voice_block = (
                f"\n\n{VOICE_VERBOSITY}\n\n=== SITE SNAPSHOT ===\n"
                f"{build_voice_context_block(current_view)}\n"
            )
        system_prompt_with_verbosity = (
            f"{system_prompt}{personal_scope}{voice_block}\n\nVERBOSITY GUIDELINE: {selected_constraint}\n\n"
            f"=== LIVE EXPENSE DATA ({expense_data.CSV_NAME}) ===\n"
            f"Use ONLY the figures below. Do not invent numbers.\n\n{expense_context}"
        )
        if client is None:
            visual = _visual_payload()
            insight = visual.get("insight") or {}
            reply = insight.get("summary", "Chart generated from your expense data.").replace("**", "")
            return _persist_and_reply(reply, engine="chart-only", **visual)

        from friday_agent import run_friday_chat
        from friday_tools import FridayContext

        friday_ctx = FridayContext(
            user=get_current_user(),
            is_admin=can_see_all(get_current_user()),
            employee_name=_scope(),
            current_view=current_view,
            invalidate_cache=_invalidate_nav_cache,
            pending_proposals_fn=_pending_proposal_items,
            decided_keys_fn=_decided_keys,
            fraud_overrides_fn=_fraud_status_overrides,
        )
        agent_result = run_friday_chat(
            client,
            history=history,
            system_prompt=system_prompt_with_verbosity,
            ctx=friday_ctx,
        )
        reply = agent_result.get("reply") or ""
        if voice_mode:
            reply = _strip_for_speech(reply)
        actions = agent_result.get("actions") or detect_voice_actions(user_message, current_view)
        return _persist_and_reply(
            reply,
            tool_calls=agent_result.get("tool_calls") or [],
            actions=actions,
            engine=agent_result.get("engine", "friday-agent"),
            **_visual_payload(),
        )

    except Exception as e:
        if 'story' not in session:
            session['story'] = 0
        
        current_index = session['story']
        
        if current_index >= len(excuses):
            current_index = len(excuses) - 1
            
        current_msg = excuses[current_index]
        session['story'] = min(current_index + 1, len(excuses) - 1)

        print(f"Error: {e}")
        try:
            visual = _visual_payload()
        except Exception:
            visual = {}
        if visual.get("chart_urls"):
            insight = visual.get("insight") or {}
            reply = insight.get("summary", "Here is the chart you asked for.").replace("**", "")
            return _persist_and_reply(reply, engine="chart-fallback", **visual)

        end = time.perf_counter()
        return jsonify({"reply": current_msg, "time": f"{end - start:.2f}"}), 500


_nav_cache = {"data": None, "at": 0.0}


def _invalidate_nav_cache():
    _nav_cache["data"] = None
    _nav_cache["at"] = 0.0


def _pending_proposal_items():
    from proposal_data import proposal_to_review_item, serialize_proposal

    rows = (
        ProjectProposal.query.filter_by(status="pending")
        .order_by(ProjectProposal.submitted_at.asc())
        .all()
    )
    return [proposal_to_review_item(serialize_proposal(p)) for p in rows]


@app.route("/api/nav")
@login_required
def api_nav():
    import time
    from guardian_data import employee_summary, flagged_transactions, get_approvals_list, get_reports_list, transactions

    scope = _scope()
    if scope:
        from expense_data import scoped_expenses
        rows = scoped_expenses(scope)
        return jsonify({
            "flags": sum(1 for r in rows if r.get("flagged") == "yes"),
            "approvals": 0,
            "reports_pending": 0,
            "employees": 1,
            "transactions": len(rows),
            "review_pending": 0,
            "fraud_pending": 0,
        })

    now = time.time()
    if _nav_cache["data"] and now - _nav_cache["at"] < 30:
        return jsonify(_nav_cache["data"])

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
        from review_data import build_review_stats

        review = build_review_stats(
            approval_exclude=_decided_keys("approval"),
            fraud_status_overrides=_fraud_status_overrides(),
            proposal_items=_pending_proposal_items(),
            flag_exclude=_decided_keys("flag"),
            report_status_overrides=_report_status_overrides(),
        )
        payload["approvals"] = review.get("approvals_pending", 0)
        payload["fraud_pending"] = review.get("fraud_pending", 0)
        payload["review_pending"] = review.get("total_pending", 0)
        payload["flags_pending"] = review.get("flags_pending", 0)
        payload["proposals_pending"] = review.get("proposals_pending", 0)
        payload["reports_pending"] = review.get("reports_pending", payload.get("reports_pending", 0))
    except Exception:
        payload["approvals"] = len(approvals)
        payload["fraud_pending"] = 0
        payload["review_pending"] = len(approvals)
    _nav_cache["data"] = payload
    _nav_cache["at"] = now
    return jsonify(payload)


@app.route("/api/surprise")
@login_required
def api_surprise():
    from surprise_data import build_spending_oracle

    return jsonify(build_spending_oracle(employee_name=_scope()))


@app.route("/api/vendor-consolidation")
@login_required
def api_vendor_consolidation():
    from vendor_consolidation import analyze_vendor_consolidation

    return jsonify(analyze_vendor_consolidation(employee_name=_scope()))


@app.route("/api/voice/ready")
@login_required
def api_voice_ready():
    """Warm the ElevenLabs client on first mic use."""
    from voice_tts import is_available

    if is_available():
        try:
            from voice_tts import warm_client

            warm_client()
        except Exception as exc:
            print(f"ElevenLabs warm-up: {exc}")
    return jsonify({"elevenlabs": is_available()})


@app.route("/api/voice/tts", methods=["POST"])
@login_required
def api_voice_tts():
    from flask import Response, stream_with_context

    from voice_assistant import _strip_for_speech
    from voice_tts import is_available, stream_speech

    if not is_available():
        return jsonify({"error": "ElevenLabs not configured"}), 503

    data = request.get_json(silent=True) or {}
    text = _strip_for_speech(data.get("text") or "")
    if not text:
        return jsonify({"error": "No text to speak"}), 400

    def generate():
        try:
            yield from stream_speech(text)
        except Exception as exc:
            print(f"ElevenLabs TTS stream: {exc}")

    return Response(
        stream_with_context(generate()),
        mimetype="audio/mpeg",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@app.route("/api/dashboard")
@login_required
def api_dashboard():
    return jsonify(get_dashboard(employee_name=_scope()))


@app.route("/api/budget")
@login_required
@admin_required
def api_budget():
    from budget_data import get_budget_overview

    try:
        resp = jsonify(get_budget_overview())
        resp.headers["Cache-Control"] = "no-store"
        return resp
    except Exception:
        app.logger.exception("Failed to build budget overview")
        return jsonify({"error": "Could not load budget data."}), 500


@app.route("/api/budget/forecast")
@login_required
@admin_required
def api_budget_forecast():
    from budget_data import forecast_department, get_forecast_for_query

    dept = request.args.get("department", "").strip()
    q = request.args.get("q", "").strip()
    if dept:
        return jsonify(forecast_department(dept))
    if q:
        result = get_forecast_for_query(q)
        if result:
            return jsonify(result)
        return jsonify({"error": "No forecast matched query"}), 404
    from budget_data import get_department_forecasts

    return jsonify(get_department_forecasts())


@app.route("/api/settings/budgets", methods=["GET", "PUT"])
@login_required
@admin_required
def api_settings_budgets():
    from budget_data import get_budget_settings, save_quarter_budgets

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
    _invalidate_nav_cache()
    return jsonify({**get_budget_settings(), "status": "saved"})


@app.route("/api/employees")
@login_required
def api_employees():
    return jsonify(list_employees(employee_name=_scope()))


@app.route("/api/employee")
@login_required
def api_employee():
    name = request.args.get("name", "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    detail = get_employee_detail(name, employee_name=_scope())
    if not detail:
        return jsonify({"error": "employee not found"}), 404
    try:
        from peer_benchmark import peer_benchmark_for_employee

        bench = peer_benchmark_for_employee(name)
        if bench:
            detail["peer_benchmark"] = bench
    except ImportError:
        pass
    return jsonify(detail)


@app.route("/api/flags")
@login_required
@admin_required
def api_flags():
    from guardian_data import get_flags_list

    return jsonify(get_flags_list(exclude_keys=_decided_keys("flag")))


@app.route("/api/policy/rules", methods=["GET", "PUT"])
@login_required
@admin_required
def api_policy_rules():
    from policy_engine import (
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
        return jsonify({
            "rules": load_policy_rules(),
            "document": load_policy_document(),
            "summary": policy_summary_text(),
            "schema": get_policy_schema(),
            "departments": list_policy_departments(),
            "dept_override_fields": DEPT_OVERRIDE_FIELDS,
        })
    data = request.json or {}
    rules = save_policy_rules(data.get("rules") or data)
    document = data.get("document")
    if document is not None:
        save_policy_document(document)
    clear_cache()
    _invalidate_nav_cache()
    return jsonify({
        "rules": rules,
        "document": load_policy_document(),
        "summary": policy_summary_text(),
        "status": "saved",
    })


@app.route("/api/policy/offenders")
@login_required
@admin_required
def api_policy_offenders():
    from policy_engine import get_repeat_offenders

    return jsonify(get_repeat_offenders(limit=12))


@app.route("/api/policy/import", methods=["POST"])
@login_required
@admin_required
def api_policy_import():
    from policy_import import apply_imported_policy, extract_policy_from_document

    file = request.files.get("file")
    if not file:
        return jsonify({"error": "file is required"}), 400

    file_bytes = file.read()
    if len(file_bytes) > 15 * 1024 * 1024:
        return jsonify({"error": "File too large (max 15 MB)"}), 400

    mime_type = _receipt_mime_type(file.filename or "", file.content_type)
    if mime_type != "application/pdf" and not mime_type.startswith("text/"):
        return jsonify({"error": "Upload a PDF or text policy document"}), 400

    extracted = extract_policy_from_document(file_bytes, mime_type)
    if extracted.get("error"):
        return jsonify({"error": extracted["error"]}), 400

    try:
        result = apply_imported_policy(extracted)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    clear_cache()
    _invalidate_nav_cache()
    import expense_data

    expense_data.reload_expense_cache()

    from policy_engine import policy_summary_text

    result["summary"] = policy_summary_text()
    return jsonify(result)


def _decided_keys(item_type: str) -> set[str]:
    rows = WorkflowDecision.query.filter_by(item_type=item_type).all()
    return {r.item_key for r in rows}


expense_data.register_resolved_flag_keys_provider(lambda: _decided_keys("flag"))


def _fraud_status_overrides() -> dict[str, str]:
    rows = WorkflowDecision.query.filter_by(item_type="fraud").all()
    return {r.item_key: r.status for r in rows}


def _report_status_overrides() -> dict[str, str]:
    rows = WorkflowDecision.query.filter_by(item_type="report").all()
    return {r.item_key: r.status for r in rows}


def _claimed_trip_transaction_keys(company_id: int, employee_name: str | None = None) -> set[str]:
    from trip_report_data import parse_transaction_keys

    query = EmployeeTripReport.query.filter_by(company_id=company_id).filter(
        EmployeeTripReport.status.in_(("pending_cfo", "approved"))
    )
    if employee_name:
        query = query.filter_by(employee_name=employee_name)
    claimed: set[str] = set()
    for row in query.all():
        claimed.update(parse_transaction_keys(row.transaction_keys))
    return claimed


def _submitted_trip_report_dicts(status_overrides: dict | None = None) -> list[dict]:
    from trip_report_data import build_report_dict, parse_transaction_keys, submission_report_key

    user = get_current_user()
    if not user or not user.company_id:
        return []
    status_overrides = status_overrides or {}
    reports: list[dict] = []
    rows = (
        EmployeeTripReport.query.filter_by(company_id=user.company_id)
        .order_by(EmployeeTripReport.submitted_at.desc())
        .all()
    )
    for model in rows:
        key = submission_report_key(model.id)
        status = status_overrides.get(key, model.status or "pending_cfo")
        report = build_report_dict(
            report_id=model.id,
            employee_name=model.employee_name,
            department=model.department,
            trip_name=model.trip_name,
            purpose=model.purpose or "",
            transaction_keys=parse_transaction_keys(model.transaction_keys),
            status=status,
            spending_purpose=model.spending_purpose or "personal",
            project_id=model.project_id,
            project_title=_trip_report_project_title(model.project_id),
        )
        if report:
            reports.append(report)
    return reports


def _resolve_submitted_report(report_key: str) -> dict | None:
    from trip_report_data import build_report_dict, parse_transaction_keys, submission_report_key

    if not report_key.startswith("submitted:"):
        return None
    try:
        report_id = int(report_key.split(":", 1)[1])
    except (TypeError, ValueError):
        return None
    model = EmployeeTripReport.query.get(report_id)
    if not model:
        return None
    override = WorkflowDecision.query.filter_by(item_key=report_key, item_type="report").first()
    status = override.status if override else (model.status or "pending_cfo")
    return build_report_dict(
        report_id=model.id,
        employee_name=model.employee_name,
        department=model.department,
        trip_name=model.trip_name,
        purpose=model.purpose or "",
        transaction_keys=parse_transaction_keys(model.transaction_keys),
        status=status,
        spending_purpose=model.spending_purpose or "personal",
        project_id=model.project_id,
        project_title=_trip_report_project_title(model.project_id),
    )


def _apply_trip_report_decision(report_key: str, approved: bool, note: str | None = None) -> str:
    status = "approved" if approved else "rejected"
    existing = WorkflowDecision.query.filter_by(item_key=report_key, item_type="report").first()
    if existing:
        raise ValueError("Already decided")
    db.session.add(
        WorkflowDecision(
            item_key=report_key,
            item_type="report",
            status=status,
            note=note,
        )
    )
    if report_key.startswith("submitted:"):
        try:
            report_id = int(report_key.split(":", 1)[1])
        except (TypeError, ValueError):
            report_id = None
        if report_id:
            model = EmployeeTripReport.query.get(report_id)
            if model:
                model.status = status
                model.decided_at = datetime.now()
                model.decision_note = (note or "").strip() or None
                admin = get_current_user()
                if admin:
                    model.decided_by_user_id = admin.id
    db.session.commit()
    return status


def _persist_fraud_decision(txn_id: str, action: str, note: str | None = None) -> None:
    existing = WorkflowDecision.query.filter_by(item_key=txn_id, item_type="fraud").first()
    if existing:
        existing.status = action
        if note is not None:
            existing.note = note
    else:
        db.session.add(
            WorkflowDecision(
                item_key=txn_id,
                item_type="fraud",
                status=action,
                note=note,
            )
        )
    db.session.commit()


@app.route("/api/review/queue")
@login_required
@admin_required
def api_review_queue():
    from review_data import build_review_queue

    overrides = _report_status_overrides()
    submitted = _submitted_trip_report_dicts(overrides)
    return jsonify(
        build_review_queue(
            approval_exclude=_decided_keys("approval"),
            fraud_status_overrides=_fraud_status_overrides(),
            proposal_items=_pending_proposal_items(),
            flag_exclude=_decided_keys("flag"),
            report_status_overrides=overrides,
            submitted_trip_reports=submitted,
        )
    )


@app.route("/api/review/stats")
@login_required
@admin_required
def api_review_stats():
    from review_data import build_review_stats

    overrides = _report_status_overrides()
    submitted = _submitted_trip_report_dicts(overrides)
    return jsonify(
        build_review_stats(
            approval_exclude=_decided_keys("approval"),
            fraud_status_overrides=_fraud_status_overrides(),
            proposal_items=_pending_proposal_items(),
            flag_exclude=_decided_keys("flag"),
            report_status_overrides=overrides,
            submitted_trip_reports=submitted,
        )
    )


@app.route("/api/review/action", methods=["POST"])
@login_required
@admin_required
def api_review_action():
    from fraud_data import review_transaction

    data = request.get_json(silent=True) or {}
    item_id = data.get("id") or ""
    action = (data.get("action") or "").lower()

    if item_id.startswith("approval:"):
        item_key = item_id.split(":", 1)[1]
        if action not in ("approve", "deny"):
            return jsonify({"error": "Invalid action for approval"}), 400
        existing = WorkflowDecision.query.filter_by(item_key=item_key, item_type="approval").first()
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
        _invalidate_nav_cache()
        return jsonify({"status": status, "id": item_id})

    if item_id.startswith("flag:"):
        item_key = item_id.split(":", 1)[1]
        if action not in ("approve", "deny"):
            return jsonify({"error": "Invalid action for flagged purchase"}), 400
        existing = WorkflowDecision.query.filter_by(item_key=item_key, item_type="flag").first()
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
        import expense_data
        expense_data.reload_expense_cache()
        _invalidate_nav_cache()
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
        _persist_fraud_decision(txn_id, fraud_action, data.get("note"))
        _invalidate_nav_cache()
        return jsonify({"status": fraud_action, "id": item_id})

    if item_id.startswith("proposal:"):
        try:
            proposal_id = int(item_id.split(":", 1)[1])
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid proposal id"}), 400
        if action not in ("approve", "deny"):
            return jsonify({"error": "Invalid action for proposal"}), 400
        proposal = ProjectProposal.query.get(proposal_id)
        if not proposal:
            return jsonify({"error": "Proposal not found"}), 404
        if proposal.status != "pending":
            return jsonify({"error": "Already decided", "status": proposal.status}), 409
        admin = get_current_user()
        budget_update = None
        if action == "approve" and (proposal.budget_source or "") == "extra":
            from budget_data import apply_extra_budget_approval

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
        _invalidate_nav_cache()
        payload = {"status": proposal.status, "id": item_id}
        if budget_update:
            payload["budget_update"] = budget_update
        return jsonify(payload)

    if item_id.startswith("report:"):
        report_key = item_id.split(":", 1)[1]
        if action not in ("approve", "deny"):
            return jsonify({"error": "Invalid action for trip report"}), 400
        existing = WorkflowDecision.query.filter_by(item_key=report_key, item_type="report").first()
        if existing:
            return jsonify({"error": "Already decided", "status": existing.status}), 409
        try:
            status = _apply_trip_report_decision(report_key, action == "approve", data.get("note"))
        except ValueError:
            return jsonify({"error": "Already decided"}), 409
        _invalidate_nav_cache()
        return jsonify({"status": status, "id": item_id})

    return jsonify({"error": "Unknown review item"}), 400


@app.route("/api/approvals")
@login_required
@admin_required
def api_approvals():
    from guardian_data import get_approvals_list

    return jsonify(get_approvals_list(exclude_keys=_decided_keys("approval")))


@app.route("/api/approvals/<path:item_key>/decide", methods=["POST"])
@login_required
@admin_required
def api_approval_decide(item_key):
    data = request.json or {}
    approved = bool(data.get("approved"))
    existing = WorkflowDecision.query.filter_by(item_key=item_key, item_type="approval").first()
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
    _invalidate_nav_cache()
    return jsonify({"status": status, "item_key": item_key})


@app.route("/api/proposals/colleagues")
@login_required
def api_proposals_colleagues():
    """Company roster for adding teammates to a project (excludes the current user)."""
    from guardian_data import employees_by_name

    user = get_current_user()
    if can_see_all(user):
        return jsonify({"error": "Only employees add colleagues to projects"}), 403
    roster = []
    for name, info in sorted(employees_by_name().items(), key=lambda item: item[0].lower()):
        if name == user.employee_name:
            continue
        roster.append({
            "name": name,
            "department": str(info.get("department") or "—"),
        })
    return jsonify(roster)


def _approved_proposals_for_user(user):
    """Approved projects the user owns or was invited to as a colleague."""
    from proposal_data import parse_colleagues

    own = (
        ProjectProposal.query.filter_by(user_id=user.id, status="approved")
        .order_by(ProjectProposal.title.asc())
        .all()
    )
    if not user.employee_name:
        return own
    seen = {p.id for p in own}
    shared = []
    for proposal in ProjectProposal.query.filter_by(
        company_id=user.company_id, status="approved"
    ).all():
        if proposal.id in seen:
            continue
        if user.employee_name in parse_colleagues(proposal.colleagues):
            shared.append(proposal)
    return own + sorted(shared, key=lambda p: p.title.lower())


def _trip_report_project_title(project_id: int | None) -> str | None:
    if not project_id:
        return None
    proposal = ProjectProposal.query.get(project_id)
    return proposal.title if proposal else None


def _user_can_use_project(user, proposal) -> bool:
    from proposal_data import parse_colleagues

    if not proposal or proposal.status != "approved":
        return False
    if proposal.user_id == user.id:
        return True
    return bool(user.employee_name and user.employee_name in parse_colleagues(proposal.colleagues))


@app.route("/api/proposals/mine")
@login_required
def api_proposals_mine():
    from proposal_data import serialize_proposal
    from receipt_store import project_spend_by_user

    user = get_current_user()
    spend = project_spend_by_user(user.id)
    rows = (
        ProjectProposal.query.filter_by(user_id=user.id)
        .order_by(ProjectProposal.submitted_at.desc())
        .all()
    )
    return jsonify([serialize_proposal(p, spent=spend.get(p.id, 0)) for p in rows])


@app.route("/api/proposals/approved")
@login_required
def api_proposals_approved():
    from proposal_data import approved_project_option
    from receipt_store import project_spend_by_user

    user = get_current_user()
    spend = project_spend_by_user(user.id)
    rows = _approved_proposals_for_user(user)
    return jsonify([
        approved_project_option(p, spent=spend.get(p.id, 0))
        for p in rows
    ])


@app.route("/api/proposals/budget-hint")
@login_required
def api_proposals_budget_hint():
    from proposal_data import build_budget_snapshot, employee_department

    user = get_current_user()
    if not user.employee_name:
        return jsonify({"error": "No employee profile linked to this account"}), 400
    dept = employee_department(user.employee_name)
    snapshot = build_budget_snapshot(dept)
    return jsonify({
        "employee_name": user.employee_name,
        "department": dept,
        **snapshot,
    })


@app.route("/api/proposals", methods=["POST"])
@login_required
def api_proposals_create():
    from proposal_data import build_budget_snapshot, employee_department, normalize_colleagues, serialize_proposal

    user = get_current_user()
    if can_see_all(user):
        return jsonify({"error": "Only employees submit project proposals"}), 403
    if not user.employee_name:
        return jsonify({"error": "Your account is not linked to an employee profile"}), 400

    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()
    try:
        amount = float(data.get("requested_amount", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid budget amount"}), 400

    if len(title) < 3:
        return jsonify({"error": "Project title is required (at least 3 characters)"}), 400
    if len(description) < 10:
        return jsonify({"error": "Please describe the project (at least 10 characters)"}), 400
    if amount <= 0:
        return jsonify({"error": "Budget amount must be greater than zero"}), 400

    budget_source = (data.get("budget_source") or "").strip().lower()
    if budget_source not in ("existing", "extra"):
        return jsonify({"error": "Please choose whether this uses existing budget or requests extra budget"}), 400

    dept = employee_department(user.employee_name)
    snapshot = build_budget_snapshot(dept)
    import json
    from guardian_data import employees_by_name

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
    _invalidate_nav_cache()
    return jsonify(serialize_proposal(proposal)), 201


@app.route("/api/reports")
@login_required
@admin_required
def api_reports():
    from guardian_data import get_reports_list
    from trip_report_data import merge_trip_report_lists

    overrides = {
        r.item_key: r.status
        for r in WorkflowDecision.query.filter_by(item_type="report").all()
    }
    submitted = _submitted_trip_report_dicts(overrides)
    auto = get_reports_list(status_overrides=overrides, include_submitted=False)
    return jsonify(merge_trip_report_lists(auto, submitted))


@app.route("/api/reports/<path:report_key>")
@login_required
@admin_required
def api_report_detail(report_key):
    from guardian_data import get_report_detail

    detail = _resolve_submitted_report(report_key) or get_report_detail(report_key)
    if not detail:
        return jsonify({"error": "Report not found"}), 404
    row = WorkflowDecision.query.filter_by(item_key=report_key, item_type="report").first()
    detail["status"] = row.status if row else detail.get("status", "pending_cfo")
    return jsonify(detail)


@app.route("/api/reports/<path:report_key>/decide", methods=["POST"])
@login_required
@admin_required
def api_report_decide(report_key):
    data = request.json or {}
    approved = bool(data.get("approved"))
    existing = WorkflowDecision.query.filter_by(item_key=report_key, item_type="report").first()
    if existing:
        return jsonify({"error": "Already decided", "status": existing.status}), 409
    try:
        status = _apply_trip_report_decision(report_key, approved, data.get("note"))
    except ValueError:
        return jsonify({"error": "Already decided"}), 409
    _invalidate_nav_cache()
    return jsonify({"status": status, "report_key": report_key})


@app.route("/api/trip-reports/transactions")
@login_required
def api_trip_report_transactions():
    from trip_report_data import eligible_transactions

    user = get_current_user()
    if can_see_all(user):
        return jsonify({"error": "Only employees submit trip reports"}), 403
    if not user.employee_name:
        return jsonify({"error": "Your account is not linked to an employee profile"}), 400
    claimed = _claimed_trip_transaction_keys(user.company_id, user.employee_name)
    return jsonify(eligible_transactions(user.employee_name, claimed))


@app.route("/api/trip-reports/mine")
@login_required
def api_trip_reports_mine():
    from trip_report_data import serialize_submission

    user = get_current_user()
    if can_see_all(user):
        return jsonify({"error": "Only employees view their trip reports here"}), 403
    overrides = _report_status_overrides()
    rows = (
        EmployeeTripReport.query.filter_by(user_id=user.id)
        .order_by(EmployeeTripReport.submitted_at.desc())
        .all()
    )
    return jsonify([
        serialize_submission(
            row,
            overrides.get(f"submitted:{row.id}"),
            _trip_report_project_title(row.project_id),
        )
        for row in rows
    ])


@app.route("/api/trip-reports", methods=["POST"])
@login_required
def api_trip_reports_create():
    import json as json_module

    from trip_report_data import (
        parse_transaction_keys,
        resolve_department,
        serialize_submission,
        transaction_key,
    )
    from expense_data import scoped_expenses

    user = get_current_user()
    if can_see_all(user):
        return jsonify({"error": "Only employees submit trip reports"}), 403
    if not user.employee_name:
        return jsonify({"error": "Your account is not linked to an employee profile"}), 400

    data = request.get_json(silent=True) or {}
    trip_name = (data.get("trip_name") or "").strip()
    purpose = (data.get("purpose") or "").strip()
    raw_keys = data.get("transaction_keys") or []

    if not trip_name:
        return jsonify({"error": "Trip name is required"}), 400
    if not isinstance(raw_keys, list) or len(raw_keys) < 1:
        return jsonify({"error": "Select at least one purchase for this trip report"}), 400

    claimed = _claimed_trip_transaction_keys(user.company_id, user.employee_name)
    owned_keys = {transaction_key(r) for r in scoped_expenses(user.employee_name) if r.get("is_debit")}
    selected: list[str] = []
    seen: set[str] = set()
    for raw in raw_keys:
        key = str(raw).strip()
        if not key or key in seen:
            continue
        if key not in owned_keys:
            return jsonify({"error": f"Purchase not found or not yours: {key}"}), 400
        if key in claimed:
            return jsonify({"error": "One or more purchases are already on another trip report"}), 409
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
            return jsonify({"error": "Please select which approved project this is for"}), 400
        proposal = ProjectProposal.query.filter_by(id=project_id, status="approved").first()
        if not proposal or not _user_can_use_project(user, proposal):
            return jsonify({"error": "That project is not approved or does not belong to you"}), 400

    report = EmployeeTripReport(
        user_id=user.id,
        company_id=user.company_id,
        employee_name=user.employee_name,
        department=resolve_department(user.employee_name),
        trip_name=trip_name[:200],
        purpose=purpose or None,
        transaction_keys=json_module.dumps(selected),
        status="pending_cfo",
        spending_purpose=spending_purpose,
        project_id=project_id,
    )
    db.session.add(report)
    db.session.commit()
    _invalidate_nav_cache()
    return jsonify(
        serialize_submission(report, project_title=_trip_report_project_title(report.project_id))
    ), 201


@app.route("/api/trip-reports/<int:report_id>")
@login_required
def api_trip_report_detail(report_id):
    from trip_report_data import build_report_dict, parse_transaction_keys

    user = get_current_user()
    model = EmployeeTripReport.query.get(report_id)
    if not model:
        return jsonify({"error": "Report not found"}), 404
    if model.user_id != user.id and not can_see_all(user):
        return jsonify({"error": "Forbidden"}), 403
    overrides = _report_status_overrides()
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
        project_title=_trip_report_project_title(model.project_id),
    )
    if not detail:
        return jsonify({"error": "Report not found"}), 404
    return jsonify(detail)


@app.route("/api/brim/chart/<filename>")
@login_required
def api_brim_chart(filename):
    if not brim_bridge:
        return jsonify({"error": "Friday is unavailable"}), 503
    path = brim_bridge.chart_file_path(filename)
    if not path.is_file():
        return jsonify({"error": "Chart not found"}), 404
    return send_file(path, mimetype="image/png")


@app.route("/api/chat/chart/<filename>")
@login_required
def api_chat_chart(filename):
    from chat_charts import chat_chart_path

    path = chat_chart_path(filename)
    if not path.is_file():
        return jsonify({"error": "Chart not found"}), 404
    return send_file(path, mimetype="image/png")


@app.route("/api/brim/reset", methods=["POST"])
@login_required
def api_brim_reset():
    if brim_bridge:
        brim_bridge.reset_chat()
    return jsonify({"status": "ok"})


@app.route("/api/purchases")
@login_required
def api_purchases():
    return jsonify(list_purchases(employee_name=_scope()))


@app.route("/api/map-locations")
@login_required
def api_map_locations():
    limit = request.args.get("limit", 40, type=int)
    limit = max(1, min(limit, 60))
    return jsonify(get_map_locations(api_key=_google_maps_api_key(), limit=limit, employee_name=_scope()))


@app.route("/api/map-merchants")
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
            employee_name=_scope(),
        )
    )


@app.route("/api/compare", methods=["POST"])
@login_required
def api_compare():
    data = request.json or {}
    names = data.get("names") or []
    result = compare_employees(names, employee_name=_scope())
    if not result:
        return jsonify({"error": "no matching employees"}), 404
    return jsonify(result)


@app.route("/api/report/pdf", methods=["POST"])
@login_required
def api_report_pdf():
    data = request.json or {}
    names = data.get("names") or []
    scope = _scope()
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


def _receipt_employee_context(user):
    """Resolve employee id/name for receipt scan (employees use their profile)."""
    from auth import can_see_all, employee_scope

    scope_name = employee_scope(user)
    employee_name = scope_name or user.employee_name
    employee_id = None
    if employee_name:
        from guardian_data import employees_by_name
        meta = employees_by_name().get(employee_name, {})
        employee_id = meta.get("employee_id") or ""
    return employee_id, employee_name, scope_name


def _receipt_mime_type(filename: str, content_type: str | None) -> str:
    if content_type and content_type != "application/octet-stream":
        return content_type.split(";")[0].strip()
    lower = (filename or "").lower()
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".pdf"):
        return "application/pdf"
    if lower.endswith(".md"):
        return "text/markdown"
    if lower.endswith(".txt"):
        return "text/plain"
    return "image/jpeg"


def _run_receipt_scan(file_bytes: bytes, mime_type: str, user):
    from auth import can_see_all, employee_scope
    from receipt_ocr import build_receipt_card, build_scan_reply, process_receipt

    employee_id, employee_name, scope_name = _receipt_employee_context(user)
    if not employee_name and not can_see_all(user):
        return None, "Your account is not linked to an employee profile."

    result = process_receipt(
        file_bytes,
        mime_type,
        employee_id=employee_id if scope_name else None,
        employee_name=scope_name,
    )
    card = build_receipt_card(result)
    card["scan_result"] = result
    return {
        "reply": build_scan_reply(result),
        "receipt": card,
        "scan": result,
    }, None


@app.route("/scan_receipt", methods=["POST"])
@login_required
def scan_receipt():
    from auth import get_current_user

    start = time.perf_counter()
    conv_id = request.form.get("conversation_id")
    user_message = request.form.get("message", "Scan this receipt")
    file = request.files.get("file")
    user = get_current_user()

    uid = _chat_user_id()
    conv = Conversation.query.filter_by(id=conv_id, user_id=uid).first() if conv_id else None
    if not conv or not file:
        return jsonify({"reply": "Pick a chat and attach a receipt."}), 400

    file_bytes = file.read()
    if len(file_bytes) > 10 * 1024 * 1024:
        return jsonify({"reply": "File too large (max 10 MB)."}), 400

    mime_type = _receipt_mime_type(file.filename or "", file.content_type)
    if not (mime_type.startswith("image/") or mime_type == "application/pdf"):
        return jsonify({"reply": "Please attach an image or PDF receipt."}), 400

    payload, err = _run_receipt_scan(file_bytes, mime_type, user)
    if err:
        return jsonify({"reply": err}), 400

    filename = file.filename or "receipt"
    attachment_note = f" [attached: {filename}]"
    db.session.add(
        Message(conversation_id=conv.id, is_user=True, text=user_message + attachment_note)
    )
    db.session.add(Message(conversation_id=conv.id, is_user=False, text=payload["reply"]))
    db.session.commit()

    end = time.perf_counter()
    return jsonify({
        "reply": payload["reply"],
        "receipt": payload["receipt"],
        "scan": payload["scan"],
        "time": f"{end - start:.2f}",
    })


@app.route("/api/receipts/colleagues")
@login_required
def api_receipts_colleagues():
    """Company roster for tagging meal companions on receipts."""
    from guardian_data import employees_by_name

    user = get_current_user()
    roster = []
    for name, info in sorted(employees_by_name().items(), key=lambda item: item[0].lower()):
        if user.employee_name and name == user.employee_name:
            continue
        roster.append({"name": name, "department": str(info.get("department") or "—")})
    return jsonify(roster)


@app.route("/api/receipts/scan", methods=["POST"])
@login_required
def api_receipts_scan():
    from auth import get_current_user

    user = get_current_user()
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "file is required"}), 400

    file_bytes = file.read()
    if len(file_bytes) > 10 * 1024 * 1024:
        return jsonify({"error": "File too large (max 10 MB)"}), 400

    mime_type = _receipt_mime_type(file.filename or "", file.content_type)
    if not (mime_type.startswith("image/") or mime_type == "application/pdf"):
        return jsonify({"error": "File must be an image or PDF"}), 400

    payload, err = _run_receipt_scan(file_bytes, mime_type, user)
    if err:
        return jsonify({"error": err}), 400
    return jsonify(payload["scan"])


@app.route("/api/receipts/confirm", methods=["POST"])
@login_required
def api_receipts_confirm():
    from auth import get_current_user
    from receipt_store import confirm_receipt

    user = get_current_user()
    data = request.get_json(silent=True) or {}
    employee_id, employee_name, _ = _receipt_employee_context(user)
    if not employee_name:
        return jsonify({"error": "Employee profile required to save receipts"}), 400

    amount = float(data.get("amount") or 0)
    payload = {
        "merchant": (data.get("merchant") or data.get("merchant_name") or "").strip(),
        "date": (data.get("date") or data.get("transaction_date") or "").strip(),
        "amount": amount,
        "category": (data.get("category") or data.get("expense_category") or "").strip(),
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

    from receipt_ocr import is_dining_receipt

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
            return jsonify({"error": "Enter how many people were at the meal (including you)"}), 400
        if party_size < 1:
            return jsonify({"error": "Party size must be at least 1"}), 400
        from receipt_store import apply_dining_context

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
            return jsonify({"error": "Please select which approved project this is for"}), 400
        proposal = ProjectProposal.query.filter_by(id=project_id, status="approved").first()
        if not proposal or not _user_can_use_project(user, proposal):
            return jsonify({"error": "That project is not approved or does not belong to you"}), 400
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


@app.route("/api/receipts", methods=["GET"])
@login_required
def api_receipts_list():
    from auth import can_see_all, get_current_user, employee_scope
    from receipt_store import list_receipts

    user = get_current_user()
    scope = employee_scope(user)
    if can_see_all(user):
        records = list_receipts()
    else:
        records = list_receipts(employee_name=user.employee_name)
    return jsonify(records)


@app.route('/get_conversations')
@login_required
def get_conversations():
    uid = _chat_user_id()
    convs = Conversation.query.filter_by(user_id=uid).order_by(Conversation.created_at.desc()).all()
    return jsonify([{'id': c.id, 'title': c.title, 'date': c.created_at.strftime('%Y-%m-%d')} for c in convs])

@app.route('/newchat', methods=["POST"])
@login_required
def newchat():
    uid = _chat_user_id()
    if brim_bridge:
        brim_bridge.reset_chat()
    new_chat = Conversation(user_id=uid, title=f"{datetime.now().strftime('%H:%M:%S')}")
    db.session.add(new_chat)
    db.session.commit()
    db.session.add(
        Message(conversation_id=new_chat.id, is_user=False, text=WELCOME_MESSAGE)
    )
    db.session.commit()
    session["conv_id"] = new_chat.id
    return jsonify({'id': new_chat.id})


@app.route("/conversation/<int:cid>/messages")
@login_required
def conversation_messages(cid):
    uid = _chat_user_id()
    conv = Conversation.query.filter_by(id=cid, user_id=uid).first()
    if not conv:
        return jsonify([])
    rows = (
        Message.query.filter_by(conversation_id=cid).order_by(Message.id.asc()).all()
    )
    out = []
    for m in rows:
        out.append(
            {
                "role": "user" if m.is_user else "assistant",
                "text": m.text,
                "lewis_structure": m.lewis_structure,
                "vsepr": m.vsepr,
            }
        )
    return jsonify(out)


@app.route("/api/fraud/flagged")
@login_required
@admin_required
def api_fraud_flagged():
    from fraud_data import flagged_records

    return jsonify(flagged_records())


@app.route("/api/fraud/stats")
@login_required
@admin_required
def api_fraud_stats():
    from fraud_data import fraud_stats

    return jsonify(fraud_stats())


@app.route("/api/fraud/review", methods=["POST"])
@login_required
@admin_required
def api_fraud_review():
    from fraud_data import review_transaction

    data = request.get_json(silent=True) or {}
    txn_id = data.get("transaction_id")
    action = data.get("action")
    if not txn_id or action not in ("approved", "dismissed", "escalated"):
        return jsonify({"error": "Invalid review payload"}), 400
    result = review_transaction(txn_id, action)
    if result.get("error"):
        return jsonify(result), 404
    _persist_fraud_decision(txn_id, action, data.get("note"))
    _invalidate_nav_cache()
    return jsonify(result)


@app.route("/api/fraud/undo", methods=["POST"])
@login_required
@admin_required
def api_fraud_undo():
    from fraud_data import undo_review

    result = undo_review()
    if result.get("error"):
        return jsonify(result), 400
    _invalidate_nav_cache()
    return jsonify(result)


@app.route("/api/fraud/threshold", methods=["POST"])
@login_required
@admin_required
def api_fraud_threshold():
    from fraud_data import set_threshold

    data = request.get_json(silent=True) or {}
    try:
        value = float(data.get("threshold", 0.4))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid threshold"}), 400
    _invalidate_nav_cache()
    return jsonify({"threshold": set_threshold(value)})


@app.route("/api/fraud/export")
@login_required
@admin_required
def api_fraud_export():
    from fraud_data import export_reviewed_csv

    buf, filename = export_reviewed_csv()
    return send_file(buf, mimetype="text/csv", as_attachment=True, download_name=filename)


def _ensure_schema():
    from sqlalchemy import inspect, text

    db.create_all()
    insp = inspect(db.engine)
    if insp.has_table("project_proposal"):
        cols = {c["name"] for c in insp.get_columns("project_proposal")}
        if "budget_source" not in cols:
            db.session.execute(
                text(
                    "ALTER TABLE project_proposal "
                    "ADD COLUMN budget_source VARCHAR(32) NOT NULL DEFAULT 'existing'"
                )
            )
            db.session.commit()
        if "colleagues" not in cols:
            db.session.execute(
                text("ALTER TABLE project_proposal ADD COLUMN colleagues TEXT")
            )
            db.session.commit()
    if insp.has_table("employee_trip_report"):
        trip_cols = {c["name"] for c in insp.get_columns("employee_trip_report")}
        if "spending_purpose" not in trip_cols:
            db.session.execute(
                text(
                    "ALTER TABLE employee_trip_report "
                    "ADD COLUMN spending_purpose VARCHAR(20) NOT NULL DEFAULT 'personal'"
                )
            )
            db.session.commit()
        if "project_id" not in trip_cols:
            db.session.execute(
                text("ALTER TABLE employee_trip_report ADD COLUMN project_id INTEGER")
            )
            db.session.commit()


with app.app_context():
    _ensure_schema()
    expense_data.reload_expense_cache()


if __name__ == "__main__":
    app.run(debug=True)