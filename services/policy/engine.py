"""Digitized expense policy engine: rules, contextual checks, split-purchase detection."""

from __future__ import annotations

import json
import logging
import re
from datetime import timedelta

import pandas as pd

from core.paths import POLICY_DOC_PATH, RULES_PATH
from core.formatting import EMPTY_LABEL, fmt_date, sanitize_display_text


def _restaurant_mcc_codes() -> frozenset:
    """Restaurant MCC codes from policy rules (single source of truth)."""
    rules = load_policy_rules()
    return frozenset(rules.get("restaurant_mcc_codes", []))


RISK_ORDER = {"Low": 1, "Medium": 2, "High": 3, "Severe": 4}


def _clean_violation(record: dict) -> dict:
    cleaned = dict(record)
    if cleaned.get("reason"):
        cleaned["reason"] = sanitize_display_text(cleaned["reason"])
    dept = cleaned.get("department")
    if dept in (None, "", "-"):
        cleaned["department"] = EMPTY_LABEL
    return cleaned


DEFAULT_RULES = {
    "pre_auth_threshold": 50,
    "manager_approval_threshold": 500,
    "solo_meal_limit": 75,
    "team_meal_limit": 200,
    "team_meal_per_person_limit": 75,
    "solo_meal_flag_minimum": 100,
    "tip_max_percent": 20,
    "service_tip_max_percent": 15,
    "receipt_required": True,
    "receipt_submission_days": 31,
    "personal_expenses_prohibited": True,
    "split_purchase_window_hours": 48,
    "split_purchase_min_charges": 2,
    "mileage_rate_per_km": 0.72,
    "alcohol_keywords": ["wine", "beer", "liquor", "bar", "pub", "brewery"],
    "team_meal_keywords": [
        "team",
        "group",
        "client",
        "customer",
        "dinner with",
        "lunch with",
    ],
    "customer_keywords": ["customer", "client", "guest"],
    "personal_expense_keywords": ["personal", "family", "spouse", "gift card"],
    "prohibited_expense_keywords": [
        "traffic ticket",
        "parking ticket",
        "personal use",
        "fine",
    ],
    "irrelevant_business_keywords": [
        "blind box",
        "blindbox",
        "pop mart",
        "popmart",
        "labubu",
        "gacha",
        "collectible",
        "figurine",
        "funko",
        "plush",
        "trading card",
        "pokemon",
        "mystery box",
        "surprise box",
        "toy",
        "lottery",
        "steam game",
        "playstation",
        "xbox",
        "anime merch",
    ],
    "restricted_merchants": [],
    "restaurant_mcc_codes": [5812, 5813, 5814],
    "department_overrides": {},
    "role_overrides": {},
}

DEPT_OVERRIDE_FIELDS = [
    {
        "key": "manager_approval_threshold",
        "label": "Approval threshold",
        "type": "number",
    },
    {"key": "pre_auth_threshold", "label": "Pre-auth threshold", "type": "number"},
    {"key": "solo_meal_limit", "label": "Solo meal limit", "type": "number"},
    {"key": "team_meal_limit", "label": "Team meal limit", "type": "number"},
    {
        "key": "conference_pre_approved",
        "label": "Conferences pre-approved",
        "type": "boolean",
    },
]

POLICY_SCHEMA = [
    {
        "key": "pre_auth_threshold",
        "label": "Pre-authorization threshold",
        "type": "number",
        "section": "thresholds",
        "unit": "$",
        "help": "Expenses above this require manager pre-auth.",
    },
    {
        "key": "manager_approval_threshold",
        "label": "Manager approval threshold",
        "type": "number",
        "section": "thresholds",
        "unit": "$",
        "help": "Expenses above this require formal approval.",
    },
    {
        "key": "solo_meal_limit",
        "label": "Solo meal limit",
        "type": "number",
        "section": "meals",
        "unit": "$",
        "help": "Max for a meal without team/client context.",
    },
    {
        "key": "team_meal_limit",
        "label": "Team meal total limit",
        "type": "number",
        "section": "meals",
        "unit": "$",
        "help": "Max total for documented team meals.",
    },
    {
        "key": "team_meal_per_person_limit",
        "label": "Team meal per-person limit",
        "type": "number",
        "section": "meals",
        "unit": "$",
        "help": "Estimated per-person cap on team meals.",
    },
    {
        "key": "solo_meal_flag_minimum",
        "label": "Solo meal flag minimum",
        "type": "number",
        "section": "meals",
        "unit": "$",
        "help": "Only flag solo meals above this amount.",
    },
    {
        "key": "tip_max_percent",
        "label": "Max meal tip",
        "type": "number",
        "section": "meals",
        "unit": "%",
        "help": "Meal tips reimbursed up to this percent.",
    },
    {
        "key": "service_tip_max_percent",
        "label": "Max service tip",
        "type": "number",
        "section": "meals",
        "unit": "%",
        "help": "Porterage/services tip cap.",
    },
    {
        "key": "receipt_required",
        "label": "Receipts required",
        "type": "boolean",
        "section": "general",
        "help": "All reimbursements require receipts.",
    },
    {
        "key": "receipt_submission_days",
        "label": "Receipt submission window",
        "type": "number",
        "section": "general",
        "unit": "days",
        "help": "Submit receipts within this many days.",
    },
    {
        "key": "personal_expenses_prohibited",
        "label": "Personal expenses prohibited",
        "type": "boolean",
        "section": "general",
        "help": "Block personal spend on corporate cards.",
    },
    {
        "key": "split_purchase_window_hours",
        "label": "Split purchase window",
        "type": "number",
        "section": "fraud",
        "unit": "hours",
        "help": "Look for split charges within this window.",
    },
    {
        "key": "split_purchase_min_charges",
        "label": "Split purchase min charges",
        "type": "number",
        "section": "fraud",
        "help": "Minimum charges to trigger split detection.",
    },
    {
        "key": "mileage_rate_per_km",
        "label": "Mileage rate",
        "type": "number",
        "section": "travel",
        "unit": "$/km",
        "help": "CRA mileage reimbursement rate.",
    },
    {
        "key": "alcohol_keywords",
        "label": "Alcohol keywords",
        "type": "keywords",
        "section": "keywords",
        "help": "Flag unless customer entertainment documented.",
    },
    {
        "key": "team_meal_keywords",
        "label": "Team meal keywords",
        "type": "keywords",
        "section": "keywords",
        "help": "Indicate team/client meal context.",
    },
    {
        "key": "customer_keywords",
        "label": "Customer keywords",
        "type": "keywords",
        "section": "keywords",
        "help": "Allow alcohol when these appear on receipt.",
    },
    {
        "key": "personal_expense_keywords",
        "label": "Personal expense keywords",
        "type": "keywords",
        "section": "keywords",
        "help": "Flag likely personal purchases.",
    },
    {
        "key": "irrelevant_business_keywords",
        "label": "Non-business expense keywords",
        "type": "keywords",
        "section": "keywords",
        "help": "Flag purchases unrelated to company work (collectibles, blind boxes, toys, etc.).",
    },
    {
        "key": "prohibited_expense_keywords",
        "label": "Prohibited expense keywords",
        "type": "keywords",
        "section": "keywords",
        "help": "Never reimbursable (tickets, fines, etc.).",
    },
    {
        "key": "restricted_merchants",
        "label": "Restricted merchants",
        "type": "keywords",
        "section": "keywords",
        "help": "Vendor names that always flag.",
    },
    {
        "key": "restaurant_mcc_codes",
        "label": "Restaurant MCC codes",
        "type": "numbers",
        "section": "meals",
        "help": "Merchant category codes treated as restaurants.",
    },
]


def load_policy_rules() -> dict:
    if RULES_PATH.is_file():
        with open(RULES_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return normalize_rules(data)
    return normalize_rules({})


def normalize_rules(rules: dict) -> dict:
    merged = {**DEFAULT_RULES, **(rules or {})}
    merged["department_overrides"] = dict(rules.get("department_overrides") or {})
    merged["role_overrides"] = dict(rules.get("role_overrides") or {})

    for key in (
        "pre_auth_threshold",
        "manager_approval_threshold",
        "solo_meal_limit",
        "team_meal_limit",
        "team_meal_per_person_limit",
        "solo_meal_flag_minimum",
        "tip_max_percent",
        "service_tip_max_percent",
        "receipt_submission_days",
        "split_purchase_window_hours",
        "split_purchase_min_charges",
        "mileage_rate_per_km",
    ):
        if key in merged:
            merged[key] = float(merged[key])

    for key in ("receipt_required", "personal_expenses_prohibited"):
        merged[key] = bool(merged[key])

    for key in (
        "alcohol_keywords",
        "team_meal_keywords",
        "customer_keywords",
        "personal_expense_keywords",
        "prohibited_expense_keywords",
        "irrelevant_business_keywords",
        "restricted_merchants",
    ):
        merged[key] = _coerce_keywords(merged.get(key))

    codes = merged.get("restaurant_mcc_codes") or []
    merged["restaurant_mcc_codes"] = [int(c) for c in codes if str(c).strip().isdigit()]

    return merged


def _coerce_keywords(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip().lower() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [
            part.strip().lower()
            for part in value.replace("\n", ",").split(",")
            if part.strip()
        ]
    return []


def save_policy_rules(rules: dict) -> dict:
    clean = normalize_rules(rules)
    clean["department_overrides"] = rules.get("department_overrides") or {}
    clean["role_overrides"] = rules.get("role_overrides") or {}
    with open(RULES_PATH, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2)
    clear_policy_cache()
    return clean


def load_policy_document() -> str:
    if POLICY_DOC_PATH.is_file():
        return POLICY_DOC_PATH.read_text(encoding="utf-8")
    return ""


def save_policy_document(text: str) -> str:
    POLICY_DOC_PATH.write_text(text or "", encoding="utf-8")
    return text


def get_policy_schema() -> list[dict]:
    return list(POLICY_SCHEMA)


def list_policy_departments() -> list[str]:
    try:
        from services.expenses.guardian import department_summary

        return sorted(department_summary()["department"].astype(str).tolist())
    except Exception:
        rules = load_policy_rules()
        return sorted(rules.get("department_overrides", {}).keys())


def policy_summary_text() -> str:
    rules = load_policy_rules()
    lines = [
        "Brim expense policy (digitized)",
        f"- Pre-authorization required above ${rules['pre_auth_threshold']:,.0f}",
        f"- Manager approval above ${rules['manager_approval_threshold']:,.0f}",
        f"- Solo meal limit ${rules['solo_meal_limit']:,.0f}, team meals up to ${rules['team_meal_limit']:,.0f}",
        f"- Meal tips up to {rules['tip_max_percent']:.0f}%, service tips up to {rules['service_tip_max_percent']:.0f}%",
        f"- Receipts required within {int(rules['receipt_submission_days'])} days"
        if rules.get("receipt_required")
        else "- Receipts optional",
        "- Personal expenses prohibited on corporate cards"
        if rules.get("personal_expenses_prohibited")
        else "- Personal expense monitoring relaxed",
        f"- Split purchase detection: {int(rules['split_purchase_min_charges'])}+ charges within {int(rules['split_purchase_window_hours'])}h",
        f"- {len(rules.get('department_overrides', {}))} department override(s) active",
    ]
    return "\n".join(lines)


def _rules_for_row(row, rules: dict) -> dict:
    dept = str(row.get("Department") or "").strip()
    merged = dict(rules)
    overrides = rules.get("department_overrides") or {}
    if dept in overrides:
        merged.update(overrides[dept])
    role = _employee_role(row, rules)
    if role:
        role_rules = (rules.get("role_overrides") or {}).get(role) or {}
        merged.update(role_rules)
    return merged


_employee_role_map_cache: dict[str, str] | None = None


def _employee_role(row, rules: dict) -> str | None:
    """Resolve role for policy overrides (explicit map or dept lead heuristic)."""
    global _employee_role_map_cache
    name = str(row.get("Employee Name") or "").strip()
    explicit = (rules.get("employee_roles") or {}).get(name)
    if explicit:
        return explicit
    if _employee_role_map_cache is None:
        _employee_role_map_cache = _build_employee_role_map()
    return _employee_role_map_cache.get(name)


def _build_employee_role_map() -> dict[str, str]:
    """Assign Director / Manager / Staff from roster for role-based policy rules."""
    from services.expenses.guardian import transactions

    df = transactions()
    if df.empty:
        return {}
    roles: dict[str, str] = {}
    for dept, grp in df.groupby("Department"):
        emps = (
            grp.groupby("Employee Name")["Employee ID"]
            .first()
            .reset_index()
            .sort_values("Employee ID")
        )
        for idx, (_, emp_row) in enumerate(emps.iterrows()):
            roles[str(emp_row["Employee Name"])] = "Manager" if idx == 0 else "Staff"
    first = (
        df.groupby("Employee Name")["Employee ID"]
        .first()
        .reset_index()
        .sort_values("Employee ID")
        .iloc[0]
    )
    roles[str(first["Employee Name"])] = "Director"
    return roles


def _receipt_covered_keys() -> set[str]:
    keys: set[str] = set()
    try:
        from services.receipts import list_receipts

        for rec in list_receipts():
            tid = rec.get("matched_transaction_id")
            if tid:
                keys.add(str(tid))
            data = rec.get("receipt_data") or {}
            merchant = str(data.get("merchant") or "").strip().lower()
            date = str(data.get("date") or "")[:10]
            employee = str(rec.get("employee_name") or "")
            if merchant and date and employee:
                keys.add(f"{employee}|{merchant}|{date}")
    except Exception:
        logging.debug("Receipt key lookup failed", exc_info=True)
    return keys


def _text_blob(row) -> str:
    parts = [
        str(row.get("Merchant Info DBA Name") or ""),
        str(row.get("Transaction Description") or ""),
        str(row.get("Transaction Category") or ""),
    ]
    return " ".join(parts).lower()


def _is_restaurant(row, rules: dict | None = None) -> bool:
    rules = rules or load_policy_rules()
    mcc_codes = {
        int(c) for c in rules.get("restaurant_mcc_codes") or _restaurant_mcc_codes()
    }
    mcc = str(row.get("Merchant Category Code") or "").strip()
    if mcc.isdigit() and int(mcc) in mcc_codes:
        return True
    blob = _text_blob(row)
    return any(
        k in blob
        for k in ("restaurant", "cafe", "dining", "grill", "bistro", "kitchen")
    )


def _team_meal_context(row, df: pd.DataFrame | None = None) -> tuple[bool, str]:
    blob = _text_blob(row)
    rules = load_policy_rules()
    if any(k in blob for k in rules.get("team_meal_keywords") or []):
        return True, "Team/client meal indicated in description"

    if df is not None and "Transaction Date" in df.columns:
        date = row.get("Transaction Date")
        merchant = str(row.get("Merchant Info DBA Name") or "").strip().lower()
        if pd.notna(date) and merchant:
            window = df[
                (df["Merchant Info DBA Name"].astype(str).str.lower() == merchant)
                & (df["Transaction Date"] >= date - timedelta(hours=6))
                & (df["Transaction Date"] <= date + timedelta(hours=6))
            ]
            employees = window["Employee Name"].nunique()
            if employees >= 2:
                return (
                    True,
                    f"{employees} employees charged same merchant within 6h (likely team meal)",
                )

    if "guest" in blob or "attendees" in blob:
        return True, "Guest list referenced on receipt"

    return False, ""


def _estimate_party_size(row, is_team: bool) -> int:
    if is_team:
        amount = float(row.get("Amount Clean") or 0)
        if amount > 150:
            return max(3, int(amount // 60))
        return 3
    return 1


def check_transaction_policy(
    row, rules: dict | None = None, df: pd.DataFrame | None = None
) -> list[dict]:
    """Return zero or more policy violation dicts for a single transaction row."""
    rules = rules or load_policy_rules()
    row_rules = _rules_for_row(row, rules)
    amount = float(row.get("Amount Clean") or 0)
    if amount <= 0:
        return []
    if str(row.get("Debit or Credit") or "").lower() == "credit":
        return []

    violations = []
    blob = _text_blob(row)
    dept = str(row.get("Department") or "-")
    employee = str(row.get("Employee Name") or "-")
    vendor = str(row.get("Merchant Info DBA Name") or "-")

    pre_auth = float(row_rules.get("pre_auth_threshold", 50))
    approval = float(row_rules.get("manager_approval_threshold", 500))
    trip = str(row.get("Project/Trip Name") or "").strip()

    if pre_auth < amount < approval and not trip:
        violations.append(
            {
                "flag_type": "policy_violation",
                "severity": "Low",
                "reason": (
                    f"Expense ${amount:,.2f} exceeds ${pre_auth:,.0f} pre-auth threshold "
                    f"and is not linked to an approved trip/project."
                ),
                "employee": employee,
                "department": dept,
                "vendor": vendor,
                "amount": amount,
            }
        )

    if _is_restaurant(row, rules):
        is_team, team_note = _team_meal_context(row, df)
        party = _estimate_party_size(row, is_team)
        solo_limit = float(row_rules.get("solo_meal_limit", 75))
        team_limit = float(row_rules.get("team_meal_limit", 200))
        per_person = float(row_rules.get("team_meal_per_person_limit", 75))
        solo_min = float(row_rules.get("solo_meal_flag_minimum", 100))

        if not is_team and amount > solo_limit and amount > solo_min:
            violations.append(
                {
                    "flag_type": "policy_violation",
                    "severity": "High" if amount > solo_limit * 2 else "Medium",
                    "reason": (
                        f"${amount:,.2f} solo meal at {vendor} exceeds ${solo_limit:,.0f} solo dining limit. "
                        f"No team/client context detected: may be personal or missing guest list."
                    ),
                    "employee": employee,
                    "department": dept,
                    "vendor": vendor,
                    "amount": amount,
                }
            )
        elif is_team:
            est_per = amount / party
            if amount > team_limit or est_per > per_person:
                violations.append(
                    {
                        "flag_type": "policy_violation",
                        "severity": "Medium",
                        "reason": (
                            f"${amount:,.2f} team meal ({team_note}, approx. {party} people, "
                            f"approx. ${est_per:,.0f}/person) exceeds policy limits."
                        ),
                        "employee": employee,
                        "department": dept,
                        "vendor": vendor,
                        "amount": amount,
                    }
                )

    alcohol_keys = rules.get("alcohol_keywords") or []
    customer_keys = rules.get("customer_keywords") or ["customer", "client", "guest"]
    if any(k in blob for k in alcohol_keys):
        if not any(k in blob for k in customer_keys):
            violations.append(
                {
                    "flag_type": "policy_violation",
                    "severity": "High",
                    "reason": (
                        "Alcohol-related charge without documented customer entertainment "
                        "(Brim policy: alcoholic beverages only with customers)."
                    ),
                    "employee": employee,
                    "department": dept,
                    "vendor": vendor,
                    "amount": amount,
                }
            )

    tip_match = re.search(r"(\d{1,2})\s*%\s*tip", blob)
    if tip_match:
        tip_pct = int(tip_match.group(1))
        max_tip = int(row_rules.get("tip_max_percent", 20))
        if tip_pct > max_tip:
            violations.append(
                {
                    "flag_type": "policy_violation",
                    "severity": "Low",
                    "reason": f"Tip {tip_pct}% exceeds {max_tip}% reimbursement cap.",
                    "employee": employee,
                    "department": dept,
                    "vendor": vendor,
                    "amount": amount,
                }
            )

    vendor_lower = vendor.lower()
    for restricted in rules.get("restricted_merchants") or []:
        if restricted and restricted.lower() in vendor_lower:
            violations.append(
                {
                    "flag_type": "policy_violation",
                    "severity": "High",
                    "reason": f"Merchant '{vendor}' is on the restricted merchants list.",
                    "employee": employee,
                    "department": dept,
                    "vendor": vendor,
                    "amount": amount,
                }
            )
            break

    if rules.get("personal_expenses_prohibited"):
        for keyword in rules.get("personal_expense_keywords") or []:
            if keyword and keyword in blob:
                violations.append(
                    {
                        "flag_type": "policy_violation",
                        "severity": "Medium",
                        "reason": f"Possible personal expense detected ('{keyword}'). Personal charges on corporate cards are prohibited.",
                        "employee": employee,
                        "department": dept,
                        "vendor": vendor,
                        "amount": amount,
                    }
                )
                break
        for keyword in rules.get("irrelevant_business_keywords") or []:
            if keyword and keyword in blob:
                violations.append(
                    {
                        "flag_type": "policy_violation",
                        "severity": "High",
                        "reason": (
                            f"Non-business expense detected ('{keyword}'). "
                            "Collectibles, blind boxes, toys, and hobby purchases are not valid company expenses."
                        ),
                        "employee": employee,
                        "department": dept,
                        "vendor": vendor,
                        "amount": amount,
                    }
                )
                break

    for keyword in rules.get("prohibited_expense_keywords") or []:
        if keyword and keyword in blob:
            violations.append(
                {
                    "flag_type": "policy_violation",
                    "severity": "Severe",
                    "reason": f"Prohibited expense type detected ('{keyword}'): not reimbursable per policy.",
                    "employee": employee,
                    "department": dept,
                    "vendor": vendor,
                    "amount": amount,
                }
            )
            break

    if row_rules.get("receipt_required") and amount >= float(
        row_rules.get("pre_auth_threshold", 50)
    ):
        covered = _receipt_covered_keys()
        tx_date = row.get("Transaction Date")
        date_str = (
            tx_date.date().isoformat()
            if hasattr(tx_date, "date") and pd.notna(tx_date)
            else ""
        )
        lookup = f"{employee}|{vendor.lower()}|{date_str}"
        emp_id = str(row.get("Employee ID") or "").strip()
        tx_id = f"{emp_id}|{date_str}|{vendor}|{round(amount, 2)}"
        if tx_id not in covered and lookup not in covered:
            days_limit = int(row_rules.get("receipt_submission_days", 31))
            violations.append(
                {
                    "flag_type": "policy_violation",
                    "severity": "Medium",
                    "reason": (
                        f"No receipt on file for ${amount:,.2f} at {vendor}. "
                        f"Policy requires receipts within {days_limit} days."
                    ),
                    "employee": employee,
                    "department": dept,
                    "vendor": vendor,
                    "amount": amount,
                }
            )

    return [_clean_violation(v) for v in violations]


def detect_split_purchases(df: pd.DataFrame, rules: dict | None = None) -> list[dict]:
    """Flag employees splitting charges to stay under approval threshold."""
    rules = rules or load_policy_rules()
    if df.empty:
        return []

    work = df.copy()
    work["Transaction Date"] = pd.to_datetime(work["Transaction Date"], errors="coerce")
    work = work[work["Debit or Credit"].astype(str).str.lower() == "debit"]
    work = work[work["Amount Clean"] > 0]

    flags = []
    seen_clusters: set[frozenset] = set()
    window_hours = float(rules.get("split_purchase_window_hours", 48))
    min_charges = int(rules.get("split_purchase_min_charges", 2))

    for (emp_id, merchant), group in work.groupby(
        [
            "Employee ID",
            work["Merchant Info DBA Name"].astype(str).str.strip().str.lower(),
        ]
    ):
        if len(group) < min_charges:
            continue
        group = group.sort_values("Transaction Date")
        dept_rules = _rules_for_row(group.iloc[0], rules)
        threshold = float(dept_rules.get("manager_approval_threshold", 500))

        for _, row in group.iterrows():
            window_start = row["Transaction Date"]
            if pd.isna(window_start):
                continue
            window_end = window_start + timedelta(hours=window_hours)
            cluster = group[
                (group["Transaction Date"] >= window_start)
                & (group["Transaction Date"] <= window_end)
            ]
            if len(cluster) < min_charges:
                continue

            amounts = cluster["Amount Clean"].astype(float)
            combined = float(amounts.sum())
            if combined < threshold:
                continue
            if any(a >= threshold for a in amounts):
                continue

            cluster_key = frozenset(cluster.index.tolist())
            if cluster_key in seen_clusters:
                continue
            seen_clusters.add(cluster_key)

            parts = ", ".join(f"${a:,.2f}" for a in amounts)
            anchor = cluster.iloc[0]
            flags.append(
                {
                    "flag_type": "split_purchase",
                    "severity": "Severe",
                    "reason": (
                        f"Possible split purchase: {len(cluster)} charges at {anchor['Merchant Info DBA Name']} "
                        f"({parts}) totaling ${combined:,.2f} within {int(window_hours)}h: each under ${threshold:,.0f} "
                        f"approval threshold."
                    ),
                    "employee": anchor["Employee Name"],
                    "department": anchor.get("Department", "-"),
                    "vendor": anchor["Merchant Info DBA Name"],
                    "amount": combined,
                    "transaction_ids": cluster.index.astype(str).tolist(),
                    "employee_id": emp_id,
                }
            )

    return [_clean_violation(v) for v in flags]


_policy_cache: list[dict] | None = None
_policy_cache_mtime: float | None = None


def scan_all_policy_violations(df: pd.DataFrame | None = None) -> list[dict]:
    global _policy_cache, _policy_cache_mtime
    from services.expenses.guardian import transactions, SCORED_TX_PATH

    df = df if df is not None else transactions()
    try:
        mtime = SCORED_TX_PATH.stat().st_mtime
    except OSError:
        mtime = None

    if (
        _policy_cache is not None
        and _policy_cache_mtime == mtime
        and df is transactions()
    ):
        return list(_policy_cache)

    rules = load_policy_rules()
    violations: list[dict] = []

    for _, row in df.iterrows():
        for v in check_transaction_policy(row, rules, df=df):
            v["date"] = row.get("Transaction Date")
            v["risk"] = v["severity"]
            violations.append(v)

    for split in detect_split_purchases(df, rules):
        split["date"] = None
        split["risk"] = split["severity"]
        violations.append(split)

    if df is transactions():
        _policy_cache = [_clean_violation(v) for v in violations]
        _policy_cache_mtime = mtime

    return [_clean_violation(v) for v in violations]


def clear_policy_cache() -> None:
    global _policy_cache, _policy_cache_mtime, _employee_role_map_cache
    _policy_cache = None
    _policy_cache_mtime = None
    _employee_role_map_cache = None


def get_repeat_offenders(limit: int = 10) -> list[dict]:
    violations = scan_all_policy_violations()
    counts: dict[str, dict] = {}

    for v in violations:
        name = v["employee"]
        if name not in counts:
            counts[name] = {
                "employee": name,
                "department": v.get("department", "-"),
                "violations": 0,
                "severe": 0,
                "split_purchases": 0,
                "total_amount": 0.0,
            }
        counts[name]["violations"] += 1
        counts[name]["total_amount"] += float(v.get("amount") or 0)
        sev = str(v.get("severity") or "Low")
        if sev in ("High", "Severe"):
            counts[name]["severe"] += 1
        if v.get("flag_type") == "split_purchase":
            counts[name]["split_purchases"] += 1

    from services.expenses.guardian import employees_by_name

    meta = employees_by_name()

    ranked = []
    for name, stats in counts.items():
        emp_meta = meta.get(name, {})
        score = float(emp_meta.get("final_score", 80))
        stats["credit_score"] = score
        stats["rank_score"] = (
            stats["violations"] * 3 + stats["severe"] * 5 + stats["split_purchases"] * 8
        )
        ranked.append(stats)

    ranked.sort(key=lambda x: (x["rank_score"], x["violations"]), reverse=True)
    return ranked[:limit]


def merge_flags_with_policy(
    guardian_flags: list[dict], policy_violations: list[dict]
) -> list[dict]:
    """Merge Guardian CSV flags with runtime policy violations; sort by severity then amount."""
    combined = list(guardian_flags)
    seen = {f.get("flag_key") for f in guardian_flags if f.get("flag_key")}

    for v in policy_violations:
        amount = round(float(v.get("amount") or 0), 2)
        date_label = fmt_date(v.get("date"))
        flag_type = v.get("flag_type", "policy_violation")
        emp = str(v.get("employee") or "").strip()
        vend = str(v.get("vendor") or "").strip()
        key = f"{emp}|{vend}|{date_label}|{amount}"
        if key in seen:
            continue
        seen.add(key)
        combined.append(
            {
                "employee": v["employee"],
                "department": v.get("department", "-"),
                "vendor": v.get("vendor", "-"),
                "amount": f"${amount:,.2f}",
                "amount_raw": amount,
                "location": "-",
                "reason": v.get("reason", ""),
                "risk": v.get("severity") or v.get("risk") or "Medium",
                "date": date_label,
                "flag_type": flag_type,
                "flag_key": key,
            }
        )

    def sort_key(item):
        risk = str(item.get("risk") or "Low")
        amt = item.get("amount", "$0")
        try:
            amount_val = float(str(amt).replace("$", "").replace(",", ""))
        except ValueError:
            amount_val = 0
        return (RISK_ORDER.get(risk, 0), amount_val)

    combined.sort(key=sort_key, reverse=True)
    return combined


