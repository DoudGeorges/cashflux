"""Seed login accounts for every employee in the CSV roster."""

from __future__ import annotations

import re

from app import app, db, User, Company
from company_data import DEFAULT_COMPANY_SLUG, ensure_company_data, set_company_context
from guardian_data import employee_summary, clear_cache

COMPANY_NAME = "Northwind Analytics Group"
COMPANY_SLUG = "northwind-analytics"
DEFAULT_PASSWORD = "1234"


def _email_for(employee_id: str, employee_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", ".", employee_name.lower()).strip(".")
    return f"{employee_id.lower()}@{COMPANY_SLUG}.local"


def seed_employee_accounts(*, replace_existing: bool = False) -> dict:
    with app.app_context():
        db.create_all()

        company = Company.query.filter_by(slug=COMPANY_SLUG).first()
        if not company:
            company = Company(name=COMPANY_NAME, slug=COMPANY_SLUG)
            db.session.add(company)
            db.session.commit()

        ensure_company_data(company.id, company.slug)
        set_company_context(company.id, company.slug)
        clear_cache()

        df = employee_summary()
        created = []
        skipped = []

        for row in df.itertuples():
            employee_id = str(row.employee_id)
            employee_name = str(row.employee_name)
            email = _email_for(employee_id, employee_name)

            existing = User.query.filter_by(email=email).first()
            if existing:
                if replace_existing:
                    existing.company_id = company.id
                    existing.display_name = employee_name
                    existing.role = "employee"
                    existing.employee_name = employee_name
                    existing.set_password(DEFAULT_PASSWORD)
                    skipped.append(f"updated:{email}")
                else:
                    skipped.append(f"exists:{email}")
                continue

            user = User(
                company_id=company.id,
                email=email,
                display_name=employee_name,
                role="employee",
                employee_name=employee_name,
            )
            user.set_password(DEFAULT_PASSWORD)
            db.session.add(user)
            created.append({"name": employee_name, "email": email, "id": employee_id})

        db.session.commit()

        return {
            "company": COMPANY_NAME,
            "company_slug": COMPANY_SLUG,
            "password": DEFAULT_PASSWORD,
            "created": created,
            "skipped": skipped,
        }


if __name__ == "__main__":
    result = seed_employee_accounts()
    print(f"Company: {result['company']} (code: {result['company_slug']})")
    print(f"Password for all new accounts: {result['password']}")
    print(f"\nCreated {len(result['created'])} accounts:")
    for acct in result["created"]:
        print(f"  {acct['name']:<20} {acct['email']}")
    if result["skipped"]:
        print(f"\nSkipped/updated {len(result['skipped'])}:")
