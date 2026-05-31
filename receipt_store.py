"""Receipt persistence and CSV pipeline (confirm → JSON + transactions)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pandas as pd

from company_data import get_company_paths
from merchant_catalog import MERCHANTS_BY_CATEGORY, MONTREAL_MERCHANTS
from new_transactions import (
    EMPLOYEE_BY_ID,
    EMPLOYEE_BY_NAME,
    PROJECT_BY_DEPARTMENT,
    make_full_address,
    money_to_float,
    parse_date,
    rescore_transactions,
    save_transaction_outputs,
)

SPENDING_PURPOSE_LABELS = {
    "project": "Project use",
    "personal": "Personal use",
}

EXPENSE_CATEGORY_TO_MCC = {
    "fuel": 5541,
    "meals": 5812,
    "meals & entertainment": 5812,
    "lodging": 7011,
    "hotel": 7011,
    "transportation": 4121,
    "travel": 4784,
    "vehicle maintenance": 7538,
    "permits & fees": 9399,
    "fees & permits": 9399,
    "office supplies": 5045,
    "software & subscriptions": 5734,
    "software & telecom": 4816,
    "telecommunications": 4814,
    "retail": 5300,
    "parking": 7523,
    "shipping": 4215,
    "business services": 7399,
    "general business": 7399,
    "general": 7399,
}

CATEGORY_LABELS = {
    "fuel": "Fuel",
    "meals": "Meals",
    "meals & entertainment": "Meals",
    "lodging": "Hotel",
    "hotel": "Hotel",
    "transportation": "Travel",
    "travel": "Travel",
    "vehicle maintenance": "Vehicle Maintenance",
    "permits & fees": "Fees & Permits",
    "fees & permits": "Fees & Permits",
    "office supplies": "Office Supplies",
    "software & subscriptions": "Software & Telecom",
    "software & telecom": "Software & Telecom",
    "telecommunications": "Software & Telecom",
    "retail": "Retail",
    "parking": "Parking",
    "shipping": "Shipping",
    "business services": "Business Services",
    "general business": "General",
    "general": "General",
}


def spending_purpose_label(purpose: str) -> str:
    return SPENDING_PURPOSE_LABELS.get(purpose or "", purpose or "—")


def apply_dining_context(payload: dict, *, party_size, dining_with: list | None, employee_name: str | None) -> dict:
    """Attach meal party details when saving a restaurant/cafe receipt."""
    from proposal_data import normalize_colleagues
    from guardian_data import employees_by_name
    from expense_data import format_money

    try:
        size = int(party_size or 1)
    except (TypeError, ValueError):
        size = 1
    size = max(size, 1)

    roster = set(employees_by_name().keys())
    guests = normalize_colleagues(dining_with or [], roster=roster, exclude=employee_name)

    payload = {**payload, "dining_party_size": size, "dining_with": guests}
    amount = float(payload.get("amount") or 0)
    if size > 0 and amount > 0:
        payload["dining_per_person"] = round(amount / size, 2)
        payload["dining_per_person_fmt"] = format_money(payload["dining_per_person"])
    return payload


def _receipts_path():
    return get_company_paths().receipts


def _load() -> dict:
    path = _receipts_path()
    if not path.is_file():
        return {"records": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"records": []}
    if not isinstance(data, dict):
        return {"records": []}
    data.setdefault("records", [])
    return data


def _save(data: dict) -> None:
    path = _receipts_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def list_receipts(*, user_id: int | None = None, employee_name: str | None = None) -> list[dict]:
    records = _load()["records"]
    out = []
    for rec in records:
        if user_id is not None and rec.get("user_id") != user_id:
            continue
        if employee_name and rec.get("employee_name") != employee_name:
            continue
        out.append(rec)
    return sorted(out, key=lambda r: r.get("confirmed_at", ""), reverse=True)


def project_spend_by_user(user_id: int) -> dict[int, float]:
    """Sum confirmed receipt amounts per project for a user."""
    from collections import defaultdict

    totals: dict[int, float] = defaultdict(float)
    for rec in _load()["records"]:
        if rec.get("user_id") != user_id:
            continue
        pid = rec.get("project_id")
        if pid is None:
            pid = (rec.get("receipt_data") or {}).get("project_id")
        if pid is None:
            continue
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            continue
        amt = float((rec.get("receipt_data") or {}).get("amount") or 0)
        totals[pid] += amt
    return dict(totals)


def _normalize_category(raw: str | None) -> str:
    key = (raw or "General").strip().lower()
    return CATEGORY_LABELS.get(key, raw.strip() if raw else "General")


def _category_to_mcc(category: str, payload: dict) -> int:
    mcc = payload.get("mcc")
    if mcc is not None and str(mcc).strip().isdigit():
        return int(float(mcc))
    key = category.strip().lower()
    if key in EXPENSE_CATEGORY_TO_MCC:
        return EXPENSE_CATEGORY_TO_MCC[key]
    return EXPENSE_CATEGORY_TO_MCC.get(key.replace("&", "and"), 7399)


def _lookup_merchant_address(merchant_name: str, city: str, category: str) -> tuple[str, str, str, str, str]:
    target = (merchant_name or "").upper()
    city = (city or "MONTREAL").upper()

    for pool in (MERCHANTS_BY_CATEGORY.get(category, []), MONTREAL_MERCHANTS):
        for m in pool:
            name = m["name"].upper()
            if name in target or target in name:
                if m["city"].upper() == city or city == "MONTREAL":
                    return (
                        m["street"],
                        m["city"],
                        m["state"],
                        m["country"],
                        m["postal"],
                    )

    return ("", city, "QC", "CAN", "")


def _resolve_employee(employee_id: str, employee_name: str) -> tuple[str, str, str]:
    if employee_id in EMPLOYEE_BY_ID:
        eid, ename, dept = EMPLOYEE_BY_ID[employee_id]
        return eid, ename, dept
    if employee_name in EMPLOYEE_BY_NAME:
        eid, ename, dept = EMPLOYEE_BY_NAME[employee_name]
        return eid, ename, dept
    try:
        from guardian_data import employees_by_name

        meta = employees_by_name().get(employee_name, {})
        return (
            employee_id or meta.get("employee_id") or "",
            employee_name,
            meta.get("department") or "Operations",
        )
    except Exception:
        return employee_id or "", employee_name, "Operations"


def _format_csv_date_windows(value) -> str:
    dt = parse_date(value)
    if pd.isna(dt):
        dt = datetime.now()
    return f"{dt.month}/{dt.day}/{dt.year}"


def _find_matched_row_index(df: pd.DataFrame, transaction_id: str) -> int | None:
    parts = (transaction_id or "").split("|")
    if len(parts) != 4:
        return None
    emp_id, date_str, vendor, amount_str = parts
    try:
        target_amount = float(amount_str)
    except ValueError:
        return None

    vendor_key = vendor.upper().replace(" ", "")[:20]

    for idx, row in df.iterrows():
        if str(row.get("Employee ID", "")).strip() != emp_id:
            continue
        row_dt = parse_date(row.get("Transaction Date"))
        if pd.isna(row_dt) or row_dt.strftime("%Y-%m-%d") != date_str:
            continue
        row_amt = money_to_float(row.get("Transaction Amount"))
        if abs(row_amt - target_amount) > 0.51:
            continue
        row_vendor = str(row.get("Merchant Info DBA Name") or "").upper().replace(" ", "")
        if vendor_key and vendor_key not in row_vendor and row_vendor[:20] not in vendor_key:
            continue
        return idx
    return None


def _build_receipt_row(
    *,
    employee_id: str,
    employee_name: str,
    department: str,
    payload: dict,
    spending_purpose: str,
    project_title: str | None,
    receipt_id: str,
) -> dict:
    merchant = (payload.get("merchant") or "RECEIPT").strip().upper()
    amount = round(float(payload.get("amount") or 0), 2)
    category = _normalize_category(payload.get("category"))
    mcc = _category_to_mcc(category, payload)

    tx_date = parse_date(payload.get("date"))
    if pd.isna(tx_date):
        tx_date = datetime.now()
    posting_date = tx_date + timedelta(days=1)

    city = (payload.get("merchant_city") or "MONTREAL").strip().upper()
    state = (payload.get("merchant_state") or "QC").strip().upper()
    country = (payload.get("merchant_country") or "CAN").strip().upper()
    postal = (payload.get("merchant_postal_code") or "").strip()

    if payload.get("merchant_street"):
        street = payload.get("merchant_street", "")
    else:
        street, city, state, country, postal = _lookup_merchant_address(
            merchant, city, category
        )

    if spending_purpose == "project" and project_title:
        project_name = project_title
    elif spending_purpose == "personal":
        project_name = "Personal expense (receipt)"
    else:
        project_name = PROJECT_BY_DEPARTMENT.get(department, "General Business Expense")

    description = (
        payload.get("description")
        or payload.get("transaction_description")
        or f"{merchant} {city} {state}"
    ).strip()
    description = f"{description} [Receipt {receipt_id}]"

    debit_or_credit = (payload.get("type") or "Debit").strip().title()
    if debit_or_credit not in ("Debit", "Credit"):
        debit_or_credit = "Debit"

    approved_start = (tx_date - timedelta(days=3)).strftime("%Y-%m-%d")
    approved_end = (tx_date + timedelta(days=3)).strftime("%Y-%m-%d")

    full_address = make_full_address(street, city, state, country, postal)

    return {
        "Employee ID": employee_id,
        "Employee Name": employee_name,
        "Department": department,
        "Project/Trip Name": project_name,
        "Approved City": city,
        "Approved State/Province": state,
        "Approved Country": country,
        "Approved Start Date": approved_start,
        "Approved End Date": approved_end,
        "Transaction Code": 3001,
        "Transaction Description": description,
        "Transaction Category": category,
        "Posting date of transaction": _format_csv_date_windows(posting_date),
        "Transaction Date": _format_csv_date_windows(tx_date),
        "Merchant Info DBA Name": merchant,
        "Transaction Amount": amount,
        "Debit or Credit": debit_or_credit,
        "Merchant Category Code": mcc,
        "Merchant City": city,
        "Merchant Country": country,
        "Merchant Postal Code": postal,
        "Merchant State/Province": state,
        "Conversion Rate": float(payload.get("conversion_rate") or 0),
        "Merchant Street Address": street,
        "Merchant Full Address": full_address,
        "Approved Street Address": street or "",
        "Approved Full Address": full_address if street else make_full_address("", city, state, country, postal),
    }


def append_receipt_to_csv(
    *,
    employee_id: str,
    employee_name: str,
    payload: dict,
    spending_purpose: str,
    project_title: str | None = None,
    matched_transaction_id: str | None = None,
    receipt_id: str,
) -> dict:
    """Persist a confirmed receipt to transactions_original.csv and rescore outputs."""
    paths = get_company_paths()
    original_path = paths.original_tx
    if not original_path.is_file():
        raise FileNotFoundError(f"Missing {original_path}")

    df = pd.read_csv(original_path)
    employee_id, employee_name, department = _resolve_employee(employee_id, employee_name)

    if matched_transaction_id:
        match_idx = _find_matched_row_index(df, matched_transaction_id)
        if match_idx is not None:
            desc = str(df.at[match_idx, "Transaction Description"] or "")
            tag = f"[Receipt {receipt_id}]"
            if tag not in desc:
                df.at[match_idx, "Transaction Description"] = f"{desc} {tag}".strip()
            if spending_purpose == "project" and project_title:
                df.at[match_idx, "Project/Trip Name"] = project_title
            scored, scores_df, flagged_df, department_df = rescore_transactions(df)
            save_transaction_outputs(scored, scores_df, flagged_df, department_df, paths=paths)
            return {
                "action": "linked",
                "transaction_id": matched_transaction_id,
                "row_index": int(match_idx),
            }

    row = _build_receipt_row(
        employee_id=employee_id,
        employee_name=employee_name,
        department=department,
        payload=payload,
        spending_purpose=spending_purpose,
        project_title=project_title,
        receipt_id=receipt_id,
    )

    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    scored, scores_df, flagged_df, department_df = rescore_transactions(df)
    save_transaction_outputs(scored, scores_df, flagged_df, department_df, paths=paths)

    new_idx = len(scored) - 1
    last = scored.iloc[-1]
    row_dt = parse_date(last.get("Transaction Date"))
    date_part = row_dt.strftime("%Y-%m-%d") if not pd.isna(row_dt) else ""
    tx_id = (
        f"{last.get('Employee ID', '')}|{date_part}|"
        f"{last.get('Merchant Info DBA Name', '')}|"
        f"{round(float(last.get('Amount Clean') or 0), 2)}"
    )

    return {
        "action": "appended",
        "transaction_id": tx_id,
        "row_index": new_idx,
    }


def refresh_transaction_caches() -> None:
    from expense_data import reload_expense_cache
    from guardian_data import clear_cache

    clear_cache()
    reload_expense_cache()


def confirm_receipt(
    *,
    user_id: int,
    employee_name: str,
    employee_id: str,
    payload: dict,
    matched_transaction_id: str | None = None,
    spending_purpose: str | None = None,
    project_id: int | None = None,
    project_title: str | None = None,
) -> dict:
    purpose = spending_purpose or payload.get("spending_purpose") or "project"
    payload = {**payload, "spending_purpose": purpose}
    if project_id is not None:
        payload["project_id"] = project_id
        payload["project_title"] = project_title or payload.get("project_title")
    tag = f"receipt_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    record = {
        "receipt_id": tag,
        "user_id": user_id,
        "employee_name": employee_name,
        "employee_id": employee_id,
        "matched_transaction_id": matched_transaction_id,
        "spending_purpose": purpose,
        "spending_purpose_label": spending_purpose_label(purpose),
        "confirmed_at": datetime.now().isoformat(timespec="seconds"),
        "receipt_confirmed": True,
        "receipt_data": payload,
    }
    if project_id is not None:
        record["project_id"] = project_id
        record["project_title"] = project_title or payload.get("project_title")
    if payload.get("dining_party_size"):
        record["dining_party_size"] = payload.get("dining_party_size")
        record["dining_with"] = payload.get("dining_with") or []
        if payload.get("dining_per_person_fmt"):
            record["dining_per_person_fmt"] = payload.get("dining_per_person_fmt")
    data = _load()
    data["records"].append(record)
    _save(data)

    csv_result = None
    try:
        csv_result = append_receipt_to_csv(
            employee_id=employee_id,
            employee_name=employee_name,
            payload=payload,
            spending_purpose=purpose,
            project_title=project_title,
            matched_transaction_id=matched_transaction_id,
            receipt_id=tag,
        )
        refresh_transaction_caches()
    except Exception as exc:
        record["csv_error"] = str(exc)
    else:
        record["csv_action"] = csv_result.get("action") if csv_result else None
        record["csv_transaction_id"] = csv_result.get("transaction_id") if csv_result else None

    return record
