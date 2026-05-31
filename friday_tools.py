"""Friday assistant tools — navigate, modify budgets, policy, review queue, proposals."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from assistant_context import SITE_PAGES, build_voice_context_block, get_site_snapshot


@dataclass
class FridayContext:
    user: Any
    is_admin: bool
    employee_name: str | None
    current_view: str = "overview"
    invalidate_cache: Callable[[], None] | None = None
    pending_proposals_fn: Callable[[], list] | None = None
    decided_keys_fn: Callable[[str], set] | None = None
    fraud_overrides_fn: Callable[[], dict] | None = None
    actions: list[dict] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)


def _err(message: str) -> dict:
    return {"ok": False, "error": message}


def _ok(**payload) -> dict:
    return {"ok": True, **payload}


def _require_admin(ctx: FridayContext) -> dict | None:
    if ctx.is_admin:
        return None
    return _err("Only admins can do that. Ask your finance lead or open Settings.")


def _invalidate(ctx: FridayContext) -> None:
    if ctx.invalidate_cache:
        ctx.invalidate_cache()
    try:
        from assistant_context import clear_site_snapshot_cache
        from guardian_data import clear_cache

        clear_site_snapshot_cache()
        clear_cache()
    except ImportError:
        pass


def _nav_action(view: str, **extra) -> dict:
    action = {"type": "navigate", "view": view, **extra}
    return action


ACTION_MESSAGE_HINTS = re.compile(
    r"\b("
    r"approve|deny|reject|submit|set|change|update|create|open|go to|navigate|"
    r"escalate|dismiss|raise|lower|increase|decrease|enable|disable|add|remove|"
    r"make|move|adjust|save|delete|assign|flag|unflag"
    r")\b",
    re.I,
)


def message_wants_actions(message: str) -> bool:
    return bool(ACTION_MESSAGE_HINTS.search(message or ""))


def tool_declarations() -> list[dict]:
    """JSON-schema function declarations for Gemini."""
    views = list(SITE_PAGES.keys())
    return [
        {
            "name": "navigate",
            "description": "Open a page in CashFlux for the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "view": {"type": "string", "enum": views, "description": "Page to open"},
                    "tab": {
                        "type": "string",
                        "enum": ["budgets", "rules"],
                        "description": "Settings sub-tab when view is settings",
                    },
                    "review_filter": {
                        "type": "string",
                        "enum": ["all", "approval", "flag", "fraud", "proposal", "report"],
                        "description": "Filter Review queue when view is approvals",
                    },
                },
                "required": ["view"],
            },
        },
        {
            "name": "get_site_overview",
            "description": "Live counts, budget caps, pending approvals, and flags.",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "get_department_budget",
            "description": "Look up a department's quarterly budget cap and spend.",
            "parameters": {
                "type": "object",
                "properties": {
                    "department": {"type": "string", "description": "Department name"},
                },
                "required": ["department"],
            },
        },
        {
            "name": "set_department_budget",
            "description": "Set a department's budget cap for the current quarter (admin).",
            "parameters": {
                "type": "object",
                "properties": {
                    "department": {"type": "string"},
                    "amount": {"type": "number", "description": "New cap in CAD"},
                },
                "required": ["department", "amount"],
            },
        },
        {
            "name": "list_spending_rules",
            "description": "List current spending policy rule keys and values (admin).",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "update_spending_rule",
            "description": "Change one spending policy rule (admin). Use list_spending_rules for valid keys.",
            "parameters": {
                "type": "object",
                "properties": {
                    "rule_key": {"type": "string", "description": "Rule key e.g. solo_meal_limit"},
                    "value": {
                        "description": "New value — number, boolean, or comma-separated keywords for list rules",
                    },
                },
                "required": ["rule_key", "value"],
            },
        },
        {
            "name": "list_pending_reviews",
            "description": "List items waiting in Review — approvals, flags, fraud, project proposals (admin).",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["all", "approval", "flag", "fraud", "proposal", "report"],
                    },
                    "limit": {"type": "integer", "description": "Max items (default 15)"},
                },
            },
        },
        {
            "name": "review_item",
            "description": "Approve, deny, dismiss, or escalate a Review queue item by id (admin).",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {
                        "type": "string",
                        "description": "Exact id from list_pending_reviews e.g. proposal:3, flag:abc",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["approve", "deny", "dismiss", "escalate"],
                    },
                    "note": {"type": "string"},
                },
                "required": ["item_id", "action"],
            },
        },
        {
            "name": "list_trip_reports",
            "description": "List trip expense reports and their status (admin).",
            "parameters": {
                "type": "object",
                "properties": {
                    "pending_only": {"type": "boolean"},
                },
            },
        },
        {
            "name": "decide_trip_report",
            "description": "Approve or reject a trip report by report_key (admin).",
            "parameters": {
                "type": "object",
                "properties": {
                    "report_key": {"type": "string"},
                    "approved": {"type": "boolean"},
                    "note": {"type": "string"},
                },
                "required": ["report_key", "approved"],
            },
        },
        {
            "name": "analyze_vendor_consolidation",
            "description": "Find duplicate vendor categories (coffee, cloud, fuel, etc.) and estimate savings from consolidating.",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "submit_project_proposal",
            "description": "Submit a new project budget proposal for approval (employees only).",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "requested_amount": {"type": "number", "description": "Budget in CAD"},
                    "budget_source": {
                        "type": "string",
                        "enum": ["existing", "extra"],
                        "description": "existing = from dept budget; extra = requests additional funds",
                    },
                    "colleagues": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional teammate names on the project",
                    },
                },
                "required": ["title", "description", "requested_amount", "budget_source"],
            },
        },
    ]


def _report_status_overrides() -> dict[str, str]:
    from app import WorkflowDecision

    return {
        r.item_key: r.status
        for r in WorkflowDecision.query.filter_by(item_type="report").all()
    }


def _find_review_item(ctx: FridayContext, item_id: str) -> dict | None:
    from review_data import build_review_queue

    queue = build_review_queue(
        approval_exclude=ctx.decided_keys_fn("approval") if ctx.decided_keys_fn else set(),
        fraud_status_overrides=ctx.fraud_overrides_fn() if ctx.fraud_overrides_fn else {},
        proposal_items=ctx.pending_proposals_fn() if ctx.pending_proposals_fn else [],
        flag_exclude=ctx.decided_keys_fn("flag") if ctx.decided_keys_fn else set(),
        report_status_overrides=_report_status_overrides(),
    )
    item_id = str(item_id or "").strip()
    for item in queue:
        if item.get("id") == item_id:
            return item
    return None


def _perform_review_action(ctx: FridayContext, item_id: str, action: str, note: str | None = None) -> dict:
    from datetime import datetime

    from app import ProjectProposal, WorkflowDecision, db, get_current_user

    action = (action or "").lower()
    item_id = str(item_id or "").strip()
    if not item_id:
        return _err("item_id is required")

    if item_id.startswith("approval:"):
        if action not in ("approve", "deny"):
            return _err("Use approve or deny for expense approvals")
        item_key = item_id.split(":", 1)[1]
        existing = WorkflowDecision.query.filter_by(item_key=item_key, item_type="approval").first()
        if existing:
            return _err(f"Already decided: {existing.status}")
        status = "approved" if action == "approve" else "denied"
        db.session.add(
            WorkflowDecision(item_key=item_key, item_type="approval", status=status, note=note)
        )
        db.session.commit()
        _invalidate(ctx)
        ctx.actions.append({"type": "review_updated", "view": "approvals"})
        return _ok(status=status, item_id=item_id)

    if item_id.startswith("flag:"):
        if action not in ("approve", "deny"):
            return _err("Use approve or deny for flagged purchases")
        item_key = item_id.split(":", 1)[1]
        existing = WorkflowDecision.query.filter_by(item_key=item_key, item_type="flag").first()
        if existing:
            return _err(f"Already decided: {existing.status}")
        status = "approved" if action == "approve" else "denied"
        db.session.add(
            WorkflowDecision(item_key=item_key, item_type="flag", status=status, note=note)
        )
        db.session.commit()
        import expense_data

        expense_data.reload_expense_cache()
        _invalidate(ctx)
        ctx.actions.append({"type": "review_updated", "view": "approvals"})
        return _ok(status=status, item_id=item_id)

    if item_id.startswith("fraud:"):
        from fraud_data import review_transaction

        txn_id = item_id.split(":", 1)[1]
        fraud_action = {
            "approve": "approved",
            "dismiss": "dismissed",
            "deny": "dismissed",
            "escalate": "escalated",
        }.get(action)
        if not fraud_action:
            return _err("Use approve, deny/dismiss, or escalate for fraud items")
        result = review_transaction(txn_id, fraud_action)
        if result.get("error"):
            return _err(result["error"])
        existing = WorkflowDecision.query.filter_by(item_key=txn_id, item_type="fraud").first()
        if existing:
            existing.status = fraud_action
            if note is not None:
                existing.note = note
        else:
            db.session.add(
                WorkflowDecision(
                    item_key=txn_id,
                    item_type="fraud",
                    status=fraud_action,
                    note=note,
                )
            )
        db.session.commit()
        _invalidate(ctx)
        ctx.actions.append({"type": "review_updated", "view": "approvals", "reviewFilter": "fraud"})
        return _ok(status=fraud_action, item_id=item_id)

    if item_id.startswith("proposal:"):
        if action not in ("approve", "deny"):
            return _err("Use approve or deny for project proposals")
        try:
            proposal_id = int(item_id.split(":", 1)[1])
        except (TypeError, ValueError):
            return _err("Invalid proposal id")
        proposal = ProjectProposal.query.get(proposal_id)
        if not proposal:
            return _err("Proposal not found")
        if proposal.status != "pending":
            return _err(f"Already decided: {proposal.status}")
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
        proposal.decision_note = (note or "").strip() or None
        db.session.commit()
        _invalidate(ctx)
        ctx.actions.append({"type": "review_updated", "view": "approvals"})
        if budget_update:
            ctx.actions.append(
                {
                    "type": "budget_updated",
                    "view": "budget",
                    "department": budget_update.get("department"),
                    "quarter": budget_update.get("quarter"),
                }
            )
        return _ok(status=proposal.status, item_id=item_id, budget_update=budget_update)

    if item_id.startswith("report:"):
        if action not in ("approve", "deny"):
            return _err("Use approve or deny for trip expense reports")
        report_key = item_id.split(":", 1)[1]
        from app import WorkflowDecision, db

        existing = WorkflowDecision.query.filter_by(item_key=report_key, item_type="report").first()
        if existing:
            return _err(f"Already decided: {existing.status}")
        status = "approved" if action == "approve" else "rejected"
        db.session.add(
            WorkflowDecision(
                item_key=report_key,
                item_type="report",
                status=status,
                note=note,
            )
        )
        db.session.commit()
        _invalidate(ctx)
        ctx.actions.append({"type": "review_updated", "view": "approvals", "reviewFilter": "report"})
        return _ok(status=status, item_id=item_id)

    return _err("Unknown review item id")


def dispatch_tool(ctx: FridayContext, name: str, args: dict | None) -> dict:
    args = dict(args or {})
    ctx.tool_calls.append(name)

    if name == "navigate":
        view = str(args.get("view") or "").strip()
        if view not in SITE_PAGES:
            return _err(f"Unknown page. Use one of: {', '.join(SITE_PAGES)}")
        if ctx.is_admin and view in ("receipts", "proposals"):
            return _err("Receipts and My projects are for employees only — admins use Review and All purchases.")
        extra = {}
        if args.get("tab"):
            extra["tab"] = args["tab"]
        if args.get("review_filter"):
            extra["reviewFilter"] = args["review_filter"]
        ctx.actions.append(_nav_action(view, **extra))
        return _ok(view=view, label=SITE_PAGES[view])

    if name == "get_site_overview":
        snap = get_site_snapshot(ctx.current_view)
        return _ok(
            current_view=snap["current_view_label"],
            counts=snap["counts"],
            totals=snap["totals"],
            top_departments=snap["top_departments"],
            budget_caps=snap.get("budget_caps") or [],
            pending_approvals=snap.get("pending_approvals") or [],
            recent_flags=snap.get("recent_flags") or [],
        )

    if name == "get_department_budget":
        from budget_data import lookup_department_budget, resolve_department_name

        dept = resolve_department_name(str(args.get("department") or ""))
        if not dept:
            return _err("Could not match that department name")
        info = lookup_department_budget(dept)
        if not info:
            return _err("No budget data for that department")
        return _ok(**info)

    if name == "set_department_budget":
        denied = _require_admin(ctx)
        if denied:
            return denied
        from budget_data import set_department_budget

        try:
            result = set_department_budget(
                str(args.get("department") or ""),
                float(args.get("amount") or 0),
            )
        except (TypeError, ValueError) as exc:
            return _err(str(exc))
        _invalidate(ctx)
        ctx.actions.append(
            {
                "type": "budget_updated",
                "view": "budget",
                "department": result["department"],
                "quarter": result["quarter"],
                "new_cap": result["new_cap"],
                "new_cap_fmt": result["new_cap_fmt"],
            }
        )
        return _ok(**result)

    if name == "list_spending_rules":
        denied = _require_admin(ctx)
        if denied:
            return denied
        from policy_engine import load_policy_rules, policy_summary_text

        rules = load_policy_rules()
        summary = []
        for key, val in rules.items():
            if key in ("department_overrides", "role_overrides"):
                continue
            if isinstance(val, list):
                preview = ", ".join(str(v) for v in val[:5])
                if len(val) > 5:
                    preview += "…"
                summary.append({"key": key, "value": preview, "type": "list"})
            else:
                summary.append({"key": key, "value": val, "type": type(val).__name__})
        return _ok(rules_summary=summary, text_summary=policy_summary_text())

    if name == "update_spending_rule":
        denied = _require_admin(ctx)
        if denied:
            return denied
        from policy_engine import POLICY_SCHEMA, load_policy_rules, save_policy_rules

        rule_key = str(args.get("rule_key") or "").strip()
        if not rule_key:
            return _err("rule_key is required")
        valid_keys = {s["key"] for s in POLICY_SCHEMA}
        if rule_key not in valid_keys:
            return _err(f"Unknown rule. Valid keys include: {', '.join(sorted(valid_keys)[:12])}…")

        schema = next(s for s in POLICY_SCHEMA if s["key"] == rule_key)
        raw = args.get("value")
        rules = load_policy_rules()

        try:
            if schema["type"] == "number":
                new_val = float(raw)
            elif schema["type"] == "boolean":
                if isinstance(raw, bool):
                    new_val = raw
                else:
                    new_val = str(raw).strip().lower() in ("true", "1", "yes", "on")
            elif schema["type"] in ("keywords", "numbers"):
                if isinstance(raw, list):
                    items = [str(x).strip() for x in raw if str(x).strip()]
                else:
                    items = [p.strip() for p in re.split(r",|\n", str(raw)) if p.strip()]
                new_val = [int(x) for x in items] if schema["type"] == "numbers" else items
            else:
                new_val = raw
        except (TypeError, ValueError):
            return _err(f"Invalid value for {rule_key}")

        old_val = rules.get(rule_key)
        rules[rule_key] = new_val
        save_policy_rules(rules)
        _invalidate(ctx)
        ctx.actions.append({"type": "policy_updated", "view": "settings", "tab": "rules"})
        return _ok(rule_key=rule_key, previous=old_val, new=new_val)

    if name == "list_pending_reviews":
        denied = _require_admin(ctx)
        if denied:
            return denied
        from review_data import build_review_queue

        kind = (args.get("kind") or "all").lower()
        limit = min(int(args.get("limit") or 15), 30)
        queue = build_review_queue(
            approval_exclude=ctx.decided_keys_fn("approval") if ctx.decided_keys_fn else set(),
            fraud_status_overrides=ctx.fraud_overrides_fn() if ctx.fraud_overrides_fn else {},
            proposal_items=ctx.pending_proposals_fn() if ctx.pending_proposals_fn else [],
            flag_exclude=ctx.decided_keys_fn("flag") if ctx.decided_keys_fn else set(),
            report_status_overrides=_report_status_overrides(),
        )
        if kind != "all":
            queue = [i for i in queue if i.get("kind") == kind]
        items = [
            {
                "id": i["id"],
                "kind": i.get("kind"),
                "title": i.get("title"),
                "employee": i.get("employee"),
                "department": i.get("department"),
                "amount": i.get("amount"),
                "risk": i.get("risk_label"),
                "brief": (i.get("brief") or "")[:200],
            }
            for i in queue[:limit]
        ]
        return _ok(items=items, total=len(queue))

    if name == "review_item":
        denied = _require_admin(ctx)
        if denied:
            return denied
        item_id = str(args.get("item_id") or "").strip()
        if not _find_review_item(ctx, item_id):
            return _err("Item not found or already decided — call list_pending_reviews first")
        return _perform_review_action(
            ctx,
            item_id,
            str(args.get("action") or ""),
            (args.get("note") or "").strip() or None,
        )

    if name == "list_trip_reports":
        denied = _require_admin(ctx)
        if denied:
            return denied
        from app import WorkflowDecision
        from guardian_data import get_reports_list

        overrides = {
            r.item_key: r.status
            for r in WorkflowDecision.query.filter_by(item_type="report").all()
        }
        reports = get_reports_list(status_overrides=overrides)
        if args.get("pending_only"):
            reports = [r for r in reports if r.get("status") == "pending_cfo"]
        items = [
            {
                "report_key": r.get("key") or r.get("report_key"),
                "employee": r.get("employee"),
                "status": r.get("status"),
                "total": r.get("total"),
                "date_range": r.get("date_range"),
            }
            for r in reports[:20]
        ]
        return _ok(reports=items)

    if name == "decide_trip_report":
        denied = _require_admin(ctx)
        if denied:
            return denied
        from app import WorkflowDecision, db

        report_key = str(args.get("report_key") or "").strip()
        if not report_key:
            return _err("report_key is required")
        approved = bool(args.get("approved"))
        existing = WorkflowDecision.query.filter_by(item_key=report_key, item_type="report").first()
        if existing:
            return _err(f"Already decided: {existing.status}")
        status = "approved" if approved else "rejected"
        db.session.add(
            WorkflowDecision(
                item_key=report_key,
                item_type="report",
                status=status,
                note=(args.get("note") or "").strip() or None,
            )
        )
        db.session.commit()
        _invalidate(ctx)
        ctx.actions.append({"type": "report_decided", "view": "reports"})
        return _ok(status=status, report_key=report_key)

    if name == "submit_project_proposal":
        if ctx.is_admin:
            return _err("Admins cannot submit proposals — employees use My projects")
        if not ctx.user or not ctx.user.employee_name:
            return _err("Your account is not linked to an employee profile")
        from datetime import datetime

        from app import ProjectProposal, db
        from proposal_data import build_budget_snapshot, employee_department, normalize_colleagues
        from guardian_data import employees_by_name

        title = str(args.get("title") or "").strip()
        description = str(args.get("description") or "").strip()
        budget_source = str(args.get("budget_source") or "").strip().lower()
        try:
            amount = round(float(args.get("requested_amount") or 0), 2)
        except (TypeError, ValueError):
            return _err("Invalid budget amount")

        if len(title) < 3:
            return _err("Title must be at least 3 characters")
        if len(description) < 10:
            return _err("Description must be at least 10 characters")
        if amount <= 0:
            return _err("Amount must be greater than zero")
        if budget_source not in ("existing", "extra"):
            return _err("budget_source must be existing or extra")

        dept = employee_department(ctx.user.employee_name)
        snapshot = build_budget_snapshot(dept)
        colleagues = normalize_colleagues(
            args.get("colleagues"),
            roster=set(employees_by_name().keys()),
            exclude=ctx.user.employee_name,
        )
        proposal = ProjectProposal(
            user_id=ctx.user.id,
            company_id=ctx.user.company_id,
            employee_name=ctx.user.employee_name,
            department=dept,
            title=title,
            description=description,
            requested_amount=amount,
            quarter=snapshot.get("quarter"),
            status="pending",
            budget_snapshot=json.dumps(snapshot),
            budget_source=budget_source,
            colleagues=json.dumps(colleagues) if colleagues else None,
        )
        db.session.add(proposal)
        db.session.commit()
        _invalidate(ctx)
        ctx.actions.append({"type": "proposal_submitted", "view": "proposals"})
        return _ok(
            proposal_id=proposal.id,
            title=title,
            requested_amount=amount,
            status="pending",
            department=dept,
        )

    if name == "analyze_vendor_consolidation":
        from vendor_consolidation import analyze_vendor_consolidation

        data = analyze_vendor_consolidation(employee_name=ctx.employee_name)
        ctx.actions.append({"type": "navigate", "view": "budget"})
        return _ok(**data)

    return _err(f"Unknown tool: {name}")
