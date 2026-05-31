"""Vendor consolidation analysis — find duplicate vendor categories and estimate savings."""

from __future__ import annotations

import re
from collections import defaultdict

from expense_data import format_money, load_expenses, scoped_expenses

CONSOLIDATION_GROUPS = {
    "coffee": {
        "label": "Coffee & cafés",
        "hints": ("starbucks", "tim hortons", "coffee", "cafe", "café", "espresso", "second cup"),
        "savings_rate": 0.12,
    },
    "cloud_software": {
        "label": "Cloud & software",
        "hints": ("aws", "azure", "google cloud", "github", "atlassian", "slack", "zoom", "microsoft 365", "adobe"),
        "savings_rate": 0.15,
    },
    "fuel": {
        "label": "Fuel & gas",
        "hints": ("esso", "shell", "petro", "ultramar", "husky", "fuel", "gas bar"),
        "savings_rate": 0.08,
    },
    "office_supply": {
        "label": "Office supplies",
        "hints": ("staples", "office depot", "grand & toy", "amazon"),
        "savings_rate": 0.10,
    },
    "telecom": {
        "label": "Telecom",
        "hints": ("bell", "rogers", "telus", "fido", "koodo", "mobile", "wireless"),
        "savings_rate": 0.11,
    },
}


def _normalize_vendor(name: str) -> str:
    return re.sub(r"\s+", " ", str(name or "").strip())


def _classify_vendor(vendor: str) -> str | None:
    low = vendor.lower()
    for key, meta in CONSOLIDATION_GROUPS.items():
        if any(h in low for h in meta["hints"]):
            return key
    return None


def analyze_vendor_consolidation(*, employee_name: str | None = None, min_vendors: int = 2) -> dict:
    rows = scoped_expenses(employee_name)
    by_group: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for r in rows:
        vendor = _normalize_vendor(r.get("vendor") or "")
        if not vendor:
            continue
        group = _classify_vendor(vendor)
        if not group:
            continue
        by_group[group][vendor] += float(r.get("amount") or 0)

    opportunities = []
    total_savings = 0.0

    for group_key, vendors in by_group.items():
        if len(vendors) < min_vendors:
            continue
        meta = CONSOLIDATION_GROUPS[group_key]
        ranked = sorted(vendors.items(), key=lambda x: -x[1])
        group_spend = sum(vendors.values())
        savings = round(group_spend * meta["savings_rate"], 2)
        total_savings += savings
        opportunities.append({
            "group": group_key,
            "label": meta["label"],
            "vendor_count": len(vendors),
            "vendors": [
                {"name": name, "spend": round(amt, 2), "spend_fmt": format_money(amt)}
                for name, amt in ranked
            ],
            "total_spend": round(group_spend, 2),
            "total_spend_fmt": format_money(group_spend),
            "estimated_savings": savings,
            "estimated_savings_fmt": format_money(savings),
            "savings_rate_pct": int(meta["savings_rate"] * 100),
            "recommendation": (
                f"You're paying {len(vendors)} different {meta['label'].lower()} vendors "
                f"({format_money(group_spend)} total). Consolidating to one preferred vendor "
                f"could save about {format_money(savings)}/year at ~{int(meta['savings_rate'] * 100)}% volume discount."
            ),
        })

    opportunities.sort(key=lambda x: x["estimated_savings"], reverse=True)

    headline = (
        f"{len(opportunities)} consolidation opportunit{'y' if len(opportunities) == 1 else 'ies'} "
        f"— estimated {format_money(total_savings)} in annual savings."
        if opportunities
        else "No multi-vendor consolidation opportunities detected in categorized spend."
    )

    return {
        "opportunities": opportunities,
        "opportunity_count": len(opportunities),
        "total_estimated_savings": round(total_savings, 2),
        "total_estimated_savings_fmt": format_money(total_savings),
        "headline": headline,
        "scope": "personal" if employee_name else "company",
    }
