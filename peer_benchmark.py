"""Peer benchmarking — compare an employee's spend to department norms."""

from __future__ import annotations

from collections import defaultdict

from expense_data import format_money, load_expenses


def peer_benchmark_for_employee(name: str) -> dict | None:
    rows = load_expenses()
    emp_rows = [r for r in rows if r.get("employee") == name]
    if not emp_rows:
        return None

    dept = emp_rows[0].get("department") or "Unknown"
    dept_rows = [r for r in rows if r.get("department") == dept]
    dept_totals = defaultdict(float)
    for r in dept_rows:
        dept_totals[r.get("employee") or "—"] += float(r.get("amount") or 0)

    emp_total = sum(float(r.get("amount") or 0) for r in emp_rows)
    peer_amounts = sorted(dept_totals.values())
    dept_median = peer_amounts[len(peer_amounts) // 2] if peer_amounts else 0
    dept_avg = sum(peer_amounts) / len(peer_amounts) if peer_amounts else 0

    rank = 1 + sum(1 for v in peer_amounts if v > emp_total)
    percentile = int(100 * (1 - (rank - 1) / max(len(peer_amounts), 1)))

    cat_emp = defaultdict(float)
    cat_dept = defaultdict(float)
    for r in emp_rows:
        cat_emp[r.get("category") or "Other"] += float(r.get("amount") or 0)
    for r in dept_rows:
        cat_dept[r.get("category") or "Other"] += float(r.get("amount") or 0)

    n_peers = len(dept_totals)
    cat_compare = []
    for cat, amt in sorted(cat_emp.items(), key=lambda x: -x[1])[:5]:
        dept_cat_avg = cat_dept[cat] / max(n_peers, 1)
        delta = amt - dept_cat_avg
        cat_compare.append({
            "category": cat,
            "employee_fmt": format_money(amt),
            "dept_avg_fmt": format_money(dept_cat_avg),
            "delta_fmt": format_money(abs(delta)),
            "direction": "above" if delta > 0 else "below" if delta < 0 else "on par",
        })

    vs_median = emp_total - dept_median
    summary = (
        f"{name} spent {format_money(emp_total)} — "
        f"{'above' if vs_median > 0 else 'below' if vs_median < 0 else 'at'} "
        f"the {dept} median ({format_money(dept_median)})."
    )

    return {
        "employee": name,
        "department": dept,
        "employee_total_fmt": format_money(emp_total),
        "dept_median_fmt": format_money(dept_median),
        "dept_average_fmt": format_money(dept_avg),
        "peer_count": n_peers,
        "spend_rank": rank,
        "spend_percentile": percentile,
        "vs_median_fmt": format_money(abs(vs_median)),
        "vs_median_direction": "above" if vs_median > 0 else "below" if vs_median < 0 else "on par",
        "category_compare": cat_compare,
        "summary": summary,
    }
