from __future__ import annotations


from flask import Flask, jsonify, request
from dotenv import load_dotenv

load_dotenv()

from config import Config  # noqa: E402
from core.extensions import db  # noqa: E402


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    app.secret_key = Config.SECRET_KEY
    app.config["PERMANENT_SESSION_LIFETIME"] = Config.PERMANENT_SESSION_LIFETIME

    # Initialise extensions
    db.init_app(app)

    # Company data bootstrap (runs once at startup)
    from services.company import (
        DEFAULT_COMPANY_SLUG,
        migrate_legacy_data_to_default_company,
        set_company_context,
    )

    migrate_legacy_data_to_default_company()
    set_company_context(0, DEFAULT_COMPANY_SLUG)

    from services.guardian import clear_cache

    clear_cache()

    # Auth setup
    from core.auth import (
        bind as bind_auth,
        register_auth_routes,
        get_current_user,
        can_see_all,
    )

    User, Company = bind_auth(db)
    register_auth_routes(app)

    # Error handlers

    @app.errorhandler(404)
    def api_not_found(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Not found"}), 404
        return "Not found", 404

    @app.errorhandler(500)
    def api_server_error(e):
        if request.path.startswith("/api/"):
            app.logger.exception("API error on %s", request.path)
            return jsonify(
                {"error": "Server error. Try refreshing or restarting the app."}
            ), 500
        return "Internal server error", 500

    # Before-request hook

    @app.before_request
    def _set_company_data_context():
        from services.company import (
            ensure_company_data,
            set_company_context,
            clear_company_context,
        )

        user = get_current_user()
        if user and user.company:
            ensure_company_data(user.company_id, user.company.slug)
            set_company_context(user.company_id, user.company.slug)
        else:
            clear_company_context()

    # Context processor

    @app.context_processor
    def inject_globals():
        user = get_current_user()
        return {
            "google_maps_api_key": Config.GOOGLE_MAPS_API_KEY,
            "current_user": user,
            "is_admin_view": can_see_all(user),
        }

    # Register blueprints

    from routes import register_blueprints

    register_blueprints(app)

    # Register resolved-flag-keys provider

    import services.expenses as expense_data
    from routes.helpers import decided_keys

    expense_data.register_resolved_flag_keys_provider(lambda: decided_keys("flag"))

    # Init schema & warm caches

    with app.app_context():
        _ensure_schema()
        expense_data.reload_expense_cache()

    return app


def _ensure_schema():
    """Run lightweight migrations for columns added after initial release."""
    from sqlalchemy import inspect, text

    db.create_all()
    insp = inspect(db.engine)
    if insp.has_table("project_proposal"):
        cols = {c["name"] for c in insp.get_columns("project_proposal")}
        if "budget_source" not in cols:
            db.session.execute(
                text(
                    "ALTER TABLE project_proposal "
                    "ADD COLUMN budget_source VARCHAR(32) NOT NULL DEFAULT 'existing'"
                )
            )
            db.session.commit()
        if "colleagues" not in cols:
            db.session.execute(
                text("ALTER TABLE project_proposal ADD COLUMN colleagues TEXT")
            )
            db.session.commit()
    if insp.has_table("employee_trip_report"):
        trip_cols = {c["name"] for c in insp.get_columns("employee_trip_report")}
        if "spending_purpose" not in trip_cols:
            db.session.execute(
                text(
                    "ALTER TABLE employee_trip_report "
                    "ADD COLUMN spending_purpose VARCHAR(20) NOT NULL DEFAULT 'personal'"
                )
            )
            db.session.commit()
        if "project_id" not in trip_cols:
            db.session.execute(
                text("ALTER TABLE employee_trip_report ADD COLUMN project_id INTEGER")
            )
            db.session.commit()


if __name__ == "__main__":
    create_app().run(debug=True)

