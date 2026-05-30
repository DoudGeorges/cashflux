import pandas as pd
from pathlib import Path
import random

# ============================================================
# FILE NAMES
# ============================================================

INPUT_FILE = "transactions_original.csv"
SCORED_OUTPUT_FILE = "transactions_scored.csv"
SCORES_OUTPUT_FILE = "employee_scores_summary.csv"
FLAGGED_OUTPUT_FILE = "flagged_transactions.csv"
DEPARTMENT_OUTPUT_FILE = "department_summary.csv"

# ============================================================
# SCORE SETTINGS
# ============================================================

STARTING_SCORE = 80
MAX_SCORE = 100
MIN_SCORE = 0

NORMAL_SCORE_INCREASE = 0.25

POINTS_BY_RISK = {
    "None": 0,
    "Low": -1,
    "Medium": -3,
    "High": -6,
    "Severe": -10
}

RISK_ORDER = {
    "None": 0,
    "Low": 1,
    "Medium": 2,
    "High": 3,
    "Severe": 4
}

# ============================================================
# FAKE EMPLOYEE DATA FOR TESTING
# ============================================================

FAKE_EMPLOYEES = [
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
    ("E011", "Ethan Nguyen", "Sales"),
    ("E012", "Ava Martinez", "Finance"),
    ("E013", "Liam Wang", "Operations"),
    ("E014", "Isabella Davis", "Human Resources"),
    ("E015", "Mason Clark", "Product"),
    ("E016", "Mia Thompson", "Customer Success"),
    ("E017", "James Anderson", "Marketing"),
    ("E018", "Charlotte Moore", "Engineering"),
    ("E019", "Benjamin Taylor", "Sales"),
    ("E020", "Amelia White", "Finance"),
    ("E021", "Henry Harris", "Operations"),
    ("E022", "Harper Martin", "Human Resources"),
    ("E023", "Jack Lewis", "Product"),
    ("E024", "Evelyn Young", "Customer Success"),
    ("E025", "Michael Walker", "Marketing"),
    ("E026", "Abigail Hall", "Engineering"),
    ("E027", "William Allen", "Sales"),
    ("E028", "Emily King", "Finance"),
    ("E029", "Jacob Wright", "Operations"),
    ("E030", "Ella Scott", "Human Resources"),
    ("E031", "Logan Green", "Product"),
    ("E032", "Grace Baker", "Customer Success"),
    ("E033", "Sebastian Adams", "Marketing"),
    ("E034", "Chloe Nelson", "Engineering"),
    ("E035", "Alexander Carter", "Sales"),
    ("E036", "Lily Mitchell", "Finance"),
    ("E037", "Owen Perez", "Operations"),
    ("E038", "Zoey Roberts", "Human Resources"),
    ("E039", "Matthew Turner", "Product"),
    ("E040", "Nora Phillips", "Customer Success"),
    ("E041", "Ryan Campbell", "Marketing"),
    ("E042", "Sofia Parker", "Engineering"),
    ("E043", "David Evans", "Sales"),
    ("E044", "Victoria Edwards", "Finance"),
    ("E045", "Joseph Collins", "Operations"),
    ("E046", "Aria Stewart", "Human Resources"),
    ("E047", "Samuel Sanchez", "Product"),
    ("E048", "Layla Morris", "Customer Success"),
    ("E049", "Christopher Rogers", "Marketing"),
    ("E050", "Scarlett Reed", "Engineering"),
]

# ============================================================
# IRRELEVANT PURCHASE KEYWORDS
# ============================================================

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
    "spotify"
]


def money_to_float(value):
    if pd.isna(value):
        return 0.0

    value = str(value).replace("$", "").replace(",", "").strip()

    try:
        return float(value)
    except ValueError:
        return 0.0


def add_fake_employees_if_needed(df):
    """
    Adds Employee ID, Employee Name, and Department only if they are missing.
    This fixed version will NOT crash if some/all columns already exist.
    """

    # If all three already exist, do nothing.
    if (
        "Employee ID" in df.columns and
        "Employee Name" in df.columns and
        "Department" in df.columns
    ):
        return df

    random.seed(2026)

    fake_ids = []
    fake_names = []
    fake_departments = []

    for _ in range(len(df)):
        employee_id, employee_name, department = random.choice(FAKE_EMPLOYEES)
        fake_ids.append(employee_id)
        fake_names.append(employee_name)
        fake_departments.append(department)

    # Only add missing columns. Do not insert a column that already exists.
    if "Employee ID" not in df.columns:
        df.insert(0, "Employee ID", fake_ids)

    if "Employee Name" not in df.columns:
        insert_position = 1 if "Employee ID" in df.columns else 0
        df.insert(insert_position, "Employee Name", fake_names)

    if "Department" not in df.columns:
        insert_position = 2 if "Employee ID" in df.columns and "Employee Name" in df.columns else 0
        df.insert(insert_position, "Department", fake_departments)

    # If a column exists but has blanks, fill them.
    df["Employee ID"] = df["Employee ID"].fillna("")
    df["Employee Name"] = df["Employee Name"].fillna("")
    df["Department"] = df["Department"].fillna("")

    for i in range(len(df)):
        employee_id, employee_name, department = FAKE_EMPLOYEES[i % len(FAKE_EMPLOYEES)]

        if str(df.at[i, "Employee ID"]).strip() == "":
            df.at[i, "Employee ID"] = employee_id

        if str(df.at[i, "Employee Name"]).strip() == "":
            df.at[i, "Employee Name"] = employee_name

        if str(df.at[i, "Department"]).strip() == "":
            df.at[i, "Department"] = department

    return df


def add_group_statistics(df):
    df["merchant_median"] = df.groupby("Merchant Info DBA Name")["Amount Clean"].transform("median")
    df["merchant_count"] = df.groupby("Merchant Info DBA Name")["Amount Clean"].transform("count")
    df["merchant_q1"] = df.groupby("Merchant Info DBA Name")["Amount Clean"].transform(lambda x: x.quantile(0.25))
    df["merchant_q3"] = df.groupby("Merchant Info DBA Name")["Amount Clean"].transform(lambda x: x.quantile(0.75))
    df["merchant_p90"] = df.groupby("Merchant Info DBA Name")["Amount Clean"].transform(lambda x: x.quantile(0.90))
    df["merchant_p95"] = df.groupby("Merchant Info DBA Name")["Amount Clean"].transform(lambda x: x.quantile(0.95))
    df["merchant_iqr"] = df["merchant_q3"] - df["merchant_q1"]

    df["mcc_median"] = df.groupby("Merchant Category Code")["Amount Clean"].transform("median")
    df["mcc_count"] = df.groupby("Merchant Category Code")["Amount Clean"].transform("count")
    df["mcc_q1"] = df.groupby("Merchant Category Code")["Amount Clean"].transform(lambda x: x.quantile(0.25))
    df["mcc_q3"] = df.groupby("Merchant Category Code")["Amount Clean"].transform(lambda x: x.quantile(0.75))
    df["mcc_p90"] = df.groupby("Merchant Category Code")["Amount Clean"].transform(lambda x: x.quantile(0.90))
    df["mcc_p95"] = df.groupby("Merchant Category Code")["Amount Clean"].transform(lambda x: x.quantile(0.95))
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
            "iqr": row["merchant_iqr"]
        }

    if row["mcc_count"] >= 30:
        return {
            "source": "same merchant category",
            "median": row["mcc_median"],
            "q3": row["mcc_q3"],
            "p90": row["mcc_p90"],
            "p95": row["mcc_p95"],
            "iqr": row["mcc_iqr"]
        }

    return {
        "source": "all transactions",
        "median": row["global_median"],
        "q3": row["global_q3"],
        "p90": row["global_p90"],
        "p95": row["global_p95"],
        "iqr": row["global_iqr"]
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
            "baseline_used": source
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

    low = (
        amount >= max(p90, q3 + 1.5 * iqr)
        and amount_ratio >= 2
        and difference >= 5
    )

    small_item_unusual = (
        median <= 10
        and amount_ratio >= 2
        and difference >= 3
    )

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
        "baseline_used": source
    }


def higher_risk(risk_a, risk_b):
    if RISK_ORDER[risk_a] >= RISK_ORDER[risk_b]:
        return risk_a
    return risk_b


def detect_transaction(row):
    amount = row["Amount Clean"]
    debit_or_credit = str(row.get("Debit or Credit", "")).lower()

    if debit_or_credit == "credit":
        return pd.Series({
            "status": "Credit/Refund",
            "flagged": False,
            "flag_reason": "Credit/refund transaction. No score change.",
            "risk_level": "None",
            "score_change": 0,
            "typical_amount": 0,
            "amount_ratio": 0,
            "baseline_used": "credit/refund",
            "irrelevant_keyword": ""
        })

    keyword = find_irrelevant_keyword(row)
    price_result = pricing_risk(row)

    price_risk = price_result["risk_level"]
    irrelevant_risk = "None"
    reasons = []

    if keyword:
        irrelevant_risk = irrelevant_risk_level(amount)
        reasons.append(f"Possible personal or irrelevant purchase detected: '{keyword}'.")

    if price_risk != "None":
        reasons.append(price_result["reason"])

    final_risk = higher_risk(price_risk, irrelevant_risk)

    if final_risk == "None":
        return pd.Series({
            "status": "Normal",
            "flagged": False,
            "flag_reason": "Reasonable expense. Score increased slightly.",
            "risk_level": "None",
            "score_change": NORMAL_SCORE_INCREASE,
            "typical_amount": price_result["typical_amount"],
            "amount_ratio": price_result["amount_ratio"],
            "baseline_used": price_result["baseline_used"],
            "irrelevant_keyword": ""
        })

    return pd.Series({
        "status": "Flagged",
        "flagged": True,
        "flag_reason": " ".join(reasons),
        "risk_level": final_risk,
        "score_change": POINTS_BY_RISK[final_risk],
        "typical_amount": price_result["typical_amount"],
        "amount_ratio": price_result["amount_ratio"],
        "baseline_used": price_result["baseline_used"],
        "irrelevant_keyword": keyword
    })


def create_department_summary(df):
    rows = []

    for department, group in df.groupby("Department"):
        rows.append({
            "department": department,
            "total_spent": round(float(group["Spend Amount"].sum()), 2),
            "transaction_count": len(group),
            "reasonable_transactions": int((group["status"] == "Normal").sum()),
            "flagged_transactions": int(group["flagged"].sum()),
            "average_score_after_transactions": round(float(group["score_after"].mean()), 2)
        })

    department_df = pd.DataFrame(rows)
    department_df = department_df.sort_values(by="total_spent", ascending=False)

    return department_df


def main():
    input_path = Path(INPUT_FILE)

    if not input_path.exists():
        raise FileNotFoundError(f"Cannot find {INPUT_FILE}.")

    df = pd.read_csv(input_path)

    # Fixed: this only adds missing fake columns. It will not duplicate existing columns.
    df = add_fake_employees_if_needed(df)

    required_columns = [
        "Transaction Amount",
        "Merchant Info DBA Name",
        "Merchant Category Code",
        "Debit or Credit"
    ]

    for col in required_columns:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    df["Amount Clean"] = df["Transaction Amount"].apply(money_to_float)

    df["Spend Amount"] = df.apply(
        lambda row: row["Amount Clean"]
        if str(row.get("Debit or Credit", "")).lower() == "debit"
        else 0,
        axis=1
    )

    df["employee_total_spent"] = (
        df.groupby("Employee ID")["Spend Amount"]
        .transform("sum")
        .round(2)
    )

    df["department_total_spent"] = (
        df.groupby("Department")["Spend Amount"]
        .transform("sum")
        .round(2)
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
        current_scores[employee_id] = min(MAX_SCORE, max(MIN_SCORE, current_scores[employee_id]))

        df.at[index, "score_after"] = float(round(current_scores[employee_id], 2))

    score_rows = []

    for employee_id, group in df.groupby("Employee ID"):
        employee_name = group["Employee Name"].iloc[0]
        department = group["Department"].iloc[0]

        final_score = round(float(group["score_after"].iloc[-1]), 2)
        flagged_count = int(group["flagged"].sum())
        normal_count = int((group["status"] == "Normal").sum())
        total_score_change = round(float(group["score_change"].sum()), 2)
        total_spent = round(float(group["Spend Amount"].sum()), 2)

        flagged_group = group[group["flagged"] == True]

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

        score_rows.append({
            "employee_id": employee_id,
            "employee_name": employee_name,
            "department": department,
            "starting_score": STARTING_SCORE,
            "final_score": final_score,
            "total_score_change": total_score_change,
            "total_spent": total_spent,
            "reasonable_transactions": normal_count,
            "flagged_transactions": flagged_count,
            "one_sentence_summary": summary
        })

    scores_df = pd.DataFrame(score_rows)
    scores_df = scores_df.sort_values(by="final_score", ascending=False)

    flagged_df = df[df["flagged"] == True].copy()
    department_df = create_department_summary(df)

    df.to_csv(SCORED_OUTPUT_FILE, index=False)
    scores_df.to_csv(SCORES_OUTPUT_FILE, index=False)
    flagged_df.to_csv(FLAGGED_OUTPUT_FILE, index=False)
    department_df.to_csv(DEPARTMENT_OUTPUT_FILE, index=False)

    # Save transactions_original.csv with Employee ID, Employee Name, and Department if they were added.
    original_columns_to_remove = [
        "Amount Clean", "Spend Amount", "employee_total_spent", "department_total_spent",
        "merchant_median", "merchant_count", "merchant_q1", "merchant_q3",
        "merchant_p90", "merchant_p95", "merchant_iqr",
        "mcc_median", "mcc_count", "mcc_q1", "mcc_q3",
        "mcc_p90", "mcc_p95", "mcc_iqr",
        "global_median", "global_q1", "global_q3", "global_p90",
        "global_p95", "global_iqr",
        "status", "flagged", "flag_reason", "risk_level",
        "score_change", "typical_amount", "amount_ratio",
        "baseline_used", "irrelevant_keyword", "score_after"
    ]

    df_original_columns = [
        col for col in df.columns
        if col not in original_columns_to_remove
    ]

    df[df_original_columns].to_csv(INPUT_FILE, index=False)

    print("Done.")
    print(f"Read: {INPUT_FILE}")
    print(f"Created/updated: {SCORED_OUTPUT_FILE}")
    print(f"Created/updated: {SCORES_OUTPUT_FILE}")
    print(f"Created/updated: {FLAGGED_OUTPUT_FILE}")
    print(f"Created/updated: {DEPARTMENT_OUTPUT_FILE}")


if __name__ == "__main__":
    main()