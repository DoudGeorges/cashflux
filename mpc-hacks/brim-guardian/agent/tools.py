"""
Tool definitions for the Gemini agent.
Each entry in TOOL_DECLARATIONS describes a function to Gemini.
dispatch() executes the real logic and returns a JSON-serialisable result.
"""
import asyncio
import json
from typing import Any

from db import queries
from charts import generator as chart_gen


TOOL_DECLARATIONS = [
    {
        "name": "get_spending_by_department",
        "description": (
            "Query total spending grouped by department and/or category. "
            "Use for questions about spending in a department, category, or time period."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "department": {"type": "string", "description": "Filter to one department (e.g. 'Marketing'). Omit for all."},
                "category": {"type": "string", "description": "Spend category: 'software', 'travel', 'meal', 'equipment', 'conference'."},
                "quarter": {"type": "string", "description": "Format YYYY-QN (e.g. '2025-Q2'). Omit for all time."},
            },
        },
    },
    {
        "name": "get_top_vendors",
        "description": "Return the top N vendors by total spend, optionally filtered by department.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "How many vendors (default 5)."},
                "department": {"type": "string", "description": "Restrict to one department."},
            },
        },
    },
    {
        "name": "get_employee_credit_score",
        "description": (
            "Get the spending credit score and violation details for an employee. "
            "Score starts at 100 and drops per policy violation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "employee_id": {"type": "string"},
                "employee_name": {"type": "string", "description": "Search by name if ID is unknown."},
            },
        },
    },
    {
        "name": "get_monthly_trend",
        "description": "Month-by-month spend totals for trend analysis.",
        "parameters": {
            "type": "object",
            "properties": {
                "department": {"type": "string"},
                "months": {"type": "integer", "description": "How many past months (default 6)."},
            },
        },
    },
    {
        "name": "get_department_budget",
        "description": "Get budget total, amount spent, and remaining for a department in a quarter.",
        "parameters": {
            "type": "object",
            "properties": {
                "department": {"type": "string"},
                "quarter": {"type": "string", "description": "e.g. '2025-Q2'"},
            },
            "required": ["department", "quarter"],
        },
    },
    {
        "name": "generate_bar_chart",
        "description": "Generate a bar chart PNG from labels and values. Call AFTER a data query.",
        "parameters": {
            "type": "object",
            "properties": {
                "labels": {"type": "array", "items": {"type": "string"}},
                "values": {"type": "array", "items": {"type": "number"}},
                "title": {"type": "string"},
                "xlabel": {"type": "string"},
                "ylabel": {"type": "string"},
            },
            "required": ["labels", "values", "title"],
        },
    },
    {
        "name": "generate_comparison_chart",
        "description": "Grouped bar chart comparing multiple departments or categories side-by-side.",
        "parameters": {
            "type": "object",
            "properties": {
                "groups": {"type": "array", "items": {"type": "string"}, "description": "X-axis labels (months or categories)."},
                "series": {"type": "object", "description": "{'Marketing': [100, 200], 'Engineering': [150, 180]}"},
                "title": {"type": "string"},
            },
            "required": ["groups", "series", "title"],
        },
    },
    {
        "name": "generate_ranked_table",
        "description": "Generate a ranked table chart (e.g. top vendors). Pass a list of row dicts.",
        "parameters": {
            "type": "object",
            "properties": {
                "rows": {"type": "array", "items": {"type": "object"}},
                "title": {"type": "string"},
            },
            "required": ["rows"],
        },
    },
    {
        "name": "get_transactions_by_location",
        "description": "Find transactions that happened in a specific country or city. Use for geofencing questions or location-based spending analysis.",
        "parameters": {
            "type": "object",
            "properties": {
                "country": {"type": "string", "description": "Country name or code (e.g. 'USA', 'CAN')."},
                "city": {"type": "string", "description": "City name (e.g. 'Las Vegas')."},
                "department": {"type": "string", "description": "Optionally filter by department."},
                "limit": {"type": "integer", "description": "Max transactions to return (default 50)."},
            },
        },
    },
    {
        "name": "get_spending_by_country",
        "description": "Show total spending grouped by country. Useful for seeing where the company spends money geographically.",
        "parameters": {
            "type": "object",
            "properties": {
                "department": {"type": "string", "description": "Optionally filter by department."},
            },
        },
    },
]


async def dispatch(tool_name: str, args: dict) -> Any:
    """Run the requested tool and return a JSON-serialisable result."""
    match tool_name:

        case "get_spending_by_department":
            rows = await queries.get_spending_by_department(
                department=args.get("department"),
                category=args.get("category"),
                quarter=args.get("quarter"),
            )
            return [
                {"department": r["_id"]["department"], "category": r["_id"]["category"],
                 "total": round(r["total"], 2), "count": r["count"]}
                for r in rows
            ]

        case "get_top_vendors":
            rows = await queries.get_top_vendors(
                limit=args.get("limit", 5),
                department=args.get("department"),
            )
            return [{"vendor": r["_id"], "total": round(r["total"], 2), "transactions": r["count"]} for r in rows]

        case "get_employee_credit_score":
            emp_id = args.get("employee_id")
            name = args.get("employee_name")
            if emp_id:
                emp = await queries.get_employee_credit_score(emp_id)
            else:
                db = queries.get_db()
                emp = await db.employees.find_one(
                    {"employee_name": {"$regex": name, "$options": "i"}}, {"_id": 0}
                )
            if not emp:
                return {"error": "Employee not found"}
            flags = await queries.get_flags_for_employee(emp["employee_id"])
            return {**emp, "active_flags": len(flags)}

        case "get_monthly_trend":
            rows = await queries.get_monthly_trend(
                department=args.get("department"),
                months=args.get("months", 6),
            )
            return [
                {"month": f"{r['_id']['year']}-{r['_id']['month']:02d}",
                 "department": r["_id"]["department"],
                 "total": round(r["total"], 2)}
                for r in rows
            ]

        case "get_department_budget":
            budget = await queries.get_department_budget(args["department"], args["quarter"])
            return budget or {"error": "Budget not found"}

        case "generate_bar_chart":
            path = await asyncio.to_thread(
                chart_gen.bar_chart,
                args["labels"], args["values"],
                title=args.get("title", ""),
                xlabel=args.get("xlabel", ""),
                ylabel=args.get("ylabel", "Amount (USD)"),
            )
            return {"chart_path": path}

        case "generate_comparison_chart":
            path = await asyncio.to_thread(
                chart_gen.comparison_bar_chart,
                args["groups"], args["series"],
                title=args.get("title", ""),
            )
            return {"chart_path": path}

        case "generate_ranked_table":
            path = await asyncio.to_thread(
                chart_gen.ranked_table_chart,
                args["rows"],
                title=args.get("title", "Top Vendors"),
            )
            return {"chart_path": path}

        case "get_transactions_by_location":
            rows = await queries.get_transactions_by_location(
                country=args.get("country"),
                city=args.get("city"),
                department=args.get("department"),
                limit=args.get("limit", 50),
            )
            return rows

        case "get_spending_by_country":
            rows = await queries.get_spending_by_country(department=args.get("department"))
            return [{"country": r["_id"], "total": round(r["total"], 2), "transactions": r["count"]} for r in rows]

        case _:
            return {"error": f"Unknown tool: {tool_name}"}
