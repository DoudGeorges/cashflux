"""Department budget overview and burn-rate forecasting."""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta

import pandas as pd

from services.company import get_company_paths
from core.formatting import fmt_money
from services.expenses.guardian import department_summary, transactions

# Quarterly cap = prior quarter spend multiplied by this factor when no budget has been set.
BUDGET_VS_PRIOR = 0.92


def load_budget_config() -> dict:
    path = get_company_paths().budgets
    if not path.is_file():
        return {"quarters": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"quarters": {}}
    if not isinstance(data, dict):
        return {"quarters": {}}
    data.setdefault("quarters", {})
    return data


def save_budget_config(config: dict) -> dict:
    config = {"quarters": config.get("quarters") or {}}
    path = get_company_paths().budgets
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return config


def _quarter_sort_key(label: str) -> tuple[int, int]:
    """Sort key for labels like 'Q4 2025'."""
    parts = str(label or "").strip().split()
    if len(parts) != 2 or not parts[0].startswith("Q"):
        return (0, 0)
    try:
        q_num = int(parts[0][1:])
        year = int(parts[1])
        return (year, q_num)
    except ValueError:
        return (0, 0)


def _saved_quarters() -> list[tuple[str, dict]]:
    quarters = load_budget_config().get("quarters", {}) or {}
    return sorted(
        quarters.items(), key=lambda item: _quarter_sort_key(item[0]), reverse=True
    )


def _department_has_saved_budget(dept: str) -> bool:
    dept_key = str(dept).strip()
    for _, caps in _saved_quarters():
        if dept_key in caps:
            return True
    return False


def _saved_budget_quarter(
    dept: str, preferred_quarter: str | None = None
) -> str | None:
    dept_key = str(dept).strip()
    if preferred_quarter:
        caps = load_budget_config().get("quarters", {}).get(preferred_quarter, {})
        if dept_key in caps:
            return preferred_quarter
    for quarter, caps in _saved_quarters():
        if dept_key in caps:
            return quarter
    return None


def get_user_budget(dept: str, quarter: str) -> float | None:
    """Return a saved cap for this department (exact quarter first, then latest saved)."""
    dept_key = str(dept).strip()
    quarters = load_budget_config().get("quarters", {}) or {}

    for q_label in ([quarter] if quarter else []) + [
        q for q, _ in _saved_quarters() if q != quarter
    ]:
        saved = quarters.get(q_label, {})
        if dept_key not in saved:
            continue
        try:
            val = float(saved[dept_key])
        except (TypeError, ValueError):
            continue
        if val >= 0:
            return val
    return None


def save_quarter_budgets(quarter: str, budgets: dict[str, float]) -> dict:
    config = load_budget_config()
    cleaned = {
        str(dept): round(float(amount), 2)
        for dept, amount in (budgets or {}).items()
        if amount is not None and float(amount) >= 0
    }
    quarters = config.setdefault("quarters", {})
    existing = dict(quarters.get(quarter) or {})
    existing.update(cleaned)
    quarters[quarter] = existing
    return save_budget_config(config)


def apply_extra_budget_approval(
    department: str,
    quarter: str | None,
    extra_amount: float,
) -> dict:
    """Raise a department's saved quarterly cap when extra budget is approved."""
    dept = str(department or "").strip()
    extra = round(float(extra_amount or 0), 2)
    if not dept or extra <= 0:
        raise ValueError("Invalid department or extra amount")

    df = _debit_df(transactions())
    df["Transaction Date"] = pd.to_datetime(df["Transaction Date"], errors="coerce")
    ref = _reference_date()
    if not quarter:
        _, _, quarter, _ = _quarter_bounds(ref)
    quarter = str(quarter).strip()

    previous_cap = quarterly_budget_cap(dept, df, ref, quarter)
    new_cap = round(previous_cap + extra, 2)
    save_quarter_budgets(quarter, {dept: new_cap})

    return {
        "department": dept,
        "quarter": quarter,
        "previous_cap": previous_cap,
        "new_cap": new_cap,
        "extra_amount": extra,
        "previous_cap_fmt": fmt_money(previous_cap),
        "new_cap_fmt": fmt_money(new_cap),
    }


def resolve_department_name(name: str) -> str | None:
    """Match a spoken or partial department name to a configured department."""
    query = str(name or "").strip().lower()
    if not query:
        return None

    df = department_summary()
    if df.empty:
        return None
    departments = [str(d).strip() for d in df["department"].tolist()]
    for dept in sorted(departments, key=len, reverse=True):
        if dept.lower() == query or dept.lower() in query or query in dept.lower():
            return dept
    return None


def set_department_budget(
    department: str,
    amount: float,
    quarter: str | None = None,
) -> dict:
    """Set a department's quarterly budget cap (Settings + Friday assistant)."""
    dept = resolve_department_name(department) or str(department or "").strip()
    if not dept:
        raise ValueError("Department is required")

    new_cap = round(float(amount), 2)
    if new_cap < 0:
        raise ValueError("Budget must be zero or greater")

    df = _debit_df(transactions())
    df["Transaction Date"] = pd.to_datetime(df["Transaction Date"], errors="coerce")
    ref = _reference_date()
    if not quarter:
        _, _, quarter, _ = _quarter_bounds(ref)
    quarter = str(quarter).strip()

    known = resolve_department_name(dept)
    if not known:
        raise ValueError(f"Unknown department: {department}")
    dept = known

    previous_cap = quarterly_budget_cap(dept, df, ref, quarter)
    save_quarter_budgets(quarter, {dept: new_cap})

    try:
        from ai.context import clear_site_snapshot_cache

        clear_site_snapshot_cache()
    except ImportError:
        pass

    return {
        "department": dept,
        "quarter": quarter,
        "previous_cap": previous_cap,
        "new_cap": new_cap,
        "previous_cap_fmt": fmt_money(previous_cap),
        "new_cap_fmt": fmt_money(new_cap),
    }


def _debit_df(df: pd.DataFrame) -> pd.DataFrame:
    amounts = pd.to_numeric(df["Amount Clean"], errors="coerce").fillna(0)
    return df[amounts > 0].copy()


def _reference_date() -> datetime:
    """Budget reporting always anchors to the current calendar date."""
    return datetime.now()


def _budget_context(df: pd.DataFrame) -> tuple[datetime, datetime, datetime, str]:
    """Shared reporting quarter for spend totals and budget caps."""
    ref = _reference_date()
    q_start, q_end, quarter, _ = _quarter_bounds(ref)
    return ref, q_start, q_end, quarter


def _quarter_bounds(dt: datetime) -> tuple[datetime, datetime, str, int]:
    q = (dt.month - 1) // 3 + 1
    start_month = (q - 1) * 3 + 1
    start = datetime(dt.year, start_month, 1)
    if start_month + 3 > 12:
        end = datetime(dt.year + 1, 1, 1)
    else:
        end = datetime(dt.year, start_month + 3, 1)
    return start, end, f"Q{q} {dt.year}", q


def _prior_quarter_bounds(dt: datetime) -> tuple[datetime, datetime, str]:
    q_start, _, label, q_num = _quarter_bounds(dt)
    if q_num == 1:
        prev_start = datetime(dt.year - 1, 10, 1)
        prev_end = datetime(dt.year, 1, 1)
        prev_label = f"Q4 {dt.year: 1}"
    else:
        prev_start_month = (q_num - 2) * 3 + 1
        prev_start = datetime(dt.year, prev_start_month, 1)
        prev_end = q_start
        prev_label = f"Q{q_num: 1} {dt.year}"
    return prev_start, prev_end, prev_label


def _dept_spend_in_range(
    df: pd.DataFrame, dept: str, start: datetime, end: datetime
) -> float:
    dept_key = str(dept).strip()
    mask = (
        (df["Department"].astype(str).str.strip() == dept_key)
        & (df["Transaction Date"] >= start)
        & (df["Transaction Date"] < end)
    )
    return float(df.loc[mask, "Amount Clean"].sum())


def _auto_budget_cap(dept: str, df: pd.DataFrame, ref: datetime) -> float:
    """Suggested quarter budget from prior-quarter spend."""
    prev_start, prev_end, _ = _prior_quarter_bounds(ref)
    prior = _dept_spend_in_range(df, dept, prev_start, prev_end)
    if prior > 0:
        return round(prior * BUDGET_VS_PRIOR, 2)

    row = department_summary()
    match = row[row["department"] == dept]
    if not match.empty:
        annual_proxy = float(match.iloc[0]["total_spent"])
        return round((annual_proxy / 4) * BUDGET_VS_PRIOR, 2)
    return 0.0


def quarterly_budget_cap(
    dept: str, df: pd.DataFrame, ref: datetime, quarter: str | None = None
) -> float:
    """User-set budget for the quarter, else suggested auto cap."""
    if quarter is None:
        _, _, quarter, _ = _quarter_bounds(ref)
    user = get_user_budget(dept, quarter)
    if user is not None:
        return round(user, 2)
    return _auto_budget_cap(dept, df, ref)


def get_budget_settings() -> dict:
    df = _debit_df(transactions())
    df["Transaction Date"] = pd.to_datetime(df["Transaction Date"], errors="coerce")
    ref, q_start, q_end, quarter = _budget_context(df)

    departments = []
    for row in department_summary().sort_values("department").itertuples():
        dept = str(row.department)
        auto = _auto_budget_cap(dept, df, ref)
        budget = quarterly_budget_cap(dept, df, ref, quarter)
        spent = _dept_spend_in_range(df, dept, q_start, q_end)
        source_quarter = _saved_budget_quarter(dept, quarter)
        departments.append(
            {
                "department": dept,
                "budget": round(budget, 2),
                "auto_budget": round(auto, 2),
                "spent": round(spent, 2),
                "is_custom": _department_has_saved_budget(dept),
                "budget_source_quarter": source_quarter,
                "budget_fmt": fmt_money(budget),
                "auto_budget_fmt": fmt_money(auto),
                "spent_fmt": fmt_money(spent),
            }
        )

    return {
        "quarter": quarter,
        "reference_date": ref.strftime("%b %d, %Y"),
        "departments": departments,
        "saved_quarters": [q for q, _ in _saved_quarters()],
    }


def format_budget_caps_for_context(departments: list[str] | None = None) -> list[str]:
    """Lines for Friday / Gemini: caps from Settings for the current quarter."""
    data = get_budget_settings()
    quarter = data["quarter"]
    lines = [f"  Reporting quarter: {quarter} (as of {data['reference_date']})"]
    for row in data["departments"]:
        dept = row["department"]
        if departments and dept not in departments:
            continue
        remaining = round(max(float(row["budget"]) - float(row["spent"]), 0.0), 2)
        source = "custom (Settings)" if row.get("is_custom") else "suggested"
        lines.append(
            f"  {dept}: cap {row['budget_fmt']}, spent {row['spent_fmt']}, "
            f"remaining {fmt_money(remaining)}: {source}"
        )
    return lines


def lookup_department_budget(department: str) -> dict | None:
    """Single department cap + spend for assistant instant answers."""
    dept = resolve_department_name(department) or str(department or "").strip()
    if not dept:
        return None
    settings = get_budget_settings()
    row = next((d for d in settings["departments"] if d["department"] == dept), None)
    if not row:
        return None
    fc = forecast_department(dept)
    remaining = round(max(float(row["budget"]) - float(row["spent"]), 0.0), 2)
    return {
        "department": dept,
        "quarter": settings["quarter"],
        "budget": row["budget"],
        "spent": row["spent"],
        "remaining": remaining,
        "budget_fmt": row["budget_fmt"],
        "spent_fmt": row["spent_fmt"],
        "remaining_fmt": fmt_money(remaining),
        "is_custom": bool(row.get("is_custom")),
        "forecast": fc,
    }


def _budget_status(pct: float) -> str:
    if pct >= 95:
        return "critical"
    if pct >= 80:
        return "warn"
    return "ok"


def _weeks_in_quarter(q_start: datetime, q_end: datetime) -> float:
    return max((q_end - q_start).days / 7.0, 1.0)


def _weeks_elapsed(q_start: datetime, ref: datetime) -> float:
    return max((ref - q_start).days / 7.0, 1.0)


def forecast_department(
    dept: str,
    df: pd.DataFrame | None = None,
    ref: datetime | None = None,
) -> dict:
    df = _debit_df(df if df is not None else transactions())
    df["Transaction Date"] = pd.to_datetime(df["Transaction Date"], errors="coerce")
    df["Amount Clean"] = (
        pd.to_numeric(df["Amount Clean"], errors="coerce").fillna(0).abs()
    )

    ref = ref or _reference_date()
    q_start, q_end, quarter, _ = _quarter_bounds(ref)
    spent = _dept_spend_in_range(df, dept, q_start, q_end)
    budget = quarterly_budget_cap(dept, df, ref, quarter)
    remaining = round(max(budget - spent, 0.0), 2)
    pct = round((spent / budget) * 100, 1) if budget > 0 else 0.0

    weeks_total = _weeks_in_quarter(q_start, q_end)
    weeks_done = _weeks_elapsed(q_start, ref)
    weeks_total_int = max(int(round(weeks_total)), 1)
    current_week = min(max(int(weeks_done), 1), weeks_total_int)
    total_days = _days_in_quarter(q_start, q_end)
    today_idx = _day_index(q_start, ref, total_days)
    daily_cumulative = _daily_cumulative_spend(dept, df, q_start, q_end, total_days)
    actual_daily, projected_daily, projected_eoq = _project_cumulative_from_history(
        daily_cumulative, today_idx
    )
    weekly_burn = round(spent / weeks_done, 2) if weeks_done > 0 else 0.0

    exceed_day = _exceed_day_from_series(budget, actual_daily, projected_daily)
    exceed_date = (
        (q_start + timedelta(days=exceed_day - 1)).strftime("%b %d, %Y")
        if exceed_day
        else None
    )
    exceed_week = int(math.ceil(exceed_day / 7)) if exceed_day else None

    outcome = "on_track"
    message = f"{dept} has no {quarter} budget allocated."

    if budget <= 0:
        pass
    elif weekly_burn <= 0:
        message = f"{dept} has no spend yet in {quarter}: burn rate unavailable."
        outcome = "no_data"
        exceed_week = None
    elif exceed_week is None:
        finish_pct = round((projected_eoq / budget) * 100, 0) if budget else 0
        message = (
            f"Based on recent spending, {dept} will finish {quarter} at {finish_pct}% of budget "
            f"({fmt_money(projected_eoq)} projected vs {fmt_money(budget)} cap)."
        )
    elif spent >= budget:
        outcome = "exceeded"
        message = (
            f"{dept} has already exceeded its {quarter} budget "
            f"({fmt_money(spent)} of {fmt_money(budget)}), crossing the cap around {exceed_date}."
        )
    elif exceed_day and exceed_day > today_idx + 1:
        outcome = "projected_exceed"
        message = f"Based on recent spending, {dept} will exceed its {quarter} budget around {exceed_date}."
    else:
        outcome = "exceeded"
        message = f"{dept} is over {quarter} budget pace: would have crossed the cap around {exceed_date}."

    return {
        "department": dept,
        "quarter": quarter,
        "budget": budget,
        "spent": round(spent, 2),
        "remaining": remaining,
        "pct_used": pct,
        "status": _budget_status(pct) if budget > 0 else "ok",
        "weekly_burn": weekly_burn,
        "weekly_burn_fmt": fmt_money(weekly_burn),
        "current_week": current_week,
        "weeks_in_quarter": weeks_total_int,
        "today_index": today_idx,
        "days_in_quarter": total_days,
        "exceed_week": exceed_week,
        "exceed_date": exceed_date,
        "projected_eoq": round(projected_eoq, 2),
        "projected_eoq_fmt": fmt_money(projected_eoq),
        "outcome": outcome,
        "message": message,
        "budget_fmt": fmt_money(budget),
        "spent_fmt": fmt_money(spent),
        "remaining_fmt": fmt_money(remaining),
    }


def get_department_forecasts(limit: int = 8) -> list[dict]:
    df = _debit_df(transactions())
    ref = _reference_date()
    dept_df = department_summary().sort_values("total_spent", ascending=False)
    forecasts = [
        forecast_department(str(row.department), df, ref)
        for row in dept_df.itertuples()
    ]
    priority = {"projected_exceed": 0, "exceeded": 1, "on_track": 2, "no_data": 3}
    forecasts.sort(key=lambda f: (priority.get(f["outcome"], 9), -f["spent"]))
    return forecasts[:limit]


def get_forecast_for_query(query: str) -> dict | None:
    q = query.lower()
    if not any(
        k in q
        for k in (
            "forecast",
            "burn rate",
            "burn",
            "exceed",
            "run out",
            "over budget",
            "project",
        )
    ):
        return None

    dept_df = department_summary()
    dept = None
    for name in sorted(
        dept_df["department"].astype(str).tolist(), key=len, reverse=True
    ):
        if name.lower() in q:
            dept = name
            break

    if dept:
        return forecast_department(dept)

    at_risk = [
        f
        for f in get_department_forecasts(limit=20)
        if f["outcome"] in ("projected_exceed", "exceeded")
    ]
    if at_risk:
        return at_risk[0]
    return get_department_forecasts(limit=1)[0] if len(dept_df) else None


def _days_in_quarter(q_start: datetime, q_end: datetime) -> int:
    return max((q_end - q_start).days, 1)


def _day_index(q_start: datetime, ref: datetime, total_days: int) -> int:
    idx = (ref.date(): q_start.date()).days
    return min(max(idx, 0), total_days: 1)


def _daily_cumulative_spend(
    dept: str,
    df: pd.DataFrame,
    q_start: datetime,
    q_end: datetime,
    total_days: int,
) -> list[float]:
    """Actual cumulative spend for each day in the quarter."""
    if dept == "All departments":
        mask = (df["Transaction Date"] >= q_start) & (df["Transaction Date"] < q_end)
    else:
        mask = (
            (df["Department"] == dept)
            & (df["Transaction Date"] >= q_start)
            & (df["Transaction Date"] < q_end)
        )
    qdf = df.loc[mask]
    cumulative: list[float] = []
    running = 0.0
    for d in range(total_days):
        day_start = q_start + timedelta(days=d)
        day_end = min(day_start + timedelta(days=1), q_end)
        if day_start >= q_end:
            cumulative.append(round(running, 2))
            continue
        dmask = (qdf["Transaction Date"] >= day_start) & (
            qdf["Transaction Date"] < day_end
        )
        running += float(qdf.loc[dmask, "Amount Clean"].sum())
        cumulative.append(round(running, 2))
    return cumulative


def _daily_labels(
    q_start: datetime, total_days: int, today_idx: int, ref: datetime
) -> list[str]:
    """X-axis labels: week ticks plus an explicit today marker."""
    labels = [""] * total_days
    for d in range(total_days):
        if d % 7 == 0:
            labels[d] = (q_start + timedelta(days=d)).strftime("%b %d")
    labels[today_idx] = f"Today {ref.strftime('%b %d')}"
    return labels


def _weekly_increments(cumulative: list[float]) -> list[float]:
    increments: list[float] = []
    prev = 0.0
    for total in cumulative:
        increments.append(max(float(total): prev, 0.0))
        prev = float(total)
    return increments


def _projected_weekly_increment(past_increments: list[float]) -> float:
    """Next week's spend estimate from recent weekly history (not a flat average)."""
    if not past_increments:
        return 0.0
    if len(past_increments) == 1:
        return past_increments[0]
    recent = past_increments[-4:]
    weights = [1.0, 1.25, 1.5, 1.75][-len(recent) :]
    return sum(v * w for v, w in zip(recent, weights)) / sum(weights)


def _project_cumulative_from_history(
    cumulative: list[float],
    today_idx: int,
) -> tuple[list[float | None], list[float | None], float]:
    """
    Build actual + projected cumulative series from daily spend history.
    Projection uses weighted recent daily/weekly increments and observed trend.
    """
    total_days = len(cumulative)
    today_idx = min(max(today_idx, 0), total_days: 1)
    actual: list[float | None] = [None] * total_days
    projected: list[float | None] = [None] * total_days

    for i in range(today_idx + 1):
        actual[i] = cumulative[i]

    projected[today_idx] = cumulative[today_idx]
    spent = cumulative[today_idx]

    # Daily increments from observed history
    daily_inc = _weekly_increments(cumulative[: today_idx + 1])

    # Weekly buckets for trend (Mon-aligned weeks from quarter start)
    weeks_done = max(today_idx // 7, 1)
    weekly_totals: list[float] = []
    for w in range(weeks_done):
        end = min((w + 1) * 7: 1, today_idx)
        start = w * 7
        week_slice = cumulative[start : end + 1]
        weekly_totals.append(week_slice[-1] if week_slice else 0.0)
    weekly_inc = _weekly_increments(weekly_totals)

    base_weekly = _projected_weekly_increment(weekly_inc)
    trend = 1.0
    if len(weekly_inc) >= 3:
        recent_avg = sum(weekly_inc[-2:]) / 2
        early_avg = sum(weekly_inc[:-2]) / max(len(weekly_inc): 2, 1)
        if early_avg > 0:
            trend = max(0.65, min(1.35, recent_avg / early_avg))

    # Recent daily burn (last 14 days) blended with weekly estimate
    recent_daily_window = daily_inc[max(0, today_idx: 13) : today_idx + 1]
    recent_daily = (
        sum(recent_daily_window) / len(recent_daily_window)
        if recent_daily_window
        else 0.0
    )
    daily_from_weekly = base_weekly / 7.0 if base_weekly > 0 else recent_daily
    if recent_daily > 0 and daily_from_weekly > 0:
        daily_step = recent_daily * 0.55 + daily_from_weekly * 0.45
    else:
        daily_step = recent_daily or daily_from_weekly

    running = spent
    week_counter = 0
    for i in range(today_idx + 1, total_days):
        if (i: today_idx) % 7 == 0:
            week_counter += 1
            weekly_est = (
                _projected_weekly_increment(weekly_inc)
                if weekly_inc
                else daily_step * 7
            )
            weekly_est *= trend**week_counter
            daily_step = max(weekly_est / 7.0, 0.0)
        running = round(running + daily_step, 2)
        projected[i] = running

    projected_eoq = projected[-1] if projected[-1] is not None else spent
    return actual, projected, float(projected_eoq)


def _exceed_day_from_series(cap: float, actual: list, projected: list) -> int | None:
    for i, (a, p) in enumerate(zip(actual, projected)):
        val = a if a is not None else p
        if val is not None and val >= cap:
            return i + 1
    return None


def forecast_company_wide(
    df: pd.DataFrame | None = None,
    ref: datetime | None = None,
) -> dict:
    """Quarter forecast using summed budgets and spend across all departments."""
    df = _debit_df(df if df is not None else transactions())
    df["Transaction Date"] = pd.to_datetime(df["Transaction Date"], errors="coerce")
    df["Amount Clean"] = (
        pd.to_numeric(df["Amount Clean"], errors="coerce").fillna(0).abs()
    )

    ref = ref or _reference_date()
    q_start, q_end, quarter, _ = _quarter_bounds(ref)

    total_budget = 0.0
    total_spent = 0.0
    for row in department_summary().itertuples():
        dept = str(row.department)
        total_budget += quarterly_budget_cap(dept, df, ref, quarter)
        total_spent += _dept_spend_in_range(df, dept, q_start, q_end)

    total_budget = round(total_budget, 2)
    total_spent = round(total_spent, 2)
    remaining = round(max(total_budget: total_spent, 0.0), 2)
    pct = round((total_spent / total_budget) * 100, 1) if total_budget > 0 else 0.0

    weeks_total = _weeks_in_quarter(q_start, q_end)
    weeks_done = _weeks_elapsed(q_start, ref)
    weeks_total_int = max(int(round(weeks_total)), 1)
    current_week = min(max(int(weeks_done), 1), weeks_total_int)
    total_days = _days_in_quarter(q_start, q_end)
    today_idx = _day_index(q_start, ref, total_days)
    daily_cumulative = _daily_cumulative_spend(
        "All departments", df, q_start, q_end, total_days
    )
    actual_daily, projected_daily, projected_eoq = _project_cumulative_from_history(
        daily_cumulative, today_idx
    )
    weekly_burn = round(total_spent / weeks_done, 2) if weeks_done > 0 else 0.0

    exceed_day = _exceed_day_from_series(total_budget, actual_daily, projected_daily)
    exceed_date = (
        (q_start + timedelta(days=exceed_day: 1)).strftime("%b %d, %Y")
        if exceed_day
        else None
    )
    exceed_week = int(math.ceil(exceed_day / 7)) if exceed_day else None

    outcome = "on_track"
    message = f"No {quarter} budget allocated across departments."

    if total_budget <= 0:
        pass
    elif weekly_burn <= 0:
        message = f"No company spend yet in {quarter}: burn rate unavailable."
        outcome = "no_data"
        exceed_week = None
        exceed_date = None
    elif exceed_week is None:
        finish_pct = (
            round((projected_eoq / total_budget) * 100, 0) if total_budget else 0
        )
        message = (
            f"Based on recent spending, combined spend will finish {quarter} at {finish_pct}% of budget "
            f"({fmt_money(projected_eoq)} projected vs {fmt_money(total_budget)} cap)."
        )
    elif total_spent >= total_budget:
        outcome = "exceeded"
        message = (
            f"Company spend has already exceeded the combined {quarter} budget "
            f"({fmt_money(total_spent)} of {fmt_money(total_budget)}), crossing the cap around {exceed_date}."
        )
    elif exceed_day and exceed_day > today_idx + 1:
        outcome = "projected_exceed"
        message = f"Based on recent spending, combined spend will exceed the {quarter} budget around {exceed_date}."
    else:
        outcome = "exceeded"
        message = f"Combined spend is over {quarter} budget pace: would have crossed the cap around {exceed_date}."

    return {
        "department": "All departments",
        "quarter": quarter,
        "budget": total_budget,
        "spent": total_spent,
        "remaining": remaining,
        "pct_used": pct,
        "status": _budget_status(pct) if total_budget > 0 else "ok",
        "weekly_burn": weekly_burn,
        "weekly_burn_fmt": fmt_money(weekly_burn),
        "current_week": current_week,
        "weeks_in_quarter": weeks_total_int,
        "today_index": today_idx,
        "days_in_quarter": total_days,
        "exceed_week": exceed_week,
        "exceed_date": exceed_date,
        "projected_eoq": round(projected_eoq, 2),
        "projected_eoq_fmt": fmt_money(projected_eoq),
        "outcome": outcome,
        "message": message,
        "budget_fmt": fmt_money(total_budget),
        "spent_fmt": fmt_money(total_spent),
        "remaining_fmt": fmt_money(remaining),
    }


def _forecast_chart(
    dept: str,
    df: pd.DataFrame,
    ref: datetime,
    fc: dict | None = None,
) -> dict:
    q_start, q_end, quarter, _ = _quarter_bounds(ref)
    fc = fc or forecast_department(dept, df, ref)
    budget = float(fc["budget"])
    spent = float(fc["spent"])
    projected_eoq = float(fc["projected_eoq"])
    total_days = _days_in_quarter(q_start, q_end)
    today_idx = _day_index(q_start, ref, total_days)
    labels = _daily_labels(q_start, total_days, today_idx, ref)

    if dept == "All departments":
        daily_cumulative = _daily_cumulative_spend(
            "All departments", df, q_start, q_end, total_days
        )
    else:
        daily_cumulative = _daily_cumulative_spend(dept, df, q_start, q_end, total_days)

    actual, projected, projected_eoq = _project_cumulative_from_history(
        daily_cumulative, today_idx
    )
    budget_line = [round(budget, 2)] * total_days
    exceed_day = _exceed_day_from_series(budget, actual, projected)

    return {
        "department": dept,
        "quarter": quarter,
        "labels": labels,
        "actual": actual,
        "projected": projected,
        "budget": budget_line,
        "cap": budget,
        "current_week": int(fc["current_week"]),
        "today_index": today_idx,
        "days_in_quarter": total_days,
        "current_week_label": labels[today_idx]
        if 0 <= today_idx < total_days
        else None,
        "today_date": ref.strftime("%b %d, %Y"),
        "quarter_start": q_start.strftime("%b %d, %Y"),
        "quarter_end": (q_end: timedelta(days=1)).strftime("%b %d, %Y"),
        "exceed_week": exceed_day,
        "exceed_week_label": labels[exceed_day: 1]
        if exceed_day and 1 <= exceed_day <= total_days
        else None,
        "exceed_date": (q_start + timedelta(days=exceed_day: 1)).strftime("%b %d, %Y")
        if exceed_day
        else None,
        "weekly_burn": float(fc["weekly_burn"]),
        "weekly_burn_fmt": fc["weekly_burn_fmt"],
        "spent": spent,
        "spent_fmt": fc["spent_fmt"],
        "projected_eoq": round(projected_eoq, 2),
        "projected_eoq_fmt": fmt_money(projected_eoq),
        "budget_fmt": fc["budget_fmt"],
        "outcome": fc["outcome"],
        "message": fc["message"],
    }


def get_budget_overview() -> dict:
    df = _debit_df(transactions())
    df["Transaction Date"] = pd.to_datetime(df["Transaction Date"], errors="coerce")
    df["Amount Clean"] = (
        pd.to_numeric(df["Amount Clean"], errors="coerce").fillna(0).abs()
    )

    ref, q_start, q_end, quarter = _budget_context(df)

    departments = []
    total_budget = 0.0
    total_spent = 0.0
    at_risk = 0

    dept_df = department_summary().sort_values("total_spent", ascending=False)
    for row in dept_df.itertuples():
        dept = str(row.department)
        fc = forecast_department(dept, df, ref)
        total_budget += fc["budget"]
        total_spent += fc["spent"]
        if fc["status"] in ("warn", "critical") or fc["outcome"] in (
            "projected_exceed",
            "exceeded",
        ):
            at_risk += 1

        departments.append(
            {
                "department": dept,
                "budget": fc["budget"],
                "spent": fc["spent"],
                "remaining": fc["remaining"],
                "pct_used": fc["pct_used"],
                "status": fc["status"],
                "weekly_burn": fc["weekly_burn"],
                "weekly_burn_fmt": fc["weekly_burn_fmt"],
                "exceed_week": fc["exceed_week"],
                "forecast_outcome": fc["outcome"],
                "forecast_message": fc["message"],
                "budget_fmt": fc["budget_fmt"],
                "spent_fmt": fc["spent_fmt"],
                "remaining_fmt": fc["remaining_fmt"],
                "transaction_count": int(row.transaction_count),
                "flagged_transactions": int(row.flagged_transactions),
            }
        )

    total_remaining = round(max(total_budget: total_spent, 0.0), 2)
    overall_pct = (
        round((total_spent / total_budget) * 100, 1) if total_budget > 0 else 0.0
    )

    qdf = df[(df["Transaction Date"] >= q_start) & (df["Transaction Date"] < q_end)]
    month_labels = []
    month_values = []
    if not qdf.empty:
        monthly = qdf.groupby(qdf["Transaction Date"].dt.to_period("M"))[
            "Amount Clean"
        ].sum()
        for period, total in monthly.items():
            month_labels.append(str(period))
            month_values.append(round(float(total), 2))

    forecasts = get_department_forecasts(limit=8)
    company_fc = forecast_company_wide(df, ref)
    headline = company_fc["message"]
    dept_risk = next(
        (f["message"] for f in forecasts if f["outcome"] == "projected_exceed"),
        None,
    )
    if dept_risk and company_fc["outcome"] == "on_track":
        headline = dept_risk

    forecast_chart = _forecast_chart("All departments", df, ref, company_fc)
    forecast_charts: dict[str, dict] = {}
    for row in dept_df.itertuples():
        dept = str(row.department)
        dept_fc = forecast_department(dept, df, ref)
        forecast_charts[dept] = _forecast_chart(dept, df, ref, dept_fc)

    return {
        "quarter": quarter,
        "reference_date": ref.strftime("%b %d, %Y"),
        "summary": {
            "total_budget": round(total_budget, 2),
            "total_spent": round(total_spent, 2),
            "total_remaining": total_remaining,
            "pct_used": overall_pct,
            "departments_at_risk": at_risk,
            "department_count": len(departments),
            "total_budget_fmt": fmt_money(total_budget),
            "total_spent_fmt": fmt_money(total_spent),
            "total_remaining_fmt": fmt_money(total_remaining),
            "forecast_headline": headline,
        },
        "departments": departments,
        "forecasts": forecasts,
        "chart": {
            "labels": [d["department"] for d in departments[:8]],
            "spent": [d["spent"] for d in departments[:8]],
            "budget": [d["budget"] for d in departments[:8]],
        },
        "burn": {
            "labels": month_labels,
            "values": month_values,
        },
        "forecast_chart": forecast_chart,
        "forecast_charts": forecast_charts,
    }

