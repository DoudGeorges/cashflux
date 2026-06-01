"""Plain-English spending analytics for Friday (charts, tables, and follow-up context)."""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import defaultdict

from core.formatting import fmt_money
from services.expenses.core import (
    CSV_NAME,
    _find_category_in_query,
    _find_employee_in_query,
    _latest_month,
    _latest_quarter_label,
    _rows_in_month,
    _rows_in_quarter,
    _sum_amounts,
    _sum_by_city,
    _top_items,
    scoped_expenses,
)


_CHART_WORDS = (
    "chart",
    "graph",
    "plot",
    "visual",
    "visualize",
    "visualise",
    "draw a",
    "make a chart",
    "make a graph",
)

_BREAKDOWN_WORDS = (
    "break down",
    "breakdown",
    "by department",
    "by category",
    "by vendor",
    "by employee",
    "by city",
    "by person",
    "spending by",
    "split by",
)

_COMPARE_WORDS = (
    "compare",
    "comparison",
    "versus",
    " vs ",
    "compared to",
    "how does that",
    "what about",
    "relative to",
    "difference between",
)

_TREND_WORDS = (
    "over time",
    "trend",
    "timeline",
    "monthly",
    "month by month",
)

_FORECAST_WORDS = (
    "forecast",
    "burn rate",
    "burn",
    "exceed",
    "run out",
    "over budget",
    "project",
)

_VENDOR_WORDS = (
    "consolidat",
    "duplicate vendor",
    "multiple vendor",
    "same vendor",
    "vendor overlap",
    "too many vendor",
    "coffee vendor",
)

_RANKING_WORDS = (
    "top vendor",
    "top merchants",
    "top spender",
    "top spenders",
    "who spent the most",
    "who spent",
    "top 5",
    "top 10",
    "rank",
)


def _wants_vendor_consolidation(text: str) -> bool:
    if any(w in text for w in _VENDOR_WORDS):
        return True
    return "vendor" in text and any(
        w in text
        for w in ("too many", "duplicate", "multiple", "consolidat", "overlap")
    )


def wants_visualization(message: str, conversation_history=None) -> bool:
    """Charts only when a visual genuinely helps; not for every spending question."""
    current = (message or "").lower().strip()
    if not current:
        return False

    if any(w in current for w in _CHART_WORDS):
        return True

    if any(w in current for w in _COMPARE_WORDS):
        return True

    if any(w in current for w in _BREAKDOWN_WORDS):
        return True

    if any(w in current for w in _TREND_WORDS):
        return True

    if any(w in current for w in _FORECAST_WORDS):
        return True

    if any(w in current for w in _RANKING_WORDS):
        return True

    if _wants_vendor_consolidation(current):
        return True

    if "show me" in current and any(
        w in current
        for w in ("top", "break", "trend", "by ", "chart", "graph", "breakdown")
    ):
        return True

    return False


def is_analytical_query(message: str, conversation_history=None) -> bool:
    """Backward-compatible alias used for voice/Brim routing."""
    return wants_visualization(message, conversation_history)


def get_query_figures_block(
    user_message: str,
    conversation_history=None,
    employee_name=None,
) -> str | None:
    """Exact figures for Gemini when answering without a chart."""
    insight = _resolve_insight(user_message, conversation_history, employee_name)
    if not insight:
        return None
    block = insight.get("_context_block")
    if block:
        return block
    summary = insight.get("summary") or ""
    return summary.replace("**", "") if summary else None


def analyze_spending_query(
    user_message: str,
    conversation_history=None,
    employee_name=None,
) -> dict | None:
    if not wants_visualization(user_message, conversation_history):
        return None
    return _resolve_insight(user_message, conversation_history, employee_name)


def _resolve_insight(
    user_message: str,
    conversation_history=None,
    employee_name=None,
) -> dict | None:
    rows = scoped_expenses(employee_name)
    if not rows:
        return None

    ctx = _extract_context(user_message, conversation_history, rows)
    scoped = _filter_rows(rows, ctx)

    if ctx.compare and len(ctx.departments) >= 2:
        return _comparison_insight(ctx, rows, scoped)

    if ctx.compare and len(ctx.departments) == 1:
        other = _find_comparison_target(
            user_message, conversation_history, rows, ctx.departments[0]
        )
        if other:
            ctx.departments = [ctx.departments[0], other]
            ctx.compare = True
            scoped = _filter_rows(rows, ctx)
            return _comparison_insight(ctx, rows, scoped)

    text = _conversation_text(user_message, conversation_history).lower()
    current = (user_message or "").lower()

    if "by department" in current or (
        "department" in current and "breakdown" in current
    ):
        return _default_department_insight(rows)

    if "by category" in current or ("category" in current and "breakdown" in current):
        by_cat = _top_items(_sum_amounts(rows, "category"), 10)
        total = sum(r["amount"] for r in rows)
        return {
            "title": "Spend by category",
            "summary": f"Company-wide spend by category: **{fmt_money(total)}** total.",
            "chart": {
                "type": "bar",
                "labels": [c for c, _ in by_cat],
                "values": [a for _, a in by_cat],
            },
            "_context_block": f"By category, total={fmt_money(total)}",
        }

    if ctx.departments and ctx.category:
        return _department_category_insight(ctx, scoped)

    if ctx.departments and not ctx.category:
        return _department_insight(ctx, scoped)

    if ctx.category and not ctx.departments:
        return _category_by_department_insight(ctx, rows, scoped)

    if ctx.employee:
        return _employee_insight(ctx, scoped)

    if "top" in text and "vendor" in text:
        return _top_vendors_insight(rows, ctx)

    if any(w in text for w in ("who spent", "by employee", "by person", "top spender")):
        return _by_employee_insight(rows)

    if any(w in text for w in ("city", "location", "where")):
        return _by_city_insight(scoped, ctx)

    if any(w in text for w in ("month", "over time", "trend", "timeline", "when")):
        return _monthly_trend_insight(scoped, employee_name)

    if any(w in text for w in _FORECAST_WORDS):
        return _forecast_insight(user_message, conversation_history)

    if _wants_vendor_consolidation(text):
        return _vendor_consolidation_insight(employee_name)

    return None


@dataclass
class SpendingContext:
    departments: list[str] = field(default_factory=list)
    category: str | None = None
    quarter: str | None = None
    employee: str | None = None
    compare: bool = False
    month: str | None = None


def _conversation_text(message: str, history) -> str:
    parts = [message or ""]
    if history:
        for msg in history[-8:]:
            parts.append(getattr(msg, "text", "") or "")
    return " ".join(parts)


def _extract_context(message: str, history, rows) -> SpendingContext:
    full = _conversation_text(message, history)
    q = full.lower()
    current = (message or "").lower()
    ctx = SpendingContext()

    ctx.departments = _find_departments_in_order(current, rows)
    if not ctx.departments:
        ctx.departments = _find_departments_in_order(q, rows)

    ctx.category = _find_category_in_query(q) or _find_category_in_query(current)
    ctx.employee = _find_employee_in_query(q, rows) or _find_employee_in_query(
        current, rows
    )
    ctx.quarter = _resolve_quarter(q, rows) or _resolve_quarter(current, rows)
    ctx.month = _resolve_month(q, rows)
    ctx.compare = any(
        w in current
        for w in (
            "compare",
            "versus",
            " vs ",
            "compared to",
            "how does that",
            "what about",
            "relative to",
            "difference between",
        )
    )

    if ctx.compare:
        prior_text = _conversation_text("", history) if history else ""
        prior_depts = [
            d
            for d in _find_departments_in_order(prior_text, rows)
            if d not in ctx.departments
        ]
        if prior_depts and len(ctx.departments) == 1:
            ctx.departments = [prior_depts[0], ctx.departments[0]]
        elif prior_depts and not ctx.departments:
            ctx.departments = prior_depts[:2]

    if ctx.compare and len(ctx.departments) < 2:
        other = _find_comparison_target(
            message, history, rows, ctx.departments[0] if ctx.departments else None
        )
        if other and ctx.departments:
            ctx.departments.append(other)
        elif other:
            ctx.departments = [other]

    if not ctx.category:
        ctx.category = _find_category_in_query(_conversation_text("", history))

    if not ctx.quarter:
        ctx.quarter = _resolve_quarter(_conversation_text("", history), rows)

    return ctx


def _find_departments_in_order(text: str, rows) -> list[str]:
    found = []
    q = text.lower()
    depts = sorted(
        {r["department"] for r in rows if r.get("department")}, key=len, reverse=True
    )
    positions = []
    for dept in depts:
        idx = q.find(dept.lower())
        if idx >= 0:
            positions.append((idx, dept))
    for _, dept in sorted(positions, key=lambda item: item[0]):
        if dept not in found:
            found.append(dept)
    if not found:
        try:
            from services.workflow.budgets import resolve_department_name

            for token in q.replace("?", " ").replace(",", " ").split():
                if len(token) < 4:
                    continue
                resolved = resolve_department_name(token)
                if resolved and resolved not in found:
                    found.append(resolved)
        except ImportError:
            pass
    return found[:2]


def _find_comparison_target(message, history, rows, exclude_dept=None) -> str | None:
    text = (message or "").lower()
    depts = sorted(
        {r["department"] for r in rows if r.get("department")}, key=len, reverse=True
    )
    for dept in depts:
        if exclude_dept and dept.lower() == exclude_dept.lower():
            continue
        if dept.lower() in text:
            return dept
    try:
        from services.workflow.budgets import resolve_department_name

        for phrase in (
            "engineering",
            "marketing",
            "finance",
            "operations",
            "sales",
            "hr",
        ):
            if phrase in text:
                resolved = resolve_department_name(phrase)
                if resolved and (
                    not exclude_dept or resolved.lower() != exclude_dept.lower()
                ):
                    return resolved
    except ImportError:
        pass
    return None


def _resolve_quarter(text: str, rows) -> str | None:
    q = text.lower()
    latest = _latest_quarter_label(rows)
    if not latest:
        return None
    year = latest.split()[-1]

    if "last quarter" in q or "previous quarter" in q:
        return latest

    if "this quarter" in q or "current quarter" in q:
        return latest

    for token in ("q1", "q2", "q3", "q4"):
        if token in q:
            return f"{token.upper()} {year}"

    if "quarter" in q:
        return latest

    return None


def _resolve_month(text: str, rows) -> str | None:
    q = text.lower()
    latest = _latest_month(rows)
    if "last month" in q or "this month" in q:
        return latest
    return None


def _filter_rows(rows, ctx: SpendingContext):
    scoped = list(rows)
    if ctx.quarter:
        scoped = _rows_in_quarter(scoped, ctx.quarter)
    if ctx.month:
        scoped = _rows_in_month(scoped, ctx.month)
    if ctx.employee:
        scoped = [r for r in scoped if r["employee"] == ctx.employee]
    if len(ctx.departments) == 1:
        scoped = [r for r in scoped if r["department"] == ctx.departments[0]]
    if ctx.category:
        scoped = [r for r in scoped if r["category"] == ctx.category]
    return scoped


def _comparison_insight(ctx: SpendingContext, rows, scoped) -> dict:
    dept_a, dept_b = ctx.departments[0], ctx.departments[1]
    base = rows
    if ctx.quarter:
        base = _rows_in_quarter(base, ctx.quarter)
    if ctx.category:
        base = [r for r in base if r["category"] == ctx.category]

    totals = {
        dept_a: sum(r["amount"] for r in base if r["department"] == dept_a),
        dept_b: sum(r["amount"] for r in base if r["department"] == dept_b),
    }
    diff = totals[dept_a] - totals[dept_b]
    pct = (totals[dept_a] / totals[dept_b] * 100 - 100) if totals[dept_b] else 0
    scope_bits = []
    if ctx.category:
        scope_bits.append(ctx.category)
    if ctx.quarter:
        scope_bits.append(ctx.quarter)
    scope_label = " · ".join(scope_bits) if scope_bits else "all time"

    higher = dept_a if diff >= 0 else dept_b
    summary = (
        f"**{dept_a}** spent **{fmt_money(totals[dept_a])}** vs **{dept_b}** "
        f"**{fmt_money(totals[dept_b])}** ({scope_label}). "
        f"**{higher}** spent **{fmt_money(abs(diff))}** more"
    )
    if totals[dept_b]:
        summary += (
            f" ({abs(pct):.0f}% {'higher' if diff >= 0 else 'lower'} for {dept_a})."
        )
    else:
        summary += "."

    return {
        "title": f"{dept_a} vs {dept_b}"
        + (f" ({ctx.category}" if ctx.category else ""),
        "summary": summary,
        "chart": {
            "type": "bar",
            "labels": [dept_a, dept_b],
            "values": [totals[dept_a], totals[dept_b]],
            "colors": ["rgba(37, 99, 235, 0.85)", "rgba(99, 102, 241, 0.85)"],
        },
        "table": [
            {"department": dept_a, "spend": fmt_money(totals[dept_a])},
            {"department": dept_b, "spend": fmt_money(totals[dept_b])},
            {"department": "Difference", "spend": fmt_money(abs(diff))},
        ],
        "_context_block": (
            f"Comparison {dept_a}={fmt_money(totals[dept_a])}, "
            f"{dept_b}={fmt_money(totals[dept_b])}, diff={fmt_money(abs(diff))}"
        ),
    }


def _department_category_insight(ctx: SpendingContext, scoped) -> dict:
    dept = ctx.departments[0]
    total = sum(r["amount"] for r in scoped)
    by_vendor = _top_items(_sum_amounts(scoped, "vendor"), 8)
    title = f"{dept}: {ctx.category or 'spend'}"
    if ctx.quarter:
        title += f" ({ctx.quarter})"

    txn_count = len(scoped)
    summary = (
        f"**{dept}** spent **{fmt_money(total)}** on **{ctx.category or 'purchases'}**"
    )
    if ctx.quarter:
        summary += f" in **{ctx.quarter}**"
    summary += f" across **{txn_count}** transaction{'s' if txn_count != 1 else ''}."

    return {
        "title": title,
        "summary": summary,
        "chart": {
            "type": "bar",
            "labels": [v for v, _ in by_vendor] or ["No data"],
            "values": [a for _, a in by_vendor] or [0],
        },
        "table": [
            {
                "vendor": v,
                "amount": fmt_money(a),
                "share": f"{(a / total * 100):.0f}%" if total else "-",
            }
            for v, a in by_vendor[:6]
        ],
        "_context_block": f"{dept} {ctx.category} total={fmt_money(total)}, txns={txn_count}",
    }


def _department_insight(ctx: SpendingContext, scoped) -> dict:
    dept = ctx.departments[0]
    total = sum(r["amount"] for r in scoped)
    by_cat = _top_items(_sum_amounts(scoped, "category"), 8)
    title = f"{dept} spending"
    if ctx.quarter:
        title += f" ({ctx.quarter}"

    return {
        "title": title,
        "summary": f"**{dept}** total spend: **{fmt_money(total)}**"
        + (f" in **{ctx.quarter}**" if ctx.quarter else "")
        + ".",
        "chart": {
            "type": "bar",
            "labels": [c for c, _ in by_cat] or ["No data"],
            "values": [a for _, a in by_cat] or [0],
        },
        "table": [{"category": c, "amount": fmt_money(a)} for c, a in by_cat[:6]],
        "_context_block": f"{dept} total={fmt_money(total)}",
    }


def _category_by_department_insight(ctx: SpendingContext, rows, scoped) -> dict:
    cat = ctx.category
    base = _rows_in_quarter(rows, ctx.quarter) if ctx.quarter else rows
    base = [r for r in base if r["category"] == cat]
    by_dept = _top_items(_sum_amounts(base, "department"), 10)
    total = sum(r["amount"] for r in base)

    return {
        "title": f"{cat} spend by department"
        + (f" ({ctx.quarter}" if ctx.quarter else ""),
        "summary": f"Company-wide **{cat}** spend: **{fmt_money(total)}**"
        + (f" in **{ctx.quarter}**" if ctx.quarter else "")
        + ".",
        "chart": {
            "type": "bar",
            "labels": [d for d, _ in by_dept],
            "values": [a for _, a in by_dept],
        },
        "table": [{"department": d, "amount": fmt_money(a)} for d, a in by_dept[:6]],
        "_context_block": f"{cat} total={fmt_money(total)}",
    }


def _employee_insight(ctx: SpendingContext, scoped) -> dict:
    emp = ctx.employee
    total = sum(r["amount"] for r in scoped)
    by_cat = _top_items(_sum_amounts(scoped, "category"), 8)
    return {
        "title": f"{emp}: spending by category",
        "summary": f"**{emp}** total spend: **{fmt_money(total)}**.",
        "chart": {
            "type": "bar",
            "labels": [c for c, _ in by_cat],
            "values": [a for _, a in by_cat],
        },
        "_context_block": f"{emp} total={fmt_money(total)}",
    }


def _top_vendors_insight(rows, ctx: SpendingContext) -> dict:
    scoped = (
        _filter_rows(rows, ctx)
        if ctx.departments or ctx.category or ctx.quarter
        else rows
    )
    latest_month = ctx.month or _latest_month(rows)
    if latest_month and not ctx.quarter:
        scoped = _rows_in_month(scoped, latest_month)
    vendors = _top_items(_sum_amounts(scoped, "vendor"), 8)
    label = ctx.quarter or latest_month or "all time"
    return {
        "title": f"Top vendors: {label}",
        "summary": f"Top merchants by spend ({label}).",
        "chart": {
            "type": "bar",
            "labels": [v for v, _ in vendors],
            "values": [a for _, a in vendors],
        },
        "table": [
            {"rank": i + 1, "vendor": v, "amount": fmt_money(a)}
            for i, (v, a) in enumerate(vendors)
        ],
    }


def _by_employee_insight(rows) -> dict:
    by_emp = _top_items(_sum_amounts(rows, "employee"), 10)
    return {
        "title": "Spend by employee",
        "summary": f"Top spenders from {CSV_NAME}.",
        "chart": {
            "type": "bar",
            "labels": [e for e, _ in by_emp],
            "values": [a for _, a in by_emp],
        },
        "table": [{"employee": e, "amount": fmt_money(a)} for e, a in by_emp[:8]],
    }


def _by_city_insight(scoped, ctx: SpendingContext) -> dict:
    by_city = _sum_by_city(scoped, limit=10)
    total = sum(r["amount"] for r in scoped)
    return {
        "title": "Spend by city" + (f" ({ctx.quarter}" if ctx.quarter else ""),
        "summary": f"**{fmt_money(total)}** across **{len(by_city)}** cities.",
        "chart": {
            "type": "bar",
            "labels": list(by_city.keys()),
            "values": list(by_city.values()),
        },
    }


def _monthly_trend_insight(scoped, employee_name) -> dict:
    by_month: dict[str, float] = defaultdict(float)
    for r in scoped:
        by_month[r["month"]] += r["amount"]
    months = sorted(by_month.keys())
    title = "My spend over time" if employee_name else "Spend over time"
    return {
        "title": title,
        "summary": f"Monthly spend trend from {CSV_NAME}.",
        "chart": {
            "type": "line",
            "labels": months,
            "values": [by_month[m] for m in months],
        },
    }


def _vendor_consolidation_insight(employee_name: str | None) -> dict | None:
    try:
        from services.expenses.merchants import analyze_vendor_consolidation

        data = analyze_vendor_consolidation(employee_name=employee_name)
        opps = data.get("opportunities") or []
        if not opps:
            return {
                "title": "Vendor consolidation",
                "summary": data.get("headline")
                or "No multi-vendor consolidation opportunities detected.",
            }
        top = opps[:6]
        labels = [o["label"] for o in top]
        values = [o["estimated_savings"] for o in top]
        bullets = "\n".join(
            f"- **{o['label']}**: {o['recommendation']}" for o in top[:4]
        )
        return {
            "title": "Vendor consolidation opportunities",
            "summary": f"{data.get('headline')}\n\n{bullets}",
            "chart": {
                "type": "bar",
                "labels": labels,
                "values": values,
            },
        }
    except Exception:
        return None


def _forecast_insight(message, history) -> dict | None:
    try:
        from services.workflow.budgets import (
            get_forecast_for_query,
            _forecast_chart,
            _debit_df,
            _reference_date,
            transactions,
        )

        text = _conversation_text(message, history)
        fc = get_forecast_for_query(text)
        if not fc:
            return None
        df = _debit_df(transactions())
        ref = _reference_date()
        chart_data = _forecast_chart(fc["department"], df, ref)
        return {
            "title": f"Budget forecast: {fc['department']}",
            "summary": (
                f"**{fc['message']}** Weekly burn: **{fc['weekly_burn_fmt']}** · "
                f"{fc['spent_fmt']} of {fc['budget_fmt']} cap used ({chart_data['quarter']})."
            ),
            "chart": {
                "type": "line",
                "labels": chart_data["labels"],
                "values": chart_data["projected"],
            },
        }
    except Exception:
        return None


def _default_department_insight(rows) -> dict:
    by_dept = _top_items(_sum_amounts(rows, "department"), 10)
    total = sum(r["amount"] for r in rows)
    return {
        "title": "Spend by department",
        "summary": f"Total company spend: **{fmt_money(total)}**.",
        "chart": {
            "type": "bar",
            "labels": [d for d, _ in by_dept],
            "values": [a for _, a in by_dept],
        },
        "_context_block": f"Total spend={fmt_money(total)}, by dept: "
        + ", ".join(f"{d}={fmt_money(a)}" for d, a in by_dept[:6]),
    }


# Backward-compatible alias (app.py and expense_data may import from either module).
get_charts_for_query = analyze_spending_query


# Peer Benchmarks (merged from benchmarks.py)


from collections import defaultdict

from services.expenses.core import load_expenses
from core.formatting import fmt_money


def peer_benchmark_for_employee(name: str) -> dict | None:
    rows = load_expenses()
    emp_rows = [r for r in rows if r.get("employee") == name]
    if not emp_rows:
        return None

    dept = emp_rows[0].get("department") or "Unknown"
    dept_rows = [r for r in rows if r.get("department") == dept]
    dept_totals: dict[str, float] = defaultdict(float)
    for r in dept_rows:
        dept_totals[r.get("employee") or "-"] += float(r.get("amount") or 0)

    emp_total = sum(float(r.get("amount") or 0) for r in emp_rows)
    peer_amounts = sorted(dept_totals.values())
    dept_median = peer_amounts[len(peer_amounts) // 2] if peer_amounts else 0
    dept_avg = sum(peer_amounts) / len(peer_amounts) if peer_amounts else 0

    rank = 1 + sum(1 for v in peer_amounts if v > emp_total)
    percentile = int(100 * (1 - (rank - 1) / max(len(peer_amounts), 1)))

    cat_emp: dict[str, float] = defaultdict(float)
    cat_dept: dict[str, float] = defaultdict(float)
    for r in emp_rows:
        cat_emp[r.get("category") or "Other"] += float(r.get("amount") or 0)
    for r in dept_rows:
        cat_dept[r.get("category") or "Other"] += float(r.get("amount") or 0)

    n_peers = len(dept_totals)
    cat_compare = []
    for cat, amt in sorted(cat_emp.items(), key=lambda x: -x[1])[:5]:
        dept_cat_avg = cat_dept[cat] / max(n_peers, 1)
        delta = amt - dept_cat_avg
        cat_compare.append(
            {
                "category": cat,
                "employee_fmt": fmt_money(amt),
                "dept_avg_fmt": fmt_money(dept_cat_avg),
                "delta_fmt": fmt_money(abs(delta)),
                "direction": "above"
                if delta > 0
                else "below"
                if delta < 0
                else "on par",
            }
        )

    vs_median = emp_total - dept_median
    summary = (
        f"{name} spent {fmt_money(emp_total)} - "
        f"{'above' if vs_median > 0 else 'below' if vs_median < 0 else 'at'} "
        f"the {dept} median ({fmt_money(dept_median)})."
    )

    return {
        "employee": name,
        "department": dept,
        "employee_total_fmt": fmt_money(emp_total),
        "dept_median_fmt": fmt_money(dept_median),
        "dept_average_fmt": fmt_money(dept_avg),
        "peer_count": n_peers,
        "spend_rank": rank,
        "spend_percentile": percentile,
        "vs_median_fmt": fmt_money(abs(vs_median)),
        "vs_median_direction": "above"
        if vs_median > 0
        else "below"
        if vs_median < 0
        else "on par",
        "category_compare": cat_compare,
        "summary": summary,
    }



# Spending Oracle / Surprise Insights (merged from surprise.py)


import random
from collections import Counter, defaultdict
from datetime import datetime

from services.expenses.core import load_expenses, scoped_expenses
from core.formatting import fmt_money

_COFFEE_HINTS = ("starbucks", "coffee", "tim hortons", "cafe", "espresso")
_FUEL_CATEGORIES = ("fuel", "gas", "petrol")
_MEAL_CATEGORIES = ("meal", "restaurant", "food", "entertainment", "dining", "coffee")

_PERSONALITIES = {
    "meals": (
        "The Connoisseur",
        "fa-utensils",
        "Your spend speaks fluent menu French.",
    ),
    "fuel": ("The Road Warrior", "fa-road", "Mileage is a lifestyle, not a line item."),
    "software": (
        "The Stack Builder",
        "fa-code",
        "Every subscription is a brick in the tower.",
    ),
    "travel": ("The Nomad", "fa-plane", "Home is where the corporate card is."),
    "lodging": ("The Suite Life", "fa-hotel", "Turn-down service, turn-up analytics."),
    "telecom": (
        "The Signal Keeper",
        "fa-signal",
        "Connected everywhere, reconciled eventually.",
    ),
    "default": (
        "The Curious CFO",
        "fa-wand-magic-sparkles",
        "The numbers whisper secrets to those who listen.",
    ),
}


def _category_bucket(category: str) -> str:
    cat = (category or "").lower()
    if any(k in cat for k in _MEAL_CATEGORIES):
        return "meals"
    if any(k in cat for k in _FUEL_CATEGORIES):
        return "fuel"
    if "software" in cat or "subscription" in cat:
        return "software"
    if "travel" in cat or "transport" in cat:
        return "travel"
    if "lodging" in cat or "hotel" in cat:
        return "lodging"
    if "telecom" in cat or "phone" in cat:
        return "telecom"
    return "default"


def _pick_personality(rows: list[dict]) -> dict:
    totals: dict[str, float] = defaultdict(float)
    for r in rows:
        totals[_category_bucket(r.get("category") or "")] += float(r.get("amount") or 0)
    if not totals:
        key = "default"
    else:
        key = max(totals.items(), key=lambda x: x[1])[0]
        if key == "default" and len(totals) > 1:
            key = max(
                ((k, v) for k, v in totals.items() if k != "default"),
                key=lambda x: x[1],
                default=("default", 0),
            )[0]
    title, icon, tagline = _PERSONALITIES.get(key, _PERSONALITIES["default"])
    return {"title": title, "icon": icon, "tagline": tagline, "bucket": key}


def _sparkline_weeks(rows: list[dict], weeks: int = 12) -> dict:
    if not rows:
        return {"labels": [], "values": []}
    by_week: dict[str, float] = defaultdict(float)
    for r in rows:
        dt = r.get("date")
        if not dt:
            continue
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt[:10])
            except ValueError:
                continue
        week = dt.strftime("%Y-W%W")
        by_week[week] += float(r.get("amount") or 0)
    ordered = sorted(by_week.items())[-weeks:]
    return {
        "labels": [w for w, _ in ordered],
        "values": [round(v, 2) for _, v in ordered],
    }


def _build_insight_pool(rows: list[dict], *, personal: bool) -> list[dict]:
    pool: list[dict] = []
    if not rows:
        return [
            {
                "emoji": "🌱",
                "headline": "A blank ledger is full of possibility",
                "body": "No purchases yet: the oracle sees infinite potential (and zero receipts).",
            }
        ]

    total = sum(float(r.get("amount") or 0) for r in rows)
    pool.append(
        {
            "emoji": "💰",
            "headline": f"{fmt_money(total)} on the move",
            "body": (
                f"That's enough $20 bills to stack about {max(int(total / 20 * 0.003), 1)} metres high: "
                "a very expensive ruler."
            ),
        }
    )

    vendors = Counter((r.get("vendor") or "Unknown").strip() for r in rows)
    if vendors:
        top_vendor, top_count = vendors.most_common(1)[0]
        pool.append(
            {
                "emoji": "💪",
                "headline": f"{top_vendor} knows your name",
                "body": f"You've stopped by {top_count} time{'s' if top_count != 1 else ''}. Loyalty program: unlocked.",
            }
        )

    coffee_spend = sum(
        float(r.get("amount") or 0)
        for r in rows
        if any(h in (r.get("vendor") or "").lower() for h in _COFFEE_HINTS)
        or "coffee" in (r.get("category") or "").lower()
    )
    if coffee_spend >= 50:
        cups = max(int(coffee_spend / 6), 1)
        pool.append(
            {
                "emoji": "☕",
                "headline": f"{fmt_money(coffee_spend)} of liquid motivation",
                "body": f"Roughly {cups} lattes worth of caffeine diplomacy. The oracle does not judge.",
            }
        )

    by_dow: dict[int, float] = defaultdict(float)
    for r in rows:
        dt = r.get("date")
        if dt:
            by_dow[
                dt.weekday()
                if hasattr(dt, "weekday")
                else datetime.fromisoformat(str(dt)[:10]).weekday()
            ] += float(r.get("amount") or 0)
    if by_dow:
        names = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        busiest = max(by_dow.items(), key=lambda x: x[1])
        quietest = min(by_dow.items(), key=lambda x: x[1])
        if quietest[1] > 0:
            pct = int((busiest[1] / quietest[1] - 1) * 100)
            pool.append(
                {
                    "emoji": "📅",
                    "headline": f"{names[busiest[0]]} is spend day",
                    "body": f"{pct}% more out the door than quiet {names[quietest[0]]}. Calendar blocked for commerce.",
                }
            )

    cities = Counter(
        (r.get("city") or "").strip() for r in rows if (r.get("city") or "").strip()
    )
    if cities:
        city, count = cities.most_common(1)[0]
        pool.append(
            {
                "emoji": "🗺️",
                "headline": f"{city} is your money magnet",
                "body": f"{count} purchases mapped there. The dots on the map aren't decoration: they're you.",
            }
        )

    big = max(rows, key=lambda r: float(r.get("amount") or 0))
    amt = float(big.get("amount") or 0)
    dt_val = big.get("date")
    dt_str = dt_val.date().isoformat() if hasattr(dt_val, "date") else str(dt_val)[:10] if dt_val else "record"  # type: ignore
    pool.append(
        {
            "emoji": "🎯",
            "headline": f"Peak purchase: {fmt_money(amt)}",
            "body": f"{big.get('vendor', 'Unknown vendor')} on {dt_str}. "
            + ("Your personal Everest." if personal else "Company legend material."),
        }
    )

    if not personal:
        dept_meals: dict[str, float] = defaultdict(float)
        for r in rows:
            cat = (r.get("category") or "").lower()
            if any(k in cat for k in _MEAL_CATEGORIES):
                dept_meals[r.get("department") or "Unknown"] += float(
                    r.get("amount") or 0
                )
        if dept_meals:
            dept, amt = max(dept_meals.items(), key=lambda x: x[1])
            pool.append(
                {
                    "emoji": "🍽️",
                    "headline": f"{dept} runs on meals",
                    "body": f"{fmt_money(amt)} on food & entertainment. The oracle smells reservations.",
                }
            )

    flagged = sum(1 for r in rows if r.get("flagged") == "yes")
    if flagged:
        pool.append(
            {
                "emoji": "🚩",
                "headline": f"{flagged} flagged purchase{'s' if flagged != 1 else ''}",
                "body": "Even the oracle raises an eyebrow sometimes. Review queue material.",
            }
        )

    return pool


def build_spending_oracle(*, employee_name: str | None = None) -> dict:
    """Return personality, insights, sparkline, and flair for the surprise modal."""
    rows = scoped_expenses(employee_name)
    personal = bool(employee_name)
    personality = _pick_personality(rows)
    pool = _build_insight_pool(rows, personal=personal)
    rng = random.Random(
        hash((employee_name or "company", datetime.now().strftime("%Y-%m-%d")))
    )
    insights = rng.sample(pool, min(3, len(pool)))
    spark = _sparkline_weeks(rows)

    tx_count = len(rows)
    employee_count = len(
        {r.get("employee") for r in load_expenses() if r.get("employee")}
    )

    return {
        "personality": personality,
        "insights": insights,
        "sparkline": spark,
        "meta": {
            "transaction_count": tx_count,
            "scope": "personal" if personal else "company",
            "employee_count": employee_count if not personal else None,
        },
        "flair": rng.choice(
            [
                "The ledger never lies - but it occasionally jokes.",
                "Friday consulted the spreadsheets in a séance.",
                "Derived from real transactions. Magic is just good grouping.",
                "Your CFO would either laugh or cry. Possibly both.",
            ]
        ),
    }




