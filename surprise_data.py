"""Hidden Spending Oracle — whimsical insights from real expense data."""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from datetime import datetime

from expense_data import format_money, load_expenses, scoped_expenses

_COFFEE_HINTS = ("starbucks", "coffee", "tim hortons", "cafe", "espresso")
_FUEL_CATEGORIES = ("fuel", "gas", "petrol")
_MEAL_CATEGORIES = ("meal", "restaurant", "food", "entertainment", "dining", "coffee")

_PERSONALITIES = {
    "meals": ("The Connoisseur", "fa-utensils", "Your spend speaks fluent menu French."),
    "fuel": ("The Road Warrior", "fa-road", "Mileage is a lifestyle, not a line item."),
    "software": ("The Stack Builder", "fa-code", "Every subscription is a brick in the tower."),
    "travel": ("The Nomad", "fa-plane", "Home is where the corporate card is."),
    "lodging": ("The Suite Life", "fa-hotel", "Turn-down service, turn-up analytics."),
    "telecom": ("The Signal Keeper", "fa-signal", "Connected everywhere, reconciled eventually."),
    "default": ("The Curious CFO", "fa-wand-magic-sparkles", "The numbers whisper secrets to those who listen."),
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
        return [{
            "emoji": "🌱",
            "headline": "A blank ledger is full of possibility",
            "body": "No purchases yet — the oracle sees infinite potential (and zero receipts).",
        }]

    total = sum(float(r.get("amount") or 0) for r in rows)
    pool.append({
        "emoji": "💰",
        "headline": f"{format_money(total)} on the move",
        "body": (
            f"That's enough $20 bills to stack about {max(int(total / 20 * 0.003), 1)} metres high — "
            "a very expensive ruler."
        ),
    })

    vendors = Counter((r.get("vendor") or "Unknown").strip() for r in rows)
    if vendors:
        top_vendor, top_count = vendors.most_common(1)[0]
        pool.append({
            "emoji": "🏪",
            "headline": f"{top_vendor} knows your name",
            "body": f"You've stopped by {top_count} time{'s' if top_count != 1 else ''}. Loyalty program: unlocked.",
        })

    coffee_spend = sum(
        float(r.get("amount") or 0)
        for r in rows
        if any(h in (r.get("vendor") or "").lower() for h in _COFFEE_HINTS)
        or "coffee" in (r.get("category") or "").lower()
    )
    if coffee_spend >= 50:
        cups = max(int(coffee_spend / 6), 1)
        pool.append({
            "emoji": "☕",
            "headline": f"{format_money(coffee_spend)} of liquid motivation",
            "body": f"Roughly {cups} lattes worth of caffeine diplomacy. The oracle does not judge.",
        })

    by_dow: dict[int, float] = defaultdict(float)
    for r in rows:
        dt = r.get("date")
        if dt:
            by_dow[dt.weekday() if hasattr(dt, "weekday") else datetime.fromisoformat(str(dt)[:10]).weekday()] += float(
                r.get("amount") or 0
            )
    if by_dow:
        names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        busiest = max(by_dow.items(), key=lambda x: x[1])
        quietest = min(by_dow.items(), key=lambda x: x[1])
        if quietest[1] > 0:
            pct = int((busiest[1] / quietest[1] - 1) * 100)
            pool.append({
                "emoji": "📅",
                "headline": f"{names[busiest[0]]} is spend day",
                "body": f"{pct}% more out the door than quiet {names[quietest[0]]}. Calendar blocked for commerce.",
            })

    cities = Counter((r.get("city") or "").strip() for r in rows if (r.get("city") or "").strip())
    if cities:
        city, count = cities.most_common(1)[0]
        pool.append({
            "emoji": "🗺️",
            "headline": f"{city} is your money magnet",
            "body": f"{count} purchases mapped there. The dots on the map aren't decoration — they're you.",
        })

    big = max(rows, key=lambda r: float(r.get("amount") or 0))
    pool.append({
        "emoji": "🎯",
        "headline": f"Peak purchase: {format_money(big.get('amount'))}",
        "body": f"{big.get('vendor', 'Unknown vendor')} on {big.get('date').date().isoformat() if big.get('date') else 'record'}. "
        + ("Your personal Everest." if personal else "Company legend material."),
    })

    if not personal:
        dept_meals: dict[str, float] = defaultdict(float)
        for r in rows:
            cat = (r.get("category") or "").lower()
            if any(k in cat for k in _MEAL_CATEGORIES):
                dept_meals[r.get("department") or "Unknown"] += float(r.get("amount") or 0)
        if dept_meals:
            dept, amt = max(dept_meals.items(), key=lambda x: x[1])
            pool.append({
                "emoji": "🍽️",
                "headline": f"{dept} runs on meals",
                "body": f"{format_money(amt)} on food & entertainment. The oracle smells reservations.",
            })

    flagged = sum(1 for r in rows if r.get("flagged") == "yes")
    if flagged:
        pool.append({
            "emoji": "🚩",
            "headline": f"{flagged} flagged purchase{'s' if flagged != 1 else ''}",
            "body": "Even the oracle raises an eyebrow sometimes. Review queue material.",
        })

    return pool


def build_spending_oracle(*, employee_name: str | None = None) -> dict:
    """Return personality, insights, sparkline, and flair for the surprise modal."""
    rows = scoped_expenses(employee_name)
    personal = bool(employee_name)
    personality = _pick_personality(rows)
    pool = _build_insight_pool(rows, personal=personal)
    rng = random.Random(hash((employee_name or "company", datetime.now().strftime("%Y-%m-%d"))))
    insights = rng.sample(pool, min(3, len(pool)))
    spark = _sparkline_weeks(rows)

    tx_count = len(rows)
    employee_count = len({r.get("employee") for r in load_expenses() if r.get("employee")})

    return {
        "personality": personality,
        "insights": insights,
        "sparkline": spark,
        "meta": {
            "transaction_count": tx_count,
            "scope": "personal" if personal else "company",
            "employee_count": employee_count if not personal else None,
        },
        "flair": rng.choice([
            "The ledger never lies — but it occasionally jokes.",
            "Friday consulted the spreadsheets in a séance.",
            "Derived from real transactions. Magic is just good grouping.",
            "Your CFO would either laugh or cry. Possibly both.",
        ]),
    }
