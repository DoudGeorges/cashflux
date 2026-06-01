"""Login, signup, company tenancy, and role helpers."""

from __future__ import annotations

import re
from typing import Any
from datetime import datetime
from functools import wraps

from flask import abort, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

User: Any = None
Company: Any = None
_db: Any = None

ADMIN_ROLES = frozenset({"finance_admin", "ceo"})


def bind(db):
    """Register User and Company models on the shared SQLAlchemy instance."""
    global _db, User, Company
    _db = db

    class Company(db.Model):
        __tablename__ = "company"

        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(200), nullable=False)
        slug = db.Column(db.String(80), unique=True, nullable=False, index=True)
        created_at = db.Column(db.DateTime, default=datetime.now)

        users = db.relationship("User", backref="company", lazy=True)

    class User(db.Model):
        __tablename__ = "user"

        id = db.Column(db.Integer, primary_key=True)
        company_id = db.Column(db.Integer, db.ForeignKey("company.id"), nullable=False)
        email = db.Column(db.String(255), unique=True, nullable=False, index=True)
        password_hash = db.Column(db.String(255), nullable=False)
        display_name = db.Column(db.String(120), nullable=False)
        role = db.Column(db.String(32), nullable=False, default="employee")
        employee_name = db.Column(db.String(120))
        created_at = db.Column(db.DateTime, default=datetime.now)

        def set_password(self, password: str) -> None:
            self.password_hash = generate_password_hash(password)

        def check_password(self, password: str) -> bool:
            return check_password_hash(self.password_hash, password)

    return User, Company


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug or "company"


def unique_slug(base: str) -> str:
    slug = slugify(base)
    if not Company.query.filter_by(slug=slug).first():
        return slug
    n = 2
    while Company.query.filter_by(slug=f"{slug}-{n}").first():
        n += 1
    return f"{slug}-{n}"


def get_current_user() -> Any:
    uid = session.get("user_id")
    if not uid:
        return None
    return _db.session.get(User, uid)


def can_see_all(user) -> bool:
    return bool(user and user.role in ADMIN_ROLES)


def employee_scope(user) -> str | None:
    if not user or can_see_all(user):
        return None
    return user.employee_name


def user_to_dict(user) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "role_label": role_label(user.role),
        "employee_name": user.employee_name,
        "company": user.company.name if user.company else "",
        "company_slug": user.company.slug if user.company else "",
        "is_admin": can_see_all(user),
    }


def role_label(role: str) -> str:
    return {
        "finance_admin": "Finance Admin",
        "ceo": "CEO",
        "employee": "Employee",
    }.get(role, role.replace("_", " ").title())


def login_user(user) -> None:
    session.clear()
    session["user_id"] = user.id
    session.permanent = True


def logout_user() -> None:
    session.clear()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if get_current_user():
            return view(*args, **kwargs)
        if request.path.startswith("/api/") or request.is_json:
            return jsonify({"error": "Unauthorized"}), 401
        nxt = request.path if request.path not in ("/", "") else ""
        return redirect(url_for("login", next=nxt))

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = get_current_user()
        if not user:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("login"))
        if not can_see_all(user):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Forbidden"}), 403
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def roster_employee_names(company_slug: str | None = None) -> list[str]:
    from services.company import ensure_company_data, set_company_context
    from services.guardian import employee_summary

    if company_slug:
        company = Company.query.filter_by(slug=slugify(company_slug)).first()
        if company:
            ensure_company_data(company.id, company.slug)
            set_company_context(company.id, company.slug)

    df = employee_summary()
    if df.empty:
        return []
    return sorted(df["employee_name"].astype(str).tolist())


def register_auth_routes(app):
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if get_current_user():
            return redirect(url_for("dashboard.index"))

        error = None
        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()
            password = request.form.get("password") or ""
            user = User.query.filter_by(email=email).first()
            if not user or not user.check_password(password):
                error = "Invalid email or password."
            else:
                login_user(user)
                nxt = request.args.get("next") or url_for("dashboard.index")
                if not nxt.startswith("/") or nxt.startswith("//"):
                    nxt = url_for("dashboard.index")
                return redirect(nxt)

        return render_template("login.html", error=error)

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if get_current_user():
            return redirect(url_for("dashboard.index"))

        error = None
        mode = (
            request.form.get("mode")
            if request.method == "POST"
            else request.args.get("mode", "create")
        )
        if mode not in ("create", "join"):
            mode = "create"
        join_slug = (
            request.args.get("company_slug") or request.form.get("company_slug") or ""
        ).strip()
        roster = (
            roster_employee_names(join_slug) if mode == "join" and join_slug else []
        )

        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()
            password = request.form.get("password") or ""
            display_name = (request.form.get("display_name") or "").strip()
            mode = request.form.get("mode") or "create"

            if not email or not password or len(password) < 6:
                error = "Email and password (6+ characters) are required."
            elif User.query.filter_by(email=email).first():
                error = "An account with that email already exists."
            elif mode == "create":
                company_name = (request.form.get("company_name") or "").strip()
                role = (request.form.get("role") or "finance_admin").strip()
                if role not in ADMIN_ROLES:
                    role = "finance_admin"
                if not company_name or not display_name:
                    error = "Company name and your name are required."
                else:
                    company = Company(name=company_name, slug=unique_slug(company_name))
                    user = User(
                        company=company,
                        email=email,
                        display_name=display_name,
                        role=role,
                        employee_name=None,
                    )
                    user.set_password(password)
                    _db.session.add(company)
                    _db.session.add(user)
                    _db.session.commit()
                    from services.company import init_empty_company_data

                    init_empty_company_data(company.id, company.slug)
                    login_user(user)
                    return redirect(url_for("dashboard.index"))
            else:
                company_slug = slugify(request.form.get("company_slug") or "")
                employee_name = (request.form.get("employee_name") or "").strip()
                company = Company.query.filter_by(slug=company_slug).first()
                if not company:
                    error = "Company not found. Check the company code."
                elif not display_name:
                    error = "Your name is required."
                else:
                    from services.company import (
                        ensure_company_data,
                        set_company_context,
                    )

                    ensure_company_data(company.id, company.slug)
                    set_company_context(company.id, company.slug)
                    join_roster = roster_employee_names(company.slug)
                    if join_roster and (
                        not employee_name or employee_name not in join_roster
                    ):
                        error = "Pick your name from the employee list."
                    elif not join_roster and not employee_name:
                        error = "Enter your name as it appears on expense reports."
                    else:
                        user = User(
                            company_id=company.id,
                            email=email,
                            display_name=display_name,
                            role="employee",
                            employee_name=employee_name or display_name,
                        )
                        user.set_password(password)
                        _db.session.add(user)
                        _db.session.commit()
                        login_user(user)
                        return redirect(url_for("dashboard.index"))

        return render_template(
            "signup.html",
            error=error,
            mode=mode,
            roster=roster,
        )

    @app.route("/logout", methods=["POST"])
    def logout():
        logout_user()
        return redirect(url_for("login"))

    @app.route("/api/me")
    @login_required
    def api_me():
        user = get_current_user()
        return jsonify(user_to_dict(user))

    @app.route("/api/auth/roster")
    def api_auth_roster():
        company_slug = (request.args.get("company_slug") or "").strip()
        return jsonify({"employees": roster_employee_names(company_slug or None)})

