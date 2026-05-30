"""
Load scored CSV data into MongoDB, replacing all existing collections.
Run from the brim-guardian root: python -m db.load_from_csv
"""
import os
import math
from pathlib import Path
import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(__file__).parent.parent / "data"
client = MongoClient(os.environ["MONGODB_URI"])
db = client[os.getenv("MONGODB_DB_NAME", "brim_guardian")]


def clean(val):
    """Convert NaN/inf to None so MongoDB accepts it."""
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return None
    return val


def row_to_doc(row):
    return {k: clean(v) for k, v in row.items()}


def load_transactions():
    df = pd.read_csv(DATA_DIR / "transactions_scored.csv")
    docs = []
    for i, row in df.iterrows():
        doc = row_to_doc(row.to_dict())
        doc["transaction_id"] = f"txn{i:05d}"
        docs.append(doc)

    db.transactions.drop()
    db.transactions.insert_many(docs)
    db.transactions.create_index([("Department", 1), ("Transaction Date", -1)])
    db.transactions.create_index([("Employee ID", 1)])
    print(f"transactions: {len(docs)} docs inserted")


def load_employees():
    df = pd.read_csv(DATA_DIR / "employee_scores_summary.csv")
    docs = [row_to_doc(row.to_dict()) for _, row in df.iterrows()]

    db.employees.drop()
    db.employees.insert_many(docs)
    db.employees.create_index([("employee_id", 1)], unique=True)
    print(f"employees: {len(docs)} docs inserted")


def load_flags():
    df = pd.read_csv(DATA_DIR / "flagged_transactions.csv")
    docs = []
    for i, row in df.iterrows():
        doc = row_to_doc(row.to_dict())
        doc["flag_id"] = f"flg{i:05d}"
        docs.append(doc)

    db.flags.drop()
    if docs:
        db.flags.insert_many(docs)
        db.flags.create_index([("Employee ID", 1)])
    print(f"flags: {len(docs)} docs inserted")


def load_departments():
    df = pd.read_csv(DATA_DIR / "department_summary.csv")
    docs = [row_to_doc(row.to_dict()) for _, row in df.iterrows()]

    db.departments.drop()
    db.departments.insert_many(docs)
    print(f"departments: {len(docs)} docs inserted")


if __name__ == "__main__":
    print("Loading CSV data into MongoDB...")
    load_transactions()
    load_employees()
    load_flags()
    load_departments()
    print("Done.")
    client.close()
