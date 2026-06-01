"""Chat routes for conversation CRUD and Gemini / Friday agent integration."""

from __future__ import annotations

import logging
import time

from datetime import datetime

from flask import Blueprint, jsonify, request, session
from google import genai

from config import Config
from core.extensions import db
from models import Conversation, Message
from core.auth import get_current_user, can_see_all, login_required
from core.paths import ROOT as _APP_ROOT
from routes.helpers import (
    chat_user_id,
    employee_scope_name,
    invalidate_nav_cache,
    decided_keys,
    fraud_status_overrides,
    pending_proposal_items,
)
import services.expenses as expense_data

WELCOME_MESSAGE = (
    "Hi! I'm Friday, your AI assistant for CashFlux. "
    "Ask about spending, or tell me to approve requests, change budgets, update rules, submit a project, or open any page."
)

# Gemini client  created once at import time
_client = genai.Client(api_key=Config.GEMINI_API_KEY) if Config.GEMINI_API_KEY else None

chat_bp = Blueprint("chat", __name__)


@chat_bp.route("/chat", methods=["POST"])
@login_required
def chat():
    from ai.voice import (
        _strip_for_speech,
        detect_voice_actions,
        try_instant_response,
        VOICE_VERBOSITY,
    )
    from ai.context import build_voice_context_block

    fallback_error_messages = [
        "Gemini is temporarily unavailable. Your spending data is safe locally. Try again in a moment.",
        "The Vultr backend is reconnecting. Chat queries will resume shortly.",
        "Spend Analyst is warming up. Please retry your query.",
    ]

    start = time.perf_counter()

    request_data = request.json
    user_message = request_data.get("message")
    conv_id = request_data.get("conversation_id")
    voice_mode = bool(request_data.get("voice"))
    current_view = (request_data.get("current_view") or "overview").strip()
    verbosity = request_data.get("verbosity", "less" if voice_mode else "medium")

    uid = chat_user_id()
    conv = (
        Conversation.query.filter_by(id=conv_id, user_id=uid).first()
        if conv_id
        else None
    )
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
        db.session.add(
            Message(conversation_id=conv.id, is_user=True, text=user_message)
        )
        db.session.add(Message(conversation_id=conv.id, is_user=False, text=reply))
        db.session.commit()
        end = time.perf_counter()
        actions = extra.pop("actions", None)
        if actions is None:
            actions = detect_voice_actions(user_message, current_view)
        payload = {
            "reply": reply,
            "time": f"{end: start:.2f}",
            "actions": actions,
            **extra,
        }
        return jsonify(payload)

    instant = try_instant_response(
        user_message,
        current_view,
        employee_name=employee_scope_name(),
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

    past_messages = (
        Message.query.filter_by(conversation_id=conv_id)
        .order_by(Message.id.asc())
        .all()
    )

    def _visual_payload():
        """Attach Chart.js insight only when a visualization is warranted."""
        from services.spending import wants_visualization
        from services.expenses import get_charts_for_query

        if voice_mode and not wants_visualization(user_message or "", past_messages):
            return {}

        insight = get_charts_for_query(
            user_message,
            conversation_history=past_messages,
            employee_name=employee_scope_name(),
        )
        if not insight:
            return {}
        return {"insight": {k: v for k, v in insight.items() if not k.startswith("_")}}

    history = []
    for msg in past_messages:
        role = "user" if msg.is_user else "model"
        history.append({"role": role, "parts": [{"text": msg.text}]})

    history.append({"role": "user", "parts": [{"text": user_message}]})

    try:
        from services.spending import get_query_figures_block
        from services.expenses import build_gemini_context, get_charts_for_query

        with open(_APP_ROOT / "ai" / "prompt.txt", "r", encoding="utf-8") as f:
            system_prompt = f.read()

        expense_context = build_gemini_context(
            user_message,
            conversation_history=past_messages,
            employee_name=employee_scope_name(),
        )

        insight = get_charts_for_query(
            user_message,
            conversation_history=past_messages,
            employee_name=employee_scope_name(),
        )
        if insight and insight.get("_context_block"):
            expense_context += (
                "\n\nCHART DATA (use these exact figures, a live chart renders below):\n"
                + insight["_context_block"]
            )
        elif insight and insight.get("summary"):
            expense_context += (
                "\n\nCHART DATA (use these exact figures, a live chart renders below):\n"
                + insight["summary"].replace("**", "")
            )
        else:
            figures = get_query_figures_block(
                user_message,
                conversation_history=past_messages,
                employee_name=employee_scope_name(),
            )
            if figures:
                expense_context += (
                    "\n\nQUERY ANSWER DATA (use these exact figures, no chart for this question):\n"
                    + figures
                )
        scope = employee_scope_name()
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
        if _client is None:
            visual = _visual_payload()
            insight = visual.get("insight") or {}
            reply = insight.get(
                "summary", "Chart generated from your expense data."
            ).replace("**", "")
            return _persist_and_reply(reply, engine="chart-only", **visual)

        from ai.agent import run_friday_chat
        from ai.tools import FridayContext

        friday_ctx = FridayContext(
            user=get_current_user(),
            is_admin=can_see_all(get_current_user()),
            employee_name=employee_scope_name(),
            current_view=current_view,
            invalidate_cache=invalidate_nav_cache,
            pending_proposals_fn=pending_proposal_items,
            decided_keys_fn=decided_keys,
            fraud_overrides_fn=fraud_status_overrides,
        )
        agent_result = run_friday_chat(
            _client,
            history=history,
            system_prompt=system_prompt_with_verbosity,
            ctx=friday_ctx,
        )
        reply = agent_result.get("reply") or ""
        if voice_mode:
            reply = _strip_for_speech(reply)
        actions = agent_result.get("actions") or detect_voice_actions(
            user_message, current_view
        )
        return _persist_and_reply(
            reply,
            tool_calls=agent_result.get("tool_calls") or [],
            actions=actions,
            engine=agent_result.get("engine", "friday-agent"),
            **_visual_payload(),
        )

    except Exception:
        logging.exception("Chat error")
        if "error_rotation_index" not in session:
            session["error_rotation_index"] = 0

        current_index = session["error_rotation_index"]
        # Clamp index to valid range before accessing the list.
        current_index = min(current_index, len(fallback_error_messages) - 1)
        current_msg = fallback_error_messages[current_index]
        session["error_rotation_index"] = min(
            current_index + 1, len(fallback_error_messages) - 1
        )
        try:
            visual = _visual_payload()
        except Exception:
            visual = {}
        if visual.get("chart_urls"):
            insight = visual.get("insight") or {}
            reply = insight.get("summary", "Here is the chart you asked for.").replace(
                "**", ""
            )
            return _persist_and_reply(reply, engine="chart-fallback", **visual)

        end = time.perf_counter()
        return jsonify({"reply": current_msg, "time": f"{end: start:.2f}"}), 500


@chat_bp.route("/get_conversations")
@login_required
def api_conversations():
    uid = chat_user_id()
    convs = (
        Conversation.query.filter_by(user_id=uid)
        .order_by(Conversation.created_at.desc())
        .all()
    )
    return jsonify(
        [
            {"id": c.id, "title": c.title, "date": c.created_at.strftime("%Y-%m-%d")}
            for c in convs
        ]
    )


@chat_bp.route("/newchat", methods=["POST"])
@login_required
def api_new_conversation():
    uid = chat_user_id()
    new_chat = Conversation(user_id=uid, title=f"{datetime.now().strftime('%H:%M:%S')}")
    db.session.add(new_chat)
    db.session.commit()
    db.session.add(
        Message(conversation_id=new_chat.id, is_user=False, text=WELCOME_MESSAGE)
    )
    db.session.commit()
    session["conv_id"] = new_chat.id
    return jsonify({"id": new_chat.id})


@chat_bp.route("/conversation/<int:cid>/messages")
@login_required
def conversation_messages(cid):
    uid = chat_user_id()
    conv = Conversation.query.filter_by(id=cid, user_id=uid).first()
    if not conv:
        return jsonify([])
    rows = Message.query.filter_by(conversation_id=cid).order_by(Message.id.asc()).all()
    out = []
    for m in rows:
        out.append(
            {
                "role": "user" if m.is_user else "assistant",
                "text": m.text,
            }
        )
    return jsonify(out)

