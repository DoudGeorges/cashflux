"""Voice assistant: instant responses, navigation detection, and speech text processing."""

from __future__ import annotations

import re

from ai.context import get_site_snapshot

VOICE_VERBOSITY = (
    "VOICE MODE: You are Friday, the CashFlux AI assistant (like Siri or Alexa). "
    "Reply in plain conversational English in 1 to 3 short sentences. "
    "No markdown, no bullet lists, no asterisks. Say numbers naturally."
)

NAV_TRIGGERS = (
    "open",
    "go to",
    "show me",
    "take me to",
    "take me",
    "navigate to",
    "switch to",
    "bring me to",
    "pull up",
    "jump to",
    "head to",
)

VIEW_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("overview", (r"\bhome\b", r"\bdashboard\b", r"\boverview\b", r"\bmain page\b")),
    ("people", (r"\bpeople\b", r"\bemployees?\b", r"\broster\b", r"\bstaff\b")),
    (
        "receipts",
        (
            r"\breceipts?\b",
            r"\breceipt scan\b",
            r"\bscan receipt\b",
            r"\bupload receipt\b",
        ),
    ),
    (
        "proposals",
        (
            r"\bmy projects\b",
            r"\bproposals?\b",
            r"\bproject proposals?\b",
            r"\bbudget request\b",
        ),
    ),
    (
        "activity",
        (
            r"\bpurchases?\b",
            r"\btransactions?\b",
            r"\ball purchases\b",
            r"\bactivity\b",
            r"\bmy purchases\b",
        ),
    ),
    (
        "budget",
        (r"\bbudgets?\b", r"\bburn rate\b", r"\bforecast\b", r"\bdepartment cap\b"),
    ),
    ("map", (r"\bmap\b", r"\blocations?\b", r"\bwhere purchases\b")),
    (
        "alerts",
        (
            r"\bproblems?\b",
            r"\bflags?\b",
            r"\bflagged\b",
            r"\bviolations?\b",
            r"\boffenders?\b",
        ),
    ),
    (
        "approvals",
        (
            r"\breview\b",
            r"\bapprove\b",
            r"\bapprovals?\b",
            r"\bpending requests?\b",
            r"\bwaiting for\b",
            r"\bfraud\b",
            r"\bfraud detection\b",
            r"\bsuspicious purchases?\b",
            r"\bscam\b",
            r"\bfraud hunter\b",
        ),
    ),
    (
        "reports",
        (
            r"\btrip reports?\b",
            r"\breports page\b",
            r"\bcfo reports?\b",
            r"\bexpense reports?\b",
        ),
    ),
    ("chat", (r"\bchat\b", r"\bask anything\b", r"\btext chat\b", r"\bfriday\b")),
    (
        "settings",
        (r"\bsettings\b", r"\bspending rules\b", r"\bconfigure\b", r"\bsetup\b"),
    ),
]

PAGE_LABELS = {
    "overview": "Home",
    "people": "People",
    "receipts": "Receipts",
    "proposals": "My projects",
    "activity": "All purchases",
    "budget": "Budgets",
    "map": "Map",
    "alerts": "Problems",
    "approvals": "Review",
    "reports": "Trip reports",
    "chat": "Ask anything",
    "settings": "Settings",
}

_DATA_HINTS = re.compile(
    r"\b(how much|how many|who|what did|tell me|explain|compare|spend|total|count|why|when|which|list)\b"
)

_COMPANY_RANKING = re.compile(
    r"\b("
    r"who spent the most|who spends the most|biggest spender|highest spender|"
    r"who spent the least|who spends the least|lowest spender|smallest spender|"
    r"top department|top employee|other employees?|all employees?|company.?wide|"
    r"across the company|everyone|compare .+ employees?"
    r")\b",
    re.I,
)

_PERSONAL_LEAST = re.compile(
    r"\b(least|lowest|minimum|smallest)\b.*\b(spend|spender|money|amount|purchase)\b|"
    r"\bwho spends the least\b|\blowest spender\b|\bspend the least\b",
    re.I,
)

_PERSONAL_MOST = re.compile(
    r"\b(most|highest|maximum|largest|biggest)\b.*\b(spend|spender|money|amount|purchase)\b|"
    r"\bwho spends the most\b|\bwho spent the most\b|\bbiggest spender\b",
    re.I,
)

_BUDGET_CHANGE = re.compile(
    r"\b(change|set|update|adjust|make|raise|lower|increase|decrease|move)\b",
    re.I,
)


def try_parse_budget_change(message: str) -> tuple[str, float] | None:
    """Parse 'set Engineering budget to $400' style requests."""
    text = str(message or "").strip()
    low = text.lower()
    if not re.search(r"\b(budget|budgets|cap|limit)\b", low):
        return None
    if not _BUDGET_CHANGE.search(low):
        return None

    from services.budgets import resolve_department_name

    dept = resolve_department_name(text)
    if not dept:
        match = re.search(
            r"(?:for|of)\s+(?:the\s+)?([a-z][\w\s&-]*?)(?:\s+(?:department|dept))?(?:\s+(?:budget|cap|limit))?\s+to\b",
            low,
        )
        if match:
            dept = resolve_department_name(match.group(1))

    amount_match = re.search(r"\bto\s+\$?\s*([\d,]+(?:\.\d{1,2})?)", text, re.I)
    if not amount_match:
        amount_match = re.search(r"\$\s*([\d,]+(?:\.\d{1,2})?)", text)
    if not dept or not amount_match:
        return None

    amount = float(amount_match.group(1).replace(",", ""))
    if amount < 0:
        return None
    return dept, amount


def try_lookup_budget_cap(message: str) -> dict | None:
    """Answer 'what is Engineering's budget?' from Settings caps."""
    text = str(message or "").strip()
    low = text.lower()
    if not re.search(r"\b(budget|budgets|cap|limit)\b", low):
        return None
    if _BUDGET_CHANGE.search(low):
        return None
    if not re.search(
        r"\b(what|how much|current|cap|limit|remaining|left|tell me|show me)\b",
        low,
    ):
        return None

    from services.budgets import lookup_department_budget, resolve_department_name

    dept = resolve_department_name(text)
    if not dept:
        return None

    info = lookup_department_budget(dept)
    if not info:
        return None

    source = "custom cap from Settings" if info["is_custom"] else "suggested cap"
    reply = (
        f"{info['department']} {info['quarter']} budget cap is {info['budget_fmt']} ({source}). "
        f"Spent so far: {info['spent_fmt']}. Remaining: {info['remaining_fmt']}."
    )
    fc = info.get("forecast") or {}
    if fc.get("outcome") not in ("on_track", "no_data", None) and fc.get("message"):
        reply += f" {fc['message']}"

    return _instant_result(reply, [{"type": "navigate", "view": "budget"}])


def try_apply_budget_change(message: str, *, is_admin: bool) -> dict | None:
    """Apply a department budget update when the user asks Friday to change a cap."""
    parsed = try_parse_budget_change(message)
    if not parsed:
        return None

    if not is_admin:
        return _instant_result(
            "Only admins can change department budgets. Open Settings to view caps, or ask your finance lead.",
            [{"type": "navigate", "view": "settings", "tab": "budgets"}],
        )

    dept, amount = parsed
    from services.budgets import set_department_budget

    try:
        result = set_department_budget(dept, amount)
    except ValueError as exc:
        return _instant_result(str(exc))

    return _instant_result(
        f"Done: {result['department']} {result['quarter']} budget is now "
        f"{result['new_cap_fmt']} (was {result['previous_cap_fmt']}).",
        [
            {
                "type": "budget_updated",
                "view": "budget",
                "department": result["department"],
                "quarter": result["quarter"],
                "new_cap": result["new_cap"],
                "new_cap_fmt": result["new_cap_fmt"],
            }
        ],
    )


def _normalize_nav_text(text: str) -> str:
    cleaned = text.lower()
    cleaned = re.sub(
        r"\b(the|a|an|section|page|tab|area|screen|panel|part)\b", " ", cleaned
    )
    return re.sub(r"\s+", " ", cleaned).strip()


def _wants_navigation(text: str) -> bool:
    low = text.lower()
    if any(trigger in low for trigger in NAV_TRIGGERS):
        return True
    if re.search(r"\b(go|open|show|view|see)\s+(me\s+)?(the\s+)?", low):
        return True
    if re.search(
        r"\b(what needs|what's pending|pending approval|waiting for me)\b", low
    ):
        return "approval" in low or "pending" in low
    return False


def _match_view(text: str) -> str | None:
    normalized = _normalize_nav_text(text)
    for view, patterns in VIEW_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, normalized) or re.search(pattern, text.lower()):
                return view
    return None


def detect_voice_actions(message: str, current_view: str | None = None) -> list[dict]:
    low = message.lower()
    actions: list[dict] = []

    if not _wants_navigation(low):
        if re.search(r"\b(show|list|see)\b.*\b(flag|problem|violation)", low):
            actions.append({"type": "navigate", "view": "alerts"})
        elif re.search(r"\b(how many|count).*\b(approval|pending)", low):
            actions.append({"type": "navigate", "view": "approvals"})
        return actions

    if any(k in low for k in ("spending rules", "policy rules", "edit rules")):
        return [{"type": "navigate", "view": "settings", "tab": "rules"}]
    if any(k in low for k in ("department budget", "budget settings", "set budget")):
        return [{"type": "navigate", "view": "settings", "tab": "budgets"}]

    view = _match_view(low)
    if view:
        action: dict = {"type": "navigate", "view": view}
        if view == "settings":
            if "rule" in low or "policy" in low:
                action["tab"] = "rules"
            elif "budget" in low:
                action["tab"] = "budgets"
        actions.append(action)

    return actions


def _is_nav_only(message: str) -> bool:
    actions = detect_voice_actions(message)
    if not actions:
        return False
    return _DATA_HINTS.search(message.lower()) is None


def _instant_result(reply: str, actions: list | None = None) -> dict:
    return {
        "reply": reply,
        "actions": actions or [],
        "chart_urls": [],
        "tool_calls": [],
        "engine": "instant",
    }


def _employee_spend_extremes(
    employee_name: str | None = None,
) -> tuple[dict | None, dict | None]:
    from services.expenses import _sum_amounts, scoped_expenses
    from core.formatting import fmt_money

    rows = scoped_expenses(employee_name)
    totals = _sum_amounts(rows, "employee")
    if not totals:
        return None, None

    items = list(totals.items())
    top_name, top_amt = items[0]
    low_name, low_amt = items[-1]
    return (
        {"name": top_name, "spend_fmt": fmt_money(top_amt)},
        {"name": low_name, "spend_fmt": fmt_money(low_amt)},
    )


def _personal_transaction_extreme(
    employee_name: str | None, highest: bool = True
) -> dict | None:
    from services.expenses import scoped_expenses
    from core.formatting import fmt_money

    rows = scoped_expenses(employee_name)
    if not rows:
        return None
    row = (
        max(rows, key=lambda r: r["amount"])
        if highest
        else min(rows, key=lambda r: r["amount"])
    )
    return {
        "amount_fmt": fmt_money(row["amount"]),
        "vendor": row.get("vendor") or "unknown vendor",
        "date": row["date"].date().isoformat(),
    }


def _personal_total(employee_name: str | None) -> str | None:
    from services.expenses import scoped_expenses
    from core.formatting import fmt_money

    rows = scoped_expenses(employee_name)
    if not rows:
        return None
    return fmt_money(sum(r["amount"] for r in rows))


def try_instant_response(
    message: str,
    current_view: str | None = None,
    employee_name: str | None = None,
    is_admin: bool = False,
) -> dict | None:
    """Answer immediately from cached site data. No LLM round trip."""
    low = message.lower()
    snap = get_site_snapshot(current_view)
    counts = snap["counts"]
    totals = snap["totals"]
    personal = bool(employee_name)

    budget_change = try_apply_budget_change(message, is_admin=is_admin)
    if budget_change:
        return budget_change

    budget_lookup = try_lookup_budget_cap(message)
    if budget_lookup:
        return budget_lookup

    actions = detect_voice_actions(message, current_view)
    if actions and _is_nav_only(message):
        view = actions[0].get("view", "")
        label = PAGE_LABELS.get(view, view.replace("_", " ").title())
        return _instant_result(f"Opening {label}.", actions)

    if personal and _COMPANY_RANKING.search(message):
        if _PERSONAL_LEAST.search(message):
            txn = _personal_transaction_extreme(employee_name, highest=False)
            if txn:
                return _instant_result(
                    f"Your smallest purchase was {txn['amount_fmt']} at {txn['vendor']} on {txn['date']}."
                )
        if _PERSONAL_MOST.search(message):
            txn = _personal_transaction_extreme(employee_name, highest=True)
            if txn:
                return _instant_result(
                    f"Your largest purchase was {txn['amount_fmt']} at {txn['vendor']} on {txn['date']}."
                )
        total = _personal_total(employee_name)
        if total:
            return _instant_result(f"Your total spend is {total}.")
        return None

    if re.search(r"\b(how many|count|number of).*\b(approval|pending)", low):
        if personal:
            return None
        n = counts["approvals_pending"]
        word = "approval" if n == 1 else "approvals"
        extra = (
            [{"type": "navigate", "view": "approvals"}]
            if _wants_navigation(low)
            else []
        )
        return _instant_result(f"You have {n} pending {word}.", extra)

    if re.search(r"\b(how many|count|number of).*\b(flag|problem|violation)", low):
        if personal:
            from services.expenses import scoped_expenses

            n = sum(
                1 for r in scoped_expenses(employee_name) if r.get("flagged") == "yes"
            )
            return _instant_result(f"You have {n} flagged purchases.")
        n = counts["flags"]
        extra = (
            [{"type": "navigate", "view": "alerts"}] if _wants_navigation(low) else []
        )
        return _instant_result(f"There are {n} flagged purchases.", extra)

    if re.search(r"\b(how many|count).*\b(report|trip)", low):
        if personal:
            return None
        n = counts["reports_pending"]
        return _instant_result(
            f"{n} trip report{'s' if n != 1 else ''} waiting for CFO review.",
        )

    if re.search(
        r"\b(total spend|overall spend|how much (have we )?spent|company spend)\b", low
    ):
        if personal:
            total = _personal_total(employee_name)
            if total:
                return _instant_result(f"Your total spend is {total}.")
            return None
        return _instant_result(f"Total spend is {totals['spend_fmt']}.")

    if re.search(
        r"\b(what needs my attention|what's pending|what should i (do|review|look at))\b",
        low,
    ):
        if personal:
            return None
        return _instant_result(
            f"You have {counts['approvals_pending']} approvals, "
            f"{counts['flags']} flagged purchases, and "
            f"{counts['reports_pending']} trip reports waiting.",
        )

    if re.search(
        r"\b(top department|most spend|who spent the most|biggest spender|highest spender)\b",
        low,
    ):
        if personal:
            txn = _personal_transaction_extreme(employee_name, highest=True)
            if txn and "least" not in low and "lowest" not in low:
                return _instant_result(
                    f"Your largest purchase was {txn['amount_fmt']} at {txn['vendor']}."
                )
            return None
        if "least" not in low and "lowest" not in low:
            most, _ = _employee_spend_extremes()
            if most:
                return _instant_result(
                    f"{most['name']} spends the most, at {most['spend_fmt']} total.",
                )
        if snap["top_departments"]:
            top = snap["top_departments"][0]
            return _instant_result(
                f"{top['name']} leads with {top['spend_fmt']} in total spend."
            )

    if _PERSONAL_LEAST.search(message):
        if personal:
            txn = _personal_transaction_extreme(employee_name, highest=False)
            if txn:
                return _instant_result(
                    f"Your smallest purchase was {txn['amount_fmt']} at {txn['vendor']} on {txn['date']}."
                )
            return None
        _, least = _employee_spend_extremes()
        if least:
            return _instant_result(
                f"{least['name']} spends the least, at {least['spend_fmt']} total.",
            )

    if re.search(r"\bwhat can you|what pages|what do you know\b", low):
        names = ", ".join(PAGE_LABELS[v] for v in PAGE_LABELS)
        return _instant_result(
            f"I can answer spending questions, take actions across the app (budgets, rules, "
            f"approvals, trip reports, project proposals) or open any page: {names}."
        )

    return None


def _strip_for_speech(text: str) -> str:
    cleaned = re.sub(r"\*\*|__|\*|_|`|#+\s?", "", text or "")
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned
