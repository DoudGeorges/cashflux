from __future__ import annotations

"""EmployeeTripReport model for employee trip report submissions."""

from datetime import datetime

from core.extensions import db


class EmployeeTripReport(db.Model):
    __tablename__ = "employee_trip_report"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )
    company_id = db.Column(
        db.Integer, db.ForeignKey("company.id"), nullable=False, index=True
    )
    employee_name = db.Column(db.String(120), nullable=False)
    department = db.Column(db.String(120), nullable=False)
    trip_name = db.Column(db.String(200), nullable=False)
    purpose = db.Column(db.Text)
    transaction_keys = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending_cfo")
    submitted_at = db.Column(db.DateTime, default=datetime.now)
    decided_at = db.Column(db.DateTime)
    decided_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    decision_note = db.Column(db.Text)
    spending_purpose = db.Column(db.String(20), nullable=False, default="personal")
    project_id = db.Column(db.Integer, db.ForeignKey("project_proposal.id"))

