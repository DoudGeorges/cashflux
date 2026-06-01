from __future__ import annotations

"""ProjectProposal model for project budget proposals."""

from datetime import datetime

from core.extensions import db


class ProjectProposal(db.Model):
    __tablename__ = "project_proposal"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )
    company_id = db.Column(
        db.Integer, db.ForeignKey("company.id"), nullable=False, index=True
    )
    employee_name = db.Column(db.String(120), nullable=False)
    department = db.Column(db.String(120), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    requested_amount = db.Column(db.Float, nullable=False)
    quarter = db.Column(db.String(32))
    status = db.Column(db.String(20), nullable=False, default="pending")
    submitted_at = db.Column(db.DateTime, default=datetime.now)
    decided_at = db.Column(db.DateTime)
    decided_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    decision_note = db.Column(db.Text)
    budget_snapshot = db.Column(db.Text)
    budget_source = db.Column(db.String(32), nullable=False, default="existing")
    colleagues = db.Column(db.Text)  # JSON list of employee names on this project

