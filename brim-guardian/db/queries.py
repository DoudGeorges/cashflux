"""MongoDB queries using the actual field names from the loaded CSV data."""
from datetime import datetime, timedelta
from db.connection import get_db


async def get_spending_by_department(department=None, category=None, quarter=None, start_date=None, end_date=None):
    db = get_db()
    match = {"Debit or Credit": "Debit"}

    if department:
        match["Department"] = department
    if category:
        match["Transaction Category"] = category
    if quarter:
        year, q = quarter.split("-Q")
        q_start_month = (int(q) - 1) * 3 + 1
        match["Transaction Date"] = {
            "$gte": f"{year}-{q_start_month:02d}-01",
        }
    elif start_date or end_date:
        date_filter = {}
        if start_date:
            date_filter["$gte"] = str(start_date)
        if end_date:
            date_filter["$lte"] = str(end_date)
        match["Transaction Date"] = date_filter

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": {"department": "$Department", "category": "$Transaction Category"},
            "total": {"$sum": "$Amount Clean"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"total": -1}},
    ]
    return await db.transactions.aggregate(pipeline).to_list(None)


async def get_top_vendors(limit=5, department=None):
    db = get_db()
    match = {"Debit or Credit": "Debit"}
    if department:
        match["Department"] = department

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$Merchant Info DBA Name",
            "total": {"$sum": "$Amount Clean"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"total": -1}},
        {"$limit": limit},
    ]
    return await db.transactions.aggregate(pipeline).to_list(None)


async def get_employee_credit_score(employee_id):
    db = get_db()
    return await db.employees.find_one({"employee_id": employee_id}, {"_id": 0})


async def get_flags_for_employee(employee_id):
    db = get_db()
    return await db.flags.find(
        {"Employee ID": employee_id}, {"_id": 0}
    ).sort("Transaction Date", -1).to_list(None)


async def get_department_budget(department, quarter):
    db = get_db()
    return await db.departments.find_one({"department": department}, {"_id": 0})


async def get_monthly_trend(department=None, months=6):
    db = get_db()
    match = {"Debit or Credit": "Debit"}
    if department:
        match["Department"] = department

    pipeline = [
        {"$match": match},
        {"$addFields": {
            "date_parsed": {"$dateFromString": {"dateString": "$Transaction Date", "onError": None}}
        }},
        {"$match": {"date_parsed": {"$ne": None}}},
        {"$group": {
            "_id": {
                "year": {"$year": "$date_parsed"},
                "month": {"$month": "$date_parsed"},
                "department": "$Department",
            },
            "total": {"$sum": "$Amount Clean"},
        }},
        {"$sort": {"_id.year": 1, "_id.month": 1}},
    ]
    return await db.transactions.aggregate(pipeline).to_list(None)


async def get_transactions_by_location(country=None, city=None, department=None, limit=50):
    db = get_db()
    match = {"Debit or Credit": "Debit"}
    if country:
        match["Merchant Country"] = {"$regex": country, "$options": "i"}
    if city:
        match["Merchant City"] = {"$regex": city, "$options": "i"}
    if department:
        match["Department"] = department

    cursor = db.transactions.find(match, {
        "_id": 0,
        "Employee Name": 1,
        "Department": 1,
        "Merchant Info DBA Name": 1,
        "Merchant City": 1,
        "Merchant Country": 1,
        "Amount Clean": 1,
        "Transaction Date": 1,
    }).sort("Amount Clean", -1).limit(limit)

    return await cursor.to_list(None)


async def get_spending_by_country(department=None):
    db = get_db()
    match = {"Debit or Credit": "Debit"}
    if department:
        match["Department"] = department

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$Merchant Country",
            "total": {"$sum": "$Amount Clean"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"total": -1}},
    ]
    return await db.transactions.aggregate(pipeline).to_list(None)
