"""Flask route blueprints for CashFlux."""

from __future__ import annotations


def register_blueprints(app):
    from routes.dashboard import dashboard_bp
    from routes.chat import chat_bp
    from routes.budget import budget_bp
    from routes.employees import employees_bp
    from routes.receipts import receipts_bp
    from routes.review import review_bp
    from routes.proposals import proposals_bp
    from routes.reports import reports_bp
    from routes.policy import policy_bp
    from routes.fraud import fraud_bp
    from routes.voice import voice_bp
    from routes.exports import exports_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(budget_bp)
    app.register_blueprint(employees_bp)
    app.register_blueprint(receipts_bp)
    app.register_blueprint(review_bp)
    app.register_blueprint(proposals_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(policy_bp)
    app.register_blueprint(fraud_bp)
    app.register_blueprint(voice_bp)
    app.register_blueprint(exports_bp)
