"""Seed MongoDB with fake data for dev/demo. Run: python -m db.seed"""
import asyncio, random
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()
from db.connection import get_db

DEPARTMENTS = ["Marketing", "Engineering", "Sales", "HR", "Finance"]
CATEGORIES = ["meal", "software", "travel", "equipment", "conference"]
VENDORS = {
    "meal": ["Chipotle", "The Keg", "Uber Eats", "DoorDash", "Local Bistro"],
    "software": ["AWS", "Salesforce", "Slack", "Figma", "GitHub"],
    "travel": ["Air Canada", "United Airlines", "Airbnb", "Marriott", "Uber"],
    "equipment": ["Apple", "Dell", "BestBuy", "Staples", "B&H Photo"],
    "conference": ["Eventbrite", "SaaStr", "HubSpot Inbound", "AWS re:Invent", "Cvent"],
}
CITIES = {
    "Marketing": ("Montreal", "Canada"),
    "Engineering": ("Toronto", "Canada"),
    "Sales": ("New York", "USA"),
    "HR": ("Montreal", "Canada"),
    "Finance": ("Montreal", "Canada"),
}
EMPLOYEES = [
    {"employee_id": "emp001", "name": "Sarah Chen", "department": "Marketing"},
    {"employee_id": "emp002", "name": "John Perez", "department": "Sales"},
    {"employee_id": "emp003", "name": "Priya Patel", "department": "Engineering"},
    {"employee_id": "emp004", "name": "Lucas Martin", "department": "HR"},
    {"employee_id": "emp005", "name": "Emma Wilson", "department": "Finance"},
    {"employee_id": "emp006", "name": "David Kim", "department": "Marketing"},
    {"employee_id": "emp007", "name": "Aisha Brown", "department": "Engineering"},
    {"employee_id": "emp008", "name": "Carlos Lopez", "department": "Sales"},
]


async def seed():
    db = get_db()
    print("Dropping existing collections...")
    for col in ["transactions", "employees", "budgets", "flags"]:
        await db[col].drop()

    # Employees
    emp_docs = []
    for e in EMPLOYEES:
        city, country = CITIES[e["department"]]
        violations = random.randint(0, 4)
        emp_docs.append({
            **e, "home_city": city, "home_country": country,
            "credit_score": max(0.0, 100.0 - violations * 12),
            "violation_count": violations,
            "total_spent_mtd": round(random.uniform(200, 3000), 2),
        })
    await db.employees.insert_many(emp_docs)
    print(f"Inserted {len(emp_docs)} employees")

    # Transactions + flags
    now = datetime.utcnow()
    txns, flags = [], []
    for i in range(300):
        emp = random.choice(EMPLOYEES)
        cat = random.choice(CATEGORIES)
        vendor = random.choice(VENDORS[cat])
        txn_date = now - timedelta(days=random.randint(0, 180))
        amount = round(random.uniform(20, 1500), 2)
        city, country = CITIES[emp["department"]]
        if random.random() < 0.05:
            city, country = "Las Vegas", "USA"

        txn = {
            "transaction_id": f"txn{i:04d}", "employee_id": emp["employee_id"],
            "employee_name": emp["name"], "department": emp["department"],
            "vendor": vendor, "amount": amount, "category": cat,
            "date": txn_date, "city": city, "country": country,
            "description": f"{cat.title()} at {vendor}",
            "approved": random.choice([True, True, True, None]),
        }
        txns.append(txn)

        if cat == "meal" and amount > 75:
            flags.append({
                "flag_id": f"flg{len(flags):04d}", "transaction_id": txn["transaction_id"],
                "employee_id": emp["employee_id"], "flag_type": "policy_violation",
                "severity": "medium" if amount < 200 else "high",
                "description": f"Meal ${amount:.2f} exceeds $75/person policy",
                "created_at": txn_date, "resolved": random.random() < 0.4,
            })
        if city == "Las Vegas":
            flags.append({
                "flag_id": f"flg{len(flags):04d}", "transaction_id": txn["transaction_id"],
                "employee_id": emp["employee_id"], "flag_type": "geofencing",
                "severity": "high",
                "description": f"{emp['name']} ({CITIES[emp['department']][0]}-based) charged in Las Vegas",
                "created_at": txn_date, "resolved": False,
            })

    await db.transactions.insert_many(txns)
    if flags:
        await db.flags.insert_many(flags)
    print(f"Inserted {len(txns)} transactions, {len(flags)} flags")

    # Budgets
    budget_docs = [
        {"department": d, "quarter": "2025-Q2",
         "total_budget": (t := round(random.uniform(15000, 60000), 2)),
         "spent": (s := round(t * random.uniform(0.3, 0.9), 2)),
         "remaining": round(t - s, 2)}
        for d in DEPARTMENTS
    ]
    await db.budgets.insert_many(budget_docs)
    print(f"Inserted {len(budget_docs)} budgets")

    # Indexes
    await db.transactions.create_index([("department", 1), ("date", -1)])
    await db.transactions.create_index([("employee_id", 1)])
    await db.employees.create_index([("employee_id", 1)], unique=True)
    await db.flags.create_index([("employee_id", 1), ("resolved", 1)])
    print("Done.")


if __name__ == "__main__":
    asyncio.run(seed())
