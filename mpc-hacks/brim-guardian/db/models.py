"""
Pydantic models that mirror MongoDB documents.

Collections
-----------
transactions  — one doc per expense charge
employees     — employee profile + computed credit score
flags         — policy violations / fraud alerts
budgets       — department quarterly budgets
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Transaction(BaseModel):
    transaction_id: str
    employee_id: str
    employee_name: str
    department: str
    vendor: str
    amount: float
    category: str
    date: datetime
    city: str
    country: str
    description: Optional[str] = None
    receipt_url: Optional[str] = None
    approved: Optional[bool] = None


class Employee(BaseModel):
    employee_id: str
    name: str
    department: str
    home_city: str
    home_country: str
    credit_score: float = Field(100.0, ge=0, le=100)
    violation_count: int = 0
    total_spent_mtd: float = 0.0


class Flag(BaseModel):
    flag_id: str
    transaction_id: str
    employee_id: str
    flag_type: str    # "policy_violation" | "geofencing" | "split_purchase" | "fraud"
    severity: str     # "low" | "medium" | "high"
    description: str
    created_at: datetime
    resolved: bool = False


class Budget(BaseModel):
    department: str
    quarter: str
    total_budget: float
    spent: float
    remaining: float
