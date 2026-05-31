"""CSV-backed query layer for Brim Guardian (uses company-scoped guardian_data)."""
from __future__ import annotations

import re
from datetime import datetime

import pandas as pd

from guardian_data import (
    department_summary,
    employee_row,
    employee_summary,
    flagged_transactions,
    transactions,
)


def _debit_df(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["Debit or Credit"].astype(str).str.lower() == "debit"].copy()


def _match_department(df: pd.DataFrame, department: str | None) -> pd.DataFrame:
    if not department:
        return df
    return df[df["Department"].astype(str).str.lower() == department.lower()]


def _match_category(df: pd.DataFrame, category: str | None) -> pd.DataFrame:
    if not category:
        return df
    cat = category.lower()
    cols = ["Transaction Category", "Merchant Info DBA Name"]
    mask = pd.Series(False, index=df.index)
    for col in cols:
        if col in df.columns:
            mask = mask | df[col].astype(str).str.lower().str.contains(cat, na=False)
    return df[mask]


def _match_quarter(df: pd.DataFrame, quarter: str | None) -> pd.DataFrame:
    if not quarter or "Transaction Date" not in df.columns:
        return df
    try:
        year, qpart = quarter.upper().split("-Q")
        qnum = int(qpart)
        start_month = (qnum - 1) * 3 + 1
        start = datetime(int(year), start_month, 1)
        if qnum == 4:
            end = datetime(int(year) + 1, 1, 1)
        else:
            end = datetime(int(year), start_month + 3, 1)
        return df[(df["Transaction Date"] >= start) & (df["Transaction Date"] < end)]
    except (ValueError, TypeError):
        return df


async def get_spending_by_department(
    department=None, category=None, quarter=None, start_date=None, end_date=None
):
    df = _debit_df(transactions())
    df = _match_department(df, department)
    df = _match_category(df, category)
    df = _match_quarter(df, quarter)

    grouped = (
        df.groupby(["Department", "Transaction Category"], dropna=False)["Amount Clean"]
        .agg(total="sum", count="count")
        .reset_index()
        .sort_values("total", ascending=False)
    )
    return [
        {
            "_id": {"department": row["Department"], "category": str(row["Transaction Category"])},
            "total": float(row["total"]),
            "count": int(row["count"]),
        }
        for _, row in grouped.iterrows()
    ]


async def get_top_vendors(limit=5, department=None):
    df = _debit_df(transactions())
    df = _match_department(df, department)
    grouped = (
        df.groupby("Merchant Info DBA Name")["Amount Clean"]
        .agg(total="sum", count="count")
        .reset_index()
        .sort_values("total", ascending=False)
        .head(limit)
    )
    return [
        {"_id": row["Merchant Info DBA Name"], "total": float(row["total"]), "count": int(row["count"])}
        for _, row in grouped.iterrows()
    ]


async def get_employee_credit_score(employee_id):
    row = employee_row(employee_id=employee_id)
    if row is None:
        return None
    return _employee_doc(row)


def _employee_doc(row):
    return {
        "employee_id": row["employee_id"],
        "employee_name": row["employee_name"],
        "department": row["department"],
        "credit_score": float(row["final_score"]),
        "final_score": float(row["final_score"]),
        "total_spent": float(row["total_spent"]),
        "flagged_transactions": int(row["flagged_transactions"]),
        "summary": row.get("one_sentence_summary", ""),
        "one_sentence_summary": row.get("one_sentence_summary", ""),
    }


class _EmployeeCollection:
    async def find_one(self, query, projection=None):
        emp_id = query.get("employee_id")
        if emp_id is not None:
            row = employee_row(employee_id=emp_id)
            if row is not None:
                return _employee_doc(row)

        name_query = query.get("employee_name", {})
        pattern = name_query.get("$regex", "")
        if not pattern:
            return None
        flags = re.I if name_query.get("$options") == "i" else 0
        for _, row in employee_summary().iterrows():
            if re.search(pattern, row["employee_name"], flags):
                return _employee_doc(row)
        return None


class _FakeDb:
    employees = _EmployeeCollection()


async def get_department_budget(department, quarter):
    from budget_data import _debit_df, _dept_spend_in_range, _quarter_bounds, _reference_date, quarterly_budget_cap

    df = _debit_df(transactions())
    ref = _reference_date(df)
    q_start, q_end, q_label, _ = _quarter_bounds(ref)
    quarter = quarter or q_label
    budget = quarterly_budget_cap(department, df, ref, quarter)
    spent = _dept_spend_in_range(df, department, q_start, q_end)

    dept_df = department_summary()
    row = dept_df[dept_df["department"].astype(str).str.lower() == department.lower()]
    txn_count = int(row.iloc[0]["transaction_count"]) if not row.empty else 0
    flagged_count = int(row.iloc[0]["flagged_transactions"]) if not row.empty else 0

    return {
        "department": department,
        "quarter": quarter,
        "total_budget": round(budget, 2),
        "spent": round(spent, 2),
        "remaining": round(max(budget - spent, 0.0), 2),
        "transaction_count": txn_count,
        "flagged_transactions": flagged_count,
    }


async def get_monthly_trend(department=None, months=6):
    df = _debit_df(transactions())
    df = _match_department(df, department)
    df = df.dropna(subset=["Transaction Date"])
    if df.empty:
        return []

    latest = df["Transaction Date"].max()
    start = latest - pd.DateOffset(months=months)
    df = df[df["Transaction Date"] >= start]
    df["year"] = df["Transaction Date"].dt.year
    df["month"] = df["Transaction Date"].dt.month

    grouped = (
        df.groupby(["year", "month", "Department"])["Amount Clean"]
        .sum()
        .reset_index()
        .sort_values(["year", "month"])
    )
    return [
        {
            "_id": {
                "year": int(row["year"]),
                "month": int(row["month"]),
                "department": row["Department"],
            },
            "total": float(row["Amount Clean"]),
        }
        for _, row in grouped.iterrows()
    ]


async def get_transactions_by_location(country=None, city=None, department=None, limit=50):
    df = _debit_df(transactions())
    if country:
        df = df[df["Merchant Country"].astype(str).str.contains(country, case=False, na=False)]
    if city:
        df = df[df["Merchant City"].astype(str).str.contains(city, case=False, na=False)]
    df = _match_department(df, department)
    df = df.sort_values("Amount Clean", ascending=False).head(limit)
    return [
        {
            "Employee Name": r["Employee Name"],
            "Department": r["Department"],
            "Merchant Info DBA Name": r["Merchant Info DBA Name"],
            "Merchant City": r["Merchant City"],
            "Merchant Country": r["Merchant Country"],
            "Amount Clean": float(r["Amount Clean"]),
            "Transaction Date": str(r["Transaction Date"].date()) if pd.notna(r["Transaction Date"]) else "",
        }
        for _, r in df.iterrows()
    ]


async def get_spending_by_country(department=None):
    df = _debit_df(transactions())
    df = _match_department(df, department)
    grouped = (
        df.groupby("Merchant Country")["Amount Clean"]
        .agg(total="sum", count="count")
        .reset_index()
        .sort_values("total", ascending=False)
    )
    return [
        {"_id": row["Merchant Country"], "total": float(row["total"]), "count": int(row["count"])}
        for _, row in grouped.iterrows()
    ]


def get_db():
    """Return a lightweight stand-in for MongoDB employee lookups."""
    return _FakeDb()


async def get_flags_for_employee(employee_id):
    df = flagged_transactions()
    rows = df[df["Employee ID"].astype(str) == str(employee_id)].head(20)
    return [
        {
            "Employee ID": r["Employee ID"],
            "Employee Name": r["Employee Name"],
            "Department": r["Department"],
            "Merchant Info DBA Name": r["Merchant Info DBA Name"],
            "Amount Clean": float(r["Amount Clean"]),
            "Transaction Date": str(r["Transaction Date"]),
            "flag_reason": r.get("flag_reason", ""),
            "risk_level": r.get("risk_level", ""),
        }
        for _, r in rows.iterrows()
    ]
