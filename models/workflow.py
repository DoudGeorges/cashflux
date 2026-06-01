from __future__ import annotations

"""WorkflowDecision model for approval / denial records."""

from datetime import datetime

from core.extensions import db


class WorkflowDecision(db.Model):
    __tablename__ = "workflow_decision"
    id = db.Column(db.Integer, primary_key=True)
    item_key = db.Column(db.String(300), unique=True, nullable=False)
    item_type = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    decided_at = db.Column(db.DateTime, default=datetime.now)
    note = db.Column(db.Text)

