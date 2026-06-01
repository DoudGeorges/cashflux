import pandas as pd

import random
import re
from datetime import timedelta

# FILE NAMES

from services.merchants import (
    CATEGORY_AMOUNT_RANGES,
    CATEGORY_WEIGHTS,
    MONTREAL_MERCHANTS,
    SECONDARY_CITY_MERCHANTS,
)
from core.paths import (
    DATA_DIR,
    DEPARTMENT_SUMMARY_PATH,
    EMPLOYEE_SCORES_PATH,
    FLAGGED_TX_PATH,
    ORIGINAL_TX_PATH,
    SCORED_TX_PATH,
)

INPUT_FILE = str(ORIGINAL_TX_PATH)
SCORED_OUTPUT_FILE = str(SCORED_TX_PATH)
SCORES_OUTPUT_FILE = str(EMPLOYEE_SCORES_PATH)
FLAGGED_OUTPUT_FILE = str(FLAGGED_TX_PATH)
DEPARTMENT_OUTPUT_FILE = str(DEPARTMENT_SUMMARY_PATH)
ARCHIVE_INPUT_FILE = str(ORIGINAL_TX_PATH)

# SCORE SETTINGS

STARTING_SCORE = 80
MAX_SCORE = 100
MIN_SCORE = 0

NORMAL_SCORE_INCREASE = 0.05

POINTS_BY_RISK = {"None": 0, "Low": -2, "Medium": -4, "High": -7, "Severe": -11}

RISK_ORDER = {"None": 0, "Low": 1, "Medium": 2, "High": 3, "Severe": 4}

# FAKE EMPLOYEE DATA FOR TESTING

# One department per person  canonical roster (10 employees).
CANONICAL_EMPLOYEES = [
    ("E001", "Sarah Chen", "Marketing"),
    ("E002", "John Miller", "Engineering"),
    ("E003", "Alex Johnson", "Sales"),
    ("E004", "Emma Wilson", "Finance"),
    ("E005", "Daniel Kim", "Operations"),
    ("E006", "Maya Patel", "Human Resources"),
    ("E007", "Lucas Brown", "Product"),
    ("E008", "Olivia Smith", "Customer Success"),
    ("E009", "Noah Garcia", "Marketing"),
    ("E010", "Sophia Lee", "Engineering"),
]


EMPLOYEE_BY_ID = {row[0]: row for row in CANONICAL_EMPLOYEES}
EMPLOYEE_BY_NAME = {row[1]: row for row in CANONICAL_EMPLOYEES}

MONTREAL_LOCATION = ("MONTREAL", "QC", "CAN", "H2X 1Y4")
SECONDARY_CITIES = [
    ("TORONTO", "ON", "CAN", "M5V 2T6"),
    ("LAVAL", "QC", "CAN", "H7T 1C8"),
    ("QUEBEC CITY", "QC", "CAN", "G1R 4P5"),
    ("OTTAWA", "ON", "CAN", "K1P 1J1"),
    ("VANCOUVER", "BC", "CAN", "V6B 1A1"),
]
MONTREAL_SPEND_SHARE = 0.78

PROJECT_BY_DEPARTMENT = {
    "Marketing": "Marketing Campaign Travel",
    "Engineering": "Engineering Site Visit",
    "Sales": "Sales Client Trip",
    "Finance": "Finance Audit Travel",
    "Operations": "Operations Field Visit",
    "Human Resources": "HR Recruiting Trip",
    "Product": "Product Research Trip",
    "Customer Success": "Customer Success Visit",
}

FAKE_APPROVED_LOCATIONS = [
    ("TORONTO", "ON", "CAN"),
    ("MONTREAL", "QC", "CAN"),
    ("VANCOUVER", "BC", "CAN"),
    ("NEW YORK", "NY", "USA"),
    ("CHICAGO", "IL", "USA"),
    ("LOS ANGELES", "CA", "USA"),
    ("BOSTON", "MA", "USA"),
    ("SEATTLE", "WA", "USA"),
]

# IRRELEVANT PURCHASE KEYWORDS

IRRELEVANT_KEYWORDS = [
    "bubble tea",
    "boba",
    "milk tea",
    "chatime",
    "coco",
    "gong cha",
    "kung fu tea",
    "blind box",
    "blind boxes",
    "pop mart",
    "toy",
    "toys",
    "anime",
    "figure",
    "figures",
    "collectible",
    "collectibles",
    "lego",
    "gamestop",
    "game stop",
    "steam",
    "playstation",
    "xbox",
    "nintendo",
    "sephora",
    "luxury",
    "casino",
    "movie",
    "cinema",
    "netflix",
    "spotify",
]


# BASIC HELPERS


def money_to_float(value):
    if pd.isna(value):
        return 0.0

    value = str(value).replace("$", "").replace(",", "").strip()

    try:
        return float(value)
    except ValueError:
        return 0.0


def clean_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def normalize_location(value):
    """
    Standardizes location strings so comparing is easier.
    """
    text = clean_text(value).upper()
    text = re.sub(r"\s+", " ", text)
    return text


def split_allowed_values(value):
    """
    Allows multiple approved cities/countries/states in one cell.

    Examples:
   : "TORONTO"
   : "TORONTO; MONTREAL"
   : "TORONTO | MONTREAL"
   : "ANY"

    Returns a list of normalized values.
    """
    text = normalize_location(value)

    if text == "":
        return []

    if text in ["ANY", "ALL", "*", "N/A", "NA", "NONE"]:
        return ["ANY"]

    parts = re.split(r"[;|,/]+", text)
    parts = [part.strip() for part in parts if part.strip() != ""]

    return parts


def parse_date(value):
    if pd.isna(value):
        return pd.NaT

    # infer format safely
    return pd.to_datetime(value, errors="coerce")


def higher_risk(risk_a, risk_b):
    if RISK_ORDER[risk_a] >= RISK_ORDER[risk_b]:
        return risk_a
    return risk_b


# ADDRESS ADDER

STREET_NAMES = [
    "Main St",
    "King St",
    "Queen St",
    "Market St",
    "Broadway",
    "Park Ave",
    "Elm St",
    "Maple Ave",
    "Oak St",
    "Cedar Rd",
    "Lake Shore Blvd",
    "University Ave",
    "Industrial Pkwy",
    "Commerce Dr",
    "Airport Rd",
    "Victoria St",
    "Saint Laurent Blvd",
    "Sherbrooke St",
    "Yonge St",
    "Front St",
    "Bloor St",
    "Rue Sainte-Catherine",
    "René-Lévesque Blvd",
]

UNIT_TYPES = ["", "", "", "Suite 100", "Unit 12", "Floor 2", "Office 5"]

ADDRESS_COLUMNS = [
    "Merchant Street Address",
    "Merchant Full Address",
    "Approved Street Address",
    "Approved Full Address",
]


def fake_street_address(seed_text):
    """
    Creates a stable fake street address.
    Same seed text = same fake address every time.
    """
    random.seed(seed_text)
    number = random.randint(10, 9999)
    street = random.choice(STREET_NAMES)
    unit = random.choice(UNIT_TYPES)

    if unit:
        return f"{number} {street}, {unit}"

    return f"{number} {street}"


def make_full_address(street, city, state, country, postal=""):
    parts = [
        clean_text(street),
        clean_text(city),
        clean_text(state),
        clean_text(postal),
        clean_text(country),
    ]

    parts = [part for part in parts if part != ""]

    return ", ".join(parts)


def add_specific_addresses_if_needed(df):
    """
    Adds specific fake address columns to transactions_original.csv.

    It keeps the SAME input file name:
        transactions_original.csv

    It does NOT create a new transaction file name.

    Columns added:
   : Merchant Street Address
   : Merchant Full Address
   : Approved Street Address
   : Approved Full Address
    """

    for col in ADDRESS_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    for i, row in df.iterrows():
        merchant_city = clean_text(row.get("Merchant City", ""))
        merchant_state = clean_text(row.get("Merchant State/Province", ""))
        merchant_country = clean_text(row.get("Merchant Country", ""))
        merchant_postal = clean_text(row.get("Merchant Postal Code", ""))
        merchant_name = clean_text(row.get("Merchant Info DBA Name", ""))

        if clean_text(row.get("Merchant Street Address", "")) == "":
            merchant_seed = (
                f"merchant-{merchant_name}-{merchant_city}-"
                f"{merchant_state}-{merchant_country}-{i}"
            )
            df.at[i, "Merchant Street Address"] = fake_street_address(merchant_seed)

        if clean_text(row.get("Merchant Full Address", "")) == "":
            df.at[i, "Merchant Full Address"] = make_full_address(
                df.at[i, "Merchant Street Address"],
                merchant_city,
                merchant_state,
                merchant_country,
                merchant_postal,
            )

        approved_city = clean_text(row.get("Approved City", ""))
        approved_state = clean_text(row.get("Approved State/Province", ""))
        approved_country = clean_text(row.get("Approved Country", ""))

        if normalize_location(approved_city) in [
            "ANY",
            "ALL",
            "*",
        ] or normalize_location(approved_country) in ["ANY", "ALL", "*"]:
            df.at[i, "Approved Street Address"] = "ANY"
            df.at[i, "Approved Full Address"] = "ANY"

        elif approved_city == "" and approved_state == "" and approved_country == "":
            # No approved location data. Leave approved address blank.
            df.at[i, "Approved Street Address"] = ""
            df.at[i, "Approved Full Address"] = ""

        else:
            if clean_text(row.get("Approved Street Address", "")) == "":
                merchant_city = normalize_location(row.get("Merchant City", ""))
                approved_city_norm = normalize_location(approved_city)
                merchant_street = clean_text(row.get("Merchant Street Address", ""))
                if (
                    merchant_street
                    and approved_city_norm == merchant_city
                    and approved_city_norm not in ["", "ANY"]
                ):
                    df.at[i, "Approved Street Address"] = merchant_street
                else:
                    approved_seed = (
                        f"approved-{approved_city}-{approved_state}-{approved_country}-"
                        f"{row.get('Employee ID', '')}-{row.get('Project/Trip Name', '')}"
                    )
                    df.at[i, "Approved Street Address"] = fake_street_address(
                        approved_seed
                    )

            if clean_text(row.get("Approved Full Address", "")) == "":
                df.at[i, "Approved Full Address"] = make_full_address(
                    df.at[i, "Approved Street Address"],
                    approved_city,
                    approved_state,
                    approved_country,
                    "",
                )

    return df


# FAKE DATA ADDERS


def assign_canonical_employees(df):
    """Ensure every row uses one fixed department per employee."""
    if "Employee ID" not in df.columns:
        df.insert(0, "Employee ID", "")
    if "Employee Name" not in df.columns:
        df.insert(1, "Employee Name", "")
    if "Department" not in df.columns:
        df.insert(2, "Department", "")

    for i in range(len(df)):
        existing_id = clean_text(df.at[i, "Employee ID"])
        existing_name = clean_text(df.at[i, "Employee Name"])

        if existing_id in EMPLOYEE_BY_ID:
            employee_id, employee_name, department = EMPLOYEE_BY_ID[existing_id]
        elif existing_name in EMPLOYEE_BY_NAME:
            employee_id, employee_name, department = EMPLOYEE_BY_NAME[existing_name]
        else:
            employee_id, employee_name, department = CANONICAL_EMPLOYEES[
                i % len(CANONICAL_EMPLOYEES)
            ]

        df.at[i, "Employee ID"] = employee_id
        df.at[i, "Employee Name"] = employee_name
        df.at[i, "Department"] = department

        if "Project/Trip Name" in df.columns:
            df.at[i, "Project/Trip Name"] = PROJECT_BY_DEPARTMENT.get(
                department, "General Business Expense"
            )

    return df


def _pick_category(rng):
    roll = rng.random()
    cumulative = 0.0
    for category, weight in CATEGORY_WEIGHTS:
        cumulative += weight
        if roll <= cumulative:
            return category
    return CATEGORY_WEIGHTS[-1][0]


def _pick_merchant(rng, category, city_key):
    """Pick a real merchant for the category in the target city."""
    if city_key == "MONTREAL":
        pool = [m for m in MONTREAL_MERCHANTS if m["category"] == category]
        if not pool:
            pool = [m for m in MONTREAL_MERCHANTS]
    else:
        pool = [
            m
            for m in SECONDARY_CITY_MERCHANTS.get(city_key, [])
            if m["category"] == category
        ]
        if not pool:
            pool = list(SECONDARY_CITY_MERCHANTS.get(city_key, MONTREAL_MERCHANTS))
    return rng.choice(pool)


def _realistic_amount(rng, category, existing_amount):
    """Nudge amounts into a plausible range for the merchant category."""
    low, high = CATEGORY_AMOUNT_RANGES.get(category, (10, 200))
    amount = float(existing_amount or 0)
    if amount <= 0:
        return round(rng.uniform(low, high), 2)
    if amount < low:
        return round(rng.uniform(low, min(high, low * 1.8)), 2)
    if amount > high * 2.0:
        return round(rng.uniform(high * 0.75, high * 1.15), 2)
    return round(amount, 2)


def _merchant_description(merchant):
    return f"{merchant['name']} {merchant['city']} {merchant['state']}"


def assign_real_merchants(df, montreal_share=MONTREAL_SPEND_SHARE):
    """Replace fake merchants with real businesses, addresses, and expense categories."""
    rng = random.Random(4242)
    category_rng = random.Random(5151)

    for col in ADDRESS_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    if "Transaction Category" in df.columns:
        df["Transaction Category"] = df["Transaction Category"].astype(object)
    if "Merchant Category Code" in df.columns:
        df["Merchant Category Code"] = df["Merchant Category Code"].astype(object)

    for i in range(len(df)):
        use_montreal = rng.random() < montreal_share
        if use_montreal:
            city_key = "MONTREAL"
        else:
            city_key = rng.choice(list(SECONDARY_CITY_MERCHANTS.keys()))

        category = _pick_category(category_rng)
        merchant = _pick_merchant(rng, category, city_key)
        category = merchant["category"]

        street = merchant["street"]
        city = merchant["city"]
        state = merchant["state"]
        country = merchant["country"]
        postal = merchant["postal"]
        full_address = make_full_address(street, city, state, country, postal)

        df.at[i, "Merchant Info DBA Name"] = merchant["name"]
        df.at[i, "Merchant Category Code"] = merchant["mcc"]
        df.at[i, "Transaction Category"] = category
        df.at[i, "Transaction Description"] = _merchant_description(merchant)
        df.at[i, "Merchant City"] = city
        df.at[i, "Merchant State/Province"] = state
        df.at[i, "Merchant Country"] = country
        if "Merchant Postal Code" in df.columns:
            df.at[i, "Merchant Postal Code"] = postal
        df.at[i, "Merchant Street Address"] = street
        df.at[i, "Merchant Full Address"] = full_address

        if (
            "Transaction Amount" in df.columns
            and str(df.at[i, "Debit or Credit"]).lower() == "debit"
        ):
            existing = money_to_float(df.at[i, "Transaction Amount"])
            df.at[i, "Transaction Amount"] = _realistic_amount(rng, category, existing)

    return df


def add_fake_geofence_if_needed(df, force=False):
    """
    Adds project/trip and approved geofence columns if they are missing.

    Geofencing columns:
   : Project/Trip Name
   : Approved City
   : Approved State/Province
   : Approved Country
   : Approved Start Date
   : Approved End Date

    For testing:
   : Most rows are approved for the merchant's actual location
   : Some rows are assigned a different approved location to create geofence flags
   : Some rows are marked ANY, meaning location is unrestricted
    """

    geofence_cols = [
        "Project/Trip Name",
        "Approved City",
        "Approved State/Province",
        "Approved Country",
        "Approved Start Date",
        "Approved End Date",
    ]

    if not force and all(col in df.columns for col in geofence_cols):
        return df

    random.seed(3030)

    project_names = []
    approved_cities = []
    approved_states = []
    approved_countries = []
    approved_start_dates = []
    approved_end_dates = []

    for _, row in df.iterrows():
        department = clean_text(row.get("Department", ""))
        project_name = PROJECT_BY_DEPARTMENT.get(department, "General Business Expense")

        merchant_city = normalize_location(row.get("Merchant City", ""))
        merchant_state = normalize_location(row.get("Merchant State/Province", ""))
        merchant_country = normalize_location(row.get("Merchant Country", ""))

        transaction_date = parse_date(row.get("Transaction Date", ""))

        roll = random.random()

        # 85%: approved location equals actual merchant location, so it passes.
        if roll < 0.85 and merchant_city != "" and merchant_country != "":
            approved_city = merchant_city
            approved_state = merchant_state
            approved_country = merchant_country

        # 8%: unrestricted approved location. This is useful for remote/general business purchases.
        elif roll < 0.93:
            approved_city = "ANY"
            approved_state = "ANY"
            approved_country = "ANY"

        # 7%: intentionally different approved location, so geofencing can catch it.
        else:
            approved_city, approved_state, approved_country = random.choice(
                FAKE_APPROVED_LOCATIONS
            )

            # Try not to accidentally pick the same location.
            if approved_city == merchant_city and approved_country == merchant_country:
                approved_city, approved_state, approved_country = random.choice(
                    FAKE_APPROVED_LOCATIONS
                )

        # Date range:
        # If transaction date exists, most ranges include transaction date.
        # A small amount will be outside the approved dates to test time-based geofencing.
        if pd.isna(transaction_date):
            start_date = ""
            end_date = ""
        else:
            if random.random() < 0.95:
                start_date = (transaction_date - timedelta(days=7)).strftime("%Y-%m-%d")
                end_date = (transaction_date + timedelta(days=7)).strftime("%Y-%m-%d")
            else:
                start_date = (transaction_date + timedelta(days=7)).strftime("%Y-%m-%d")
                end_date = (transaction_date + timedelta(days=14)).strftime("%Y-%m-%d")

        project_names.append(project_name)
        approved_cities.append(approved_city)
        approved_states.append(approved_state)
        approved_countries.append(approved_country)
        approved_start_dates.append(start_date)
        approved_end_dates.append(end_date)

    # Add only missing columns. If your teammate already has one, it will be preserved.
    insert_position = 3 if "Department" in df.columns else 0

    if "Project/Trip Name" not in df.columns:
        df.insert(insert_position, "Project/Trip Name", project_names)
        insert_position += 1

    if "Approved City" not in df.columns:
        df.insert(insert_position, "Approved City", approved_cities)
        insert_position += 1

    if "Approved State/Province" not in df.columns:
        df.insert(insert_position, "Approved State/Province", approved_states)
        insert_position += 1

    if "Approved Country" not in df.columns:
        df.insert(insert_position, "Approved Country", approved_countries)
        insert_position += 1

    if "Approved Start Date" not in df.columns:
        df.insert(insert_position, "Approved Start Date", approved_start_dates)
        insert_position += 1

    if "Approved End Date" not in df.columns:
        df.insert(insert_position, "Approved End Date", approved_end_dates)
    else:
        df["Project/Trip Name"] = project_names
        df["Approved City"] = approved_cities
        df["Approved State/Province"] = approved_states
        df["Approved Country"] = approved_countries
        df["Approved Start Date"] = approved_start_dates
        df["Approved End Date"] = approved_end_dates

    return df


# PRICE / KEYWORD CHECKING


def add_group_statistics(df):
    df["merchant_median"] = df.groupby("Merchant Info DBA Name")[
        "Amount Clean"
    ].transform("median")
    df["merchant_count"] = df.groupby("Merchant Info DBA Name")[
        "Amount Clean"
    ].transform("count")
    df["merchant_q1"] = df.groupby("Merchant Info DBA Name")["Amount Clean"].transform(
        lambda x: x.quantile(0.25)
    )
    df["merchant_q3"] = df.groupby("Merchant Info DBA Name")["Amount Clean"].transform(
        lambda x: x.quantile(0.75)
    )
    df["merchant_p90"] = df.groupby("Merchant Info DBA Name")["Amount Clean"].transform(
        lambda x: x.quantile(0.90)
    )
    df["merchant_p95"] = df.groupby("Merchant Info DBA Name")["Amount Clean"].transform(
        lambda x: x.quantile(0.95)
    )
    df["merchant_iqr"] = df["merchant_q3"] - df["merchant_q1"]

    df["mcc_median"] = df.groupby("Merchant Category Code")["Amount Clean"].transform(
        "median"
    )
    df["mcc_count"] = df.groupby("Merchant Category Code")["Amount Clean"].transform(
        "count"
    )
    df["mcc_q1"] = df.groupby("Merchant Category Code")["Amount Clean"].transform(
        lambda x: x.quantile(0.25)
    )
    df["mcc_q3"] = df.groupby("Merchant Category Code")["Amount Clean"].transform(
        lambda x: x.quantile(0.75)
    )
    df["mcc_p90"] = df.groupby("Merchant Category Code")["Amount Clean"].transform(
        lambda x: x.quantile(0.90)
    )
    df["mcc_p95"] = df.groupby("Merchant Category Code")["Amount Clean"].transform(
        lambda x: x.quantile(0.95)
    )
    df["mcc_iqr"] = df["mcc_q3"] - df["mcc_q1"]

    df["global_median"] = df["Amount Clean"].median()
    df["global_q1"] = df["Amount Clean"].quantile(0.25)
    df["global_q3"] = df["Amount Clean"].quantile(0.75)
    df["global_p90"] = df["Amount Clean"].quantile(0.90)
    df["global_p95"] = df["Amount Clean"].quantile(0.95)
    df["global_iqr"] = df["global_q3"] - df["global_q1"]

    return df


def choose_baseline(row):
    if row["merchant_count"] >= 8:
        return {
            "source": "same merchant",
            "median": row["merchant_median"],
            "q3": row["merchant_q3"],
            "p90": row["merchant_p90"],
            "p95": row["merchant_p95"],
            "iqr": row["merchant_iqr"],
        }

    if row["mcc_count"] >= 30:
        return {
            "source": "same merchant category",
            "median": row["mcc_median"],
            "q3": row["mcc_q3"],
            "p90": row["mcc_p90"],
            "p95": row["mcc_p95"],
            "iqr": row["mcc_iqr"],
        }

    return {
        "source": "all transactions",
        "median": row["global_median"],
        "q3": row["global_q3"],
        "p90": row["global_p90"],
        "p95": row["global_p95"],
        "iqr": row["global_iqr"],
    }


def find_irrelevant_keyword(row):
    text_parts = [
        str(row.get("Merchant Info DBA Name", "")),
        str(row.get("Transaction Description", "")),
        str(row.get("Merchant City", "")),
    ]

    combined_text = " ".join(text_parts).lower()

    for keyword in IRRELEVANT_KEYWORDS:
        if keyword in combined_text:
            return keyword

    return ""


def irrelevant_risk_level(amount):
    if amount >= 300:
        return "Severe"
    if amount >= 100:
        return "High"
    if amount >= 30:
        return "Medium"
    return "Low"


def pricing_risk(row):
    amount = row["Amount Clean"]
    baseline = choose_baseline(row)

    median = float(baseline["median"])
    q3 = float(baseline["q3"])
    p90 = float(baseline["p90"])
    p95 = float(baseline["p95"])
    iqr = float(baseline["iqr"])
    source = baseline["source"]

    if median <= 0:
        return {
            "risk_level": "None",
            "reason": "Not enough data to compare.",
            "typical_amount": 0,
            "amount_ratio": 0,
            "baseline_used": source,
        }

    iqr = max(iqr, median * 0.20, 1)

    amount_ratio = amount / median
    difference = amount - median

    severe = (
        amount >= max(p95 * 1.75, q3 + 4 * iqr)
        and amount_ratio >= 4
        and difference >= 100
    )

    high = (
        amount >= max(p95 * 1.25, q3 + 3 * iqr)
        and amount_ratio >= 3
        and difference >= 50
    )

    medium = (
        amount >= max(p90 * 1.20, q3 + 2 * iqr)
        and amount_ratio >= 2.5
        and difference >= 20
    )

    low = amount >= max(p90, q3 + 1.5 * iqr) and amount_ratio >= 2 and difference >= 5

    small_item_unusual = median <= 10 and amount_ratio >= 2 and difference >= 3

    if severe:
        risk_level = "Severe"
    elif high:
        risk_level = "High"
    elif medium:
        risk_level = "Medium"
    elif low or small_item_unusual:
        risk_level = "Low"
    else:
        risk_level = "None"

    if risk_level == "None":
        reason = "Reasonable price compared with similar transactions."
    else:
        reason = (
            f"Amount is {amount_ratio:.1f}x higher than the typical "
            f"${median:.2f}, based on {source}."
        )

    return {
        "risk_level": risk_level,
        "reason": reason,
        "typical_amount": round(median, 2),
        "amount_ratio": round(amount_ratio, 2),
        "baseline_used": source,
    }


# GEOFENCING


def geofence_risk(row):
    """
    Geofencing checks all common cases:

    1. No approved location set -> no geofence restriction
    2. Approved City/Country/State set to ANY -> no restriction for that field
    3. Approved country only -> checks country only
    4. Approved city + country -> checks city and country
    5. Approved state/province -> checks state/province if present
    6. Multiple approved values -> supports semicolon/comma/pipe-separated values
    7. Missing merchant location -> Low risk because it cannot verify location
    8. Country mismatch -> High risk
    9. City/state mismatch -> Medium risk
    10. Transaction outside approved start/end dates -> Medium risk
    """

    merchant_city = normalize_location(row.get("Merchant City", ""))
    merchant_state = normalize_location(row.get("Merchant State/Province", ""))
    merchant_country = normalize_location(row.get("Merchant Country", ""))

    approved_cities = split_allowed_values(row.get("Approved City", ""))
    approved_states = split_allowed_values(row.get("Approved State/Province", ""))
    approved_countries = split_allowed_values(row.get("Approved Country", ""))

    approved_start = parse_date(row.get("Approved Start Date", ""))
    approved_end = parse_date(row.get("Approved End Date", ""))
    transaction_date = parse_date(row.get("Transaction Date", ""))

    # If there is no geofence info at all, no restriction.
    no_location_restriction = (
        len(approved_cities) == 0
        and len(approved_states) == 0
        and len(approved_countries) == 0
    )

    no_date_restriction = pd.isna(approved_start) and pd.isna(approved_end)

    if no_location_restriction and no_date_restriction:
        return {
            "risk_level": "None",
            "reason": "",
            "geo_flagged": False,
            "geo_reason": "",
            "approved_location": "No restriction",
            "merchant_location": f"{merchant_city}, {merchant_state}, {merchant_country}".strip(
                ", "
            ),
            "geofence_status": "No restriction",
        }

    reasons = []
    risk = "None"

    # If location restriction exists but merchant location is missing
    if not no_location_restriction:
        if merchant_city == "" and merchant_state == "" and merchant_country == "":
            risk = higher_risk(risk, "Low")
            reasons.append(
                "Merchant location is missing, so geofence cannot be verified."
            )

    # Country check
    if len(approved_countries) > 0 and "ANY" not in approved_countries:
        if merchant_country == "":
            risk = higher_risk(risk, "Low")
            reasons.append("Merchant country is missing.")
        elif merchant_country not in approved_countries:
            risk = higher_risk(risk, "High")
            reasons.append(
                f"Country mismatch: merchant country is {merchant_country}, "
                f"approved country is {', '.join(approved_countries)}."
            )

    # State/province check
    if len(approved_states) > 0 and "ANY" not in approved_states:
        if merchant_state == "":
            risk = higher_risk(risk, "Low")
            reasons.append("Merchant state/province is missing.")
        elif merchant_state not in approved_states:
            risk = higher_risk(risk, "Medium")
            reasons.append(
                f"State/province mismatch: merchant state/province is {merchant_state}, "
                f"approved state/province is {', '.join(approved_states)}."
            )

    # City check
    if len(approved_cities) > 0 and "ANY" not in approved_cities:
        if merchant_city == "":
            risk = higher_risk(risk, "Low")
            reasons.append("Merchant city is missing.")
        elif merchant_city not in approved_cities:
            risk = higher_risk(risk, "Medium")
            reasons.append(
                f"City mismatch: merchant city is {merchant_city}, "
                f"approved city is {', '.join(approved_cities)}."
            )

    # Date/time fence check
    if not no_date_restriction:
        if pd.isna(transaction_date):
            risk = higher_risk(risk, "Low")
            reasons.append(
                "Transaction date is missing or invalid, so approved travel dates cannot be verified."
            )
        else:
            if not pd.isna(approved_start) and transaction_date < approved_start:
                risk = higher_risk(risk, "Medium")
                reasons.append(
                    f"Transaction date {transaction_date.date()} is before approved start date {approved_start.date()}."
                )

            if not pd.isna(approved_end) and transaction_date > approved_end:
                risk = higher_risk(risk, "Medium")
                reasons.append(
                    f"Transaction date {transaction_date.date()} is after approved end date {approved_end.date()}."
                )

    approved_location = (
        f"City: {clean_text(row.get('Approved City', ''))}; "
        f"State/Province: {clean_text(row.get('Approved State/Province', ''))}; "
        f"Country: {clean_text(row.get('Approved Country', ''))}; "
        f"Dates: {clean_text(row.get('Approved Start Date', ''))} to {clean_text(row.get('Approved End Date', ''))}"
    )

    merchant_location = f"City: {merchant_city}; State/Province: {merchant_state}; Country: {merchant_country}"

    if risk == "None":
        return {
            "risk_level": "None",
            "reason": "",
            "geo_flagged": False,
            "geo_reason": "",
            "approved_location": approved_location,
            "merchant_location": merchant_location,
            "geofence_status": "Within approved geofence",
        }

    return {
        "risk_level": risk,
        "reason": " ".join(reasons),
        "geo_flagged": True,
        "geo_reason": " ".join(reasons),
        "approved_location": approved_location,
        "merchant_location": merchant_location,
        "geofence_status": "Outside approved geofence",
    }


# MAIN TRANSACTION DETECTION


def detect_transaction(row):
    amount = row["Amount Clean"]
    debit_or_credit = str(row.get("Debit or Credit", "")).lower()

    if debit_or_credit == "credit":
        return pd.Series(
            {
                "status": "Credit/Refund",
                "flagged": False,
                "flag_reason": "Credit/refund transaction. No score change.",
                "risk_level": "None",
                "score_change": 0,
                "typical_amount": 0,
                "amount_ratio": 0,
                "baseline_used": "credit/refund",
                "irrelevant_keyword": "",
                "geo_flagged": False,
                "geo_reason": "",
                "approved_location": "",
                "merchant_location": "",
                "geofence_status": "Credit/refund skipped",
            }
        )

    keyword = find_irrelevant_keyword(row)
    price_result = pricing_risk(row)
    geo_result = geofence_risk(row)

    price_risk = price_result["risk_level"]
    irrelevant_risk = "None"
    credit_reasons = []

    if keyword:
        irrelevant_risk = irrelevant_risk_level(amount)
        credit_reasons.append(
            f"Possible personal or irrelevant purchase detected: '{keyword}'."
        )

    if price_risk != "None":
        credit_reasons.append(price_result["reason"])

    # Credit score uses the original Guardian method: pricing + irrelevant purchases only.
    credit_risk = higher_risk(price_risk, irrelevant_risk)

    if credit_risk == "None":
        return pd.Series(
            {
                "status": "Normal",
                "flagged": False,
                "flag_reason": "Reasonable expense. Score increased slightly.",
                "risk_level": "None",
                "score_change": NORMAL_SCORE_INCREASE,
                "typical_amount": price_result["typical_amount"],
                "amount_ratio": price_result["amount_ratio"],
                "baseline_used": price_result["baseline_used"],
                "irrelevant_keyword": "",
                "geo_flagged": geo_result["geo_flagged"],
                "geo_reason": geo_result["geo_reason"],
                "approved_location": geo_result["approved_location"],
                "merchant_location": geo_result["merchant_location"],
                "geofence_status": geo_result["geofence_status"],
            }
        )

    return pd.Series(
        {
            "status": "Flagged",
            "flagged": True,
            "flag_reason": " ".join(credit_reasons),
            "risk_level": credit_risk,
            "score_change": POINTS_BY_RISK[credit_risk],
            "typical_amount": price_result["typical_amount"],
            "amount_ratio": price_result["amount_ratio"],
            "baseline_used": price_result["baseline_used"],
            "irrelevant_keyword": keyword,
            "geo_flagged": geo_result["geo_flagged"],
            "geo_reason": geo_result["geo_reason"],
            "approved_location": geo_result["approved_location"],
            "merchant_location": geo_result["merchant_location"],
            "geofence_status": geo_result["geofence_status"],
        }
    )


# SUMMARIES


def create_department_summary(df):
    rows = []

    for department, group in df.groupby("Department"):
        rows.append(
            {
                "department": department,
                "total_spent": round(float(group["Spend Amount"].sum()), 2),
                "transaction_count": len(group),
                "reasonable_transactions": int((group["status"] == "Normal").sum()),
                "flagged_transactions": int(group["flagged"].sum()),
                "geofence_flags": int(group["geo_flagged"].sum()),
                "average_score_after_transactions": round(
                    float(group["score_after"].mean()), 2
                ),
            }
        )

    department_df = pd.DataFrame(rows)
    department_df = department_df.sort_values(by="total_spent", ascending=False)

    return department_df


# Columns produced by scoring  stripped when writing transactions_original.csv
ORIGINAL_COLUMNS_TO_REMOVE = [
    "Amount Clean",
    "Spend Amount",
    "employee_total_spent",
    "department_total_spent",
    "merchant_median",
    "merchant_count",
    "merchant_q1",
    "merchant_q3",
    "merchant_p90",
    "merchant_p95",
    "merchant_iqr",
    "mcc_median",
    "mcc_count",
    "mcc_q1",
    "mcc_q3",
    "mcc_p90",
    "mcc_p95",
    "mcc_iqr",
    "global_median",
    "global_q1",
    "global_q3",
    "global_p90",
    "global_p95",
    "global_iqr",
    "status",
    "flagged",
    "flag_reason",
    "risk_level",
    "score_change",
    "typical_amount",
    "amount_ratio",
    "baseline_used",
    "irrelevant_keyword",
    "score_after",
    "geo_flagged",
    "geo_reason",
    "approved_location",
    "merchant_location",
    "geofence_status",
]


def rescore_transactions(df):
    """Score all transaction rows and build summary DataFrames."""
    df = df.copy()

    df["Amount Clean"] = df["Transaction Amount"].apply(money_to_float)

    df["Spend Amount"] = df.apply(
        lambda row: (
            row["Amount Clean"]
            if str(row.get("Debit or Credit", "")).lower() == "debit"
            else 0
        ),
        axis=1,
    )

    df["employee_total_spent"] = (
        df.groupby("Employee ID")["Spend Amount"].transform("sum").round(2)
    )

    df["department_total_spent"] = (
        df.groupby("Department")["Spend Amount"].transform("sum").round(2)
    )

    df = add_group_statistics(df)

    results = df.apply(detect_transaction, axis=1)
    df = pd.concat([df, results], axis=1)

    df["score_after"] = float(STARTING_SCORE)

    current_scores = {}

    for index, row in df.iterrows():
        employee_id = row["Employee ID"]

        if employee_id not in current_scores:
            current_scores[employee_id] = STARTING_SCORE

        current_scores[employee_id] += float(row["score_change"])
        current_scores[employee_id] = min(
            MAX_SCORE, max(MIN_SCORE, current_scores[employee_id])
        )

        df.at[index, "score_after"] = float(round(current_scores[employee_id], 2))

    score_rows = []

    for employee_id, group in df.groupby("Employee ID"):
        employee_name = group["Employee Name"].iloc[0]
        department = group["Department"].iloc[0]

        final_score = round(float(group["score_after"].iloc[-1]), 2)
        flagged_count = int(group["flagged"].sum())
        geo_flag_count = int(group["geo_flagged"].sum())
        normal_count = int((group["status"] == "Normal").sum())
        total_score_change = round(float(group["score_change"].sum()), 2)
        total_spent = round(float(group["Spend Amount"].sum()), 2)

        flagged_group = group[group["flagged"] == True]  # noqa: E712

        if flagged_count == 0:
            summary = (
                f"{normal_count} reasonable transaction(s). "
                f"Total spent: ${total_spent:,.2f}. "
                f"Final score is {final_score}/100."
            )
        else:
            most_common_risk = flagged_group["risk_level"].value_counts().idxmax()
            irrelevant_count = int((flagged_group["irrelevant_keyword"] != "").sum())

            summary = (
                f"{flagged_count} flagged transaction(s), mostly {most_common_risk} risk. "
                f"{irrelevant_count} possible irrelevant purchase(s). "
                f"Total spent: ${total_spent:,.2f}. "
                f"Final score is {final_score}/100."
            )

        score_rows.append(
            {
                "employee_id": employee_id,
                "employee_name": employee_name,
                "department": department,
                "starting_score": STARTING_SCORE,
                "final_score": final_score,
                "total_score_change": total_score_change,
                "total_spent": total_spent,
                "reasonable_transactions": normal_count,
                "flagged_transactions": flagged_count,
                "geofence_flags": geo_flag_count,
                "one_sentence_summary": summary,
            }
        )

    scores_df = pd.DataFrame(score_rows)
    scores_df = scores_df.sort_values(by="final_score", ascending=False)

    flagged_df = df[df["flagged"] == True].copy()  # noqa: E712

    try:
        from services.policy import (
            check_transaction_policy,
            detect_split_purchases,
            load_policy_rules,
        )

        rules = load_policy_rules()
        policy_rows = []
        for idx, row in df.iterrows():
            for v in check_transaction_policy(row, rules):
                policy_rows.append(
                    {
                        **row.to_dict(),
                        "flagged": True,
                        "flag_reason": v["reason"],
                        "risk_level": v["severity"],
                        "flag_type": v.get("flag_type", "policy_violation"),
                        "status": "Flagged",
                        "score_change": POINTS_BY_RISK.get(v["severity"], -4),
                    }
                )

        split_flags = detect_split_purchases(df, rules)
        split_indices = set()
        for sf in split_flags:
            for tid in sf.get("transaction_ids") or []:
                try:
                    split_indices.add(int(tid))
                except ValueError:
                    pass
        for idx in split_indices:
            if idx in df.index and idx not in flagged_df.index:
                row = df.loc[idx].copy()
                matching = next(
                    (
                        s
                        for s in split_flags
                        if str(idx) in (s.get("transaction_ids") or [])
                    ),
                    None,
                )
                reason = matching["reason"] if matching else "Split purchase detected"
                policy_rows.append(
                    {
                        **row.to_dict(),
                        "flagged": True,
                        "flag_reason": reason,
                        "risk_level": "Severe",
                        "flag_type": "split_purchase",
                        "status": "Flagged",
                        "score_change": -10,
                    }
                )

        if policy_rows:
            policy_df = pd.DataFrame(policy_rows)
            if "flag_type" not in flagged_df.columns:
                flagged_df["flag_type"] = "guardian"
            flagged_df = pd.concat([flagged_df, policy_df], ignore_index=True)
            flagged_df = flagged_df.drop_duplicates(
                subset=[
                    "Employee ID",
                    "Transaction Date",
                    "Merchant Info DBA Name",
                    "Amount Clean",
                ],
                keep="first",
            )
    except ImportError:
        pass

    department_df = create_department_summary(df)
    return df, scores_df, flagged_df, department_df


def save_transaction_outputs(df, scores_df, flagged_df, department_df, paths=None):
    """Write scored CSV, summaries, and base original CSV."""
    if paths is None:
        try:
            from services.company import get_company_paths

            paths = get_company_paths()
        except ImportError:
            paths = None

    if paths is not None:
        paths.root.mkdir(parents=True, exist_ok=True)
        df.to_csv(paths.scored_tx, index=False)
        scores_df.to_csv(paths.employee_scores, index=False)
        flagged_df.to_csv(paths.flagged_tx, index=False)
        department_df.to_csv(paths.department_summary, index=False)
        df_original_columns = [
            col for col in df.columns if col not in ORIGINAL_COLUMNS_TO_REMOVE
        ]
        df[df_original_columns].to_csv(paths.original_tx, index=False)
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(SCORED_OUTPUT_FILE, index=False)
    scores_df.to_csv(SCORES_OUTPUT_FILE, index=False)
    flagged_df.to_csv(FLAGGED_OUTPUT_FILE, index=False)
    department_df.to_csv(DEPARTMENT_OUTPUT_FILE, index=False)
    df_original_columns = [
        col for col in df.columns if col not in ORIGINAL_COLUMNS_TO_REMOVE
    ]
    df[df_original_columns].to_csv(ARCHIVE_INPUT_FILE, index=False)


# MAIN PROGRAM


def main(company_slug=None):
    from services.company import (
        DEFAULT_COMPANY_SLUG,
        ensure_company_data,
        migrate_legacy_data_to_default_company,
        set_company_context,
    )

    slug = company_slug or DEFAULT_COMPANY_SLUG
    migrate_legacy_data_to_default_company()
    company_paths = ensure_company_data(0, slug)
    set_company_context(0, slug)
    input_path = company_paths.original_tx

    if not input_path.exists():
        raise FileNotFoundError(f"Cannot find {input_path}.")

    df = pd.read_csv(input_path)

    df = assign_canonical_employees(df)
    df = assign_real_merchants(df)
    df = add_fake_geofence_if_needed(df, force=True)
    df = add_specific_addresses_if_needed(df)

    required_columns = [
        "Transaction Amount",
        "Merchant Info DBA Name",
        "Merchant Category Code",
        "Debit or Credit",
    ]

    for col in required_columns:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    df, scores_df, flagged_df, department_df = rescore_transactions(df)
    save_transaction_outputs(
        df, scores_df, flagged_df, department_df, paths=company_paths
    )

    print("Done.")
    print(f"Read: {input_path}")
    print(f"Created/updated: {company_paths.scored_tx}")
    print(f"Created/updated: {company_paths.employee_scores}")
    print(f"Created/updated: {company_paths.flagged_tx}")
    print(f"Created/updated: {company_paths.department_summary}")
    print(f"Total transactions: {len(df)}")
    print(f"Flagged transactions: {int(df['flagged'].sum())}")
    print(f"Geofence flags: {int(df['geo_flagged'].sum())}")


if __name__ == "__main__":
    import sys

    slug = None
    if len(sys.argv) > 1:
        slug = sys.argv[1]
    main(company_slug=slug)

