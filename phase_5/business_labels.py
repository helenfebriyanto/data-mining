from __future__ import annotations

from typing import Any

import pandas as pd

CLUSTER_LABELS = {
    0: "Segment 0 — Exceptional High-Value Transfer",
    1: "Segment 1 — Mainstream Everyday Banking",
    2: "Segment 2 — High-Balance Cash-In",
    3: "Segment 3 — Very High-Balance Cash-In",
}

ITEM_LABELS = {
    "isFraud_yes": "confirmed fraud",
    "isFraud_no": "not labelled as fraud",
    "hdbscan_outlier": "cluster outlier",
    "hdbscan_normal": "normal cluster position",
    "orig_drained_yes": "sender balance was drained to zero",
    "orig_drained_no": "sender balance was not drained to zero",
    "dest_merchant_yes": "destination is a merchant",
    "dest_merchant_no": "destination is a customer account",
    "type_CASH_IN": "cash-in transaction",
    "type_CASH_OUT": "cash-out transaction",
    "type_DEBIT": "debit transaction",
    "type_PAYMENT": "payment transaction",
    "type_TRANSFER": "transfer transaction",
    "cluster_kmeans_0": CLUSTER_LABELS[0],
    "cluster_kmeans_1": CLUSTER_LABELS[1],
    "cluster_kmeans_2": CLUSTER_LABELS[2],
    "cluster_kmeans_3": CLUSTER_LABELS[3],
    "amount_very_low": "very low transaction amount",
    "amount_low": "low transaction amount",
    "amount_medium": "medium transaction amount",
    "amount_high": "high transaction amount",
    "amount_very_high": "very high transaction amount",
    "oldbalanceOrg_very_low": "very low sender starting balance",
    "oldbalanceOrg_low": "low sender starting balance",
    "oldbalanceOrg_medium": "medium sender starting balance",
    "oldbalanceOrg_high": "high sender starting balance",
    "oldbalanceOrg_very_high": "very high sender starting balance",
    "oldbalanceDest_very_low": "very low receiver starting balance",
    "oldbalanceDest_low": "low receiver starting balance",
    "oldbalanceDest_medium": "medium receiver starting balance",
    "oldbalanceDest_high": "high receiver starting balance",
    "oldbalanceDest_very_high": "very high receiver starting balance",
    "origError_very_low": "sender-balance pattern is in the very-low bucket",
    "origError_low": "sender-balance pattern is in the low bucket",
    "origError_medium": "sender-balance pattern is in the medium bucket",
    "origError_high": "sender-balance pattern is in the high bucket",
    "origError_very_high": "sender-balance pattern is in the very-high bucket",
    "destError_very_low": "receiver-balance pattern is in the very-low bucket",
    "destError_low": "receiver-balance pattern is in the low bucket",
    "destError_medium": "receiver-balance pattern is in the medium bucket",
    "destError_high": "receiver-balance pattern is in the high bucket",
    "destError_very_high": "receiver-balance pattern is in the very-high bucket",
}


def pct(value: Any, decimals: int = 2) -> str:
    try:
        value_float = float(value)
    except Exception:
        return "—"
    return f"{value_float * 100:.{decimals}f}%"


def humanize_item(item: str) -> str:
    item = str(item).strip()
    return ITEM_LABELS.get(item, item.replace("_", " "))


def humanize_item_list(items: str) -> str:
    parts = [humanize_item(part) for part in str(items).split(",") if part.strip()]
    if not parts:
        return "—"
    if len(parts) == 1:
        return parts[0]
    return "; ".join(parts)


def rule_takeaway(row: pd.Series) -> str:
    antecedents = str(row.get("antecedents_str", ""))
    consequents = str(row.get("consequents_str", ""))
    both = f"{antecedents} {consequents}"
    lift = float(row.get("lift", 0) or 0)
    confidence = float(row.get("confidence", 0) or 0)

    if "isFraud_yes" in consequents:
        return (
            "Escalate this pattern. It is rare, but when it appears it is strongly concentrated around confirmed fraud."
            if confidence >= 0.5
            else "Monitor this pattern. It increases fraud concentration but still needs confirmation before action."
        )
    if "cluster_kmeans" in both:
        return "This rule explains which behaviors naturally belong to a customer-transaction segment."
    if "hdbscan_outlier" in both:
        return "This rule points to transactions that fall outside the normal structure of the population."
    if lift >= 10:
        return "This is a strong behavioral pattern and is useful for explaining how transaction attributes move together."
    return "This is a business pattern that helps describe common transaction behavior."


# ---------------------------------------------------------------------------
# Rule grouping (drives the plain-English filter chips on the Patterns tab)
# ---------------------------------------------------------------------------

RULE_GROUP_FRAUD = "Fraud pattern"
RULE_GROUP_SEGMENT = "Segment pattern"
RULE_GROUP_OUTLIER = "Outlier pattern"
RULE_GROUP_GENERAL = "General behavior"

RULE_GROUP_ORDER = [RULE_GROUP_FRAUD, RULE_GROUP_SEGMENT, RULE_GROUP_OUTLIER, RULE_GROUP_GENERAL]

RULE_GROUP_BADGE = {
    RULE_GROUP_FRAUD: "badge badge-critical",
    RULE_GROUP_SEGMENT: "badge badge-info",
    RULE_GROUP_OUTLIER: "badge badge-high",
    RULE_GROUP_GENERAL: "badge badge-normal",
}


def rule_group(row: pd.Series) -> str:
    antecedents = str(row.get("antecedents_str", ""))
    consequents = str(row.get("consequents_str", ""))
    both = f"{antecedents} {consequents}"
    if "isFraud_yes" in consequents:
        return RULE_GROUP_FRAUD
    if "cluster_kmeans" in both:
        return RULE_GROUP_SEGMENT
    if "hdbscan_outlier" in both:
        return RULE_GROUP_OUTLIER
    return RULE_GROUP_GENERAL


# ---------------------------------------------------------------------------
# Transaction type labels
# ---------------------------------------------------------------------------

TRANSACTION_TYPE_LABELS = {
    "CASH_IN": "Cash In",
    "CASH_OUT": "Cash Out",
    "DEBIT": "Debit",
    "PAYMENT": "Payment",
    "TRANSFER": "Transfer",
}


def humanize_transaction_type(value: Any) -> str:
    key = str(value).strip().upper()
    return TRANSACTION_TYPE_LABELS.get(key, str(value).replace("_", " ").title())


# ---------------------------------------------------------------------------
# Badge class helpers (used by the Unusual Activities and Data Explorer tabs)
# ---------------------------------------------------------------------------

RISK_BADGE_CLASS = {
    "Normal": "badge badge-normal",
    "Low": "badge badge-low",
    "Medium": "badge badge-medium",
    "High": "badge badge-high",
    "Critical": "badge badge-critical",
}


def risk_badge_class(risk_level: Any) -> str:
    return RISK_BADGE_CLASS.get(str(risk_level), "badge badge-normal")


INVESTIGATION_BADGE_CLASS = {
    "Potential Fraud": "badge badge-critical",
    "Possible Data Quality Issue": "badge badge-medium",
    "Potential Risk / Monitor": "badge badge-high",
    "Rare Legitimate Transaction": "badge badge-info",
    "Normal / Low Concern": "badge badge-normal",
}


def investigation_badge_class(category: Any) -> str:
    return INVESTIGATION_BADGE_CLASS.get(str(category), "badge badge-normal")


# ---------------------------------------------------------------------------
# Time helper — PaySim's "step" is one simulation hour; turn it into a day/time
# a reader can picture instead of a bare integer.
# ---------------------------------------------------------------------------

def day_from_step(step: Any) -> str:
    try:
        step_int = int(step)
    except Exception:
        return "—"
    day = (step_int - 1) // 24 + 1
    hour = (step_int - 1) % 24
    return f"Day {day}, {hour:02d}:00"


# ---------------------------------------------------------------------------
# Cluster / segment business columns — mirrors add_rule_business_columns so
# app.py can enrich cluster_summary the same way it enriches rules, regardless
# of whether the data came from the real cache or the fallback.
# ---------------------------------------------------------------------------

def _num(value: Any) -> str:
    try:
        return f"{int(round(float(value))):,}"
    except Exception:
        return "—"


def add_cluster_business_columns(cluster: pd.DataFrame) -> pd.DataFrame:
    cluster = cluster.copy()
    if cluster.empty:
        return cluster

    for col in ["fraud_rate", "high_risk_rate", "population_share", "avg_risk_score", "transactions", "fraud_count"]:
        if col in cluster.columns:
            cluster[col] = pd.to_numeric(cluster[col], errors="coerce")
    
    
    if "transactions" in cluster.columns and "high_risk_count" in cluster.columns:
        cluster["high_risk_rate"] = (
            cluster["high_risk_count"]
            / cluster["transactions"]
        )

    if "population_share" not in cluster.columns and "transactions" in cluster.columns:
        total = cluster["transactions"].sum()
        cluster["population_share"] = cluster["transactions"] / total if total else 0.0

    baseline_fraud_rate = None
    if "transactions" in cluster.columns and "fraud_count" in cluster.columns:
        total_txn = cluster["transactions"].sum()
        total_fraud = cluster["fraud_count"].sum()
        baseline_fraud_rate = (total_fraud / total_txn) if total_txn else 0.0

    # Prefer CLUSTER_LABELS ("Segment 0 — Exceptional High-Value Transfer") so the
    # name matches exactly how segments are labelled in the Data Explorer tab.
    # Fall back to the cache's own segment_name text only if cluster_kmeans is missing.
    if "cluster_kmeans" in cluster.columns:
        cluster["Segment"] = (
            pd.to_numeric(cluster["cluster_kmeans"], errors="coerce")
            .map(CLUSTER_LABELS)
        )
        if "segment_name" in cluster.columns:
            cluster["Segment"] = cluster["Segment"].fillna(cluster["segment_name"])
        cluster["Segment"] = cluster["Segment"].fillna(cluster["cluster_kmeans"].astype(str))
    elif "segment_name" in cluster.columns:
        cluster["Segment"] = cluster["segment_name"]
    else:
        cluster["Segment"] = "—"

    cluster["Share of activity"] = (
        cluster["population_share"].apply(lambda x: pct(x, 2)) if "population_share" in cluster.columns else "—"
    )
    cluster["Transactions"] = cluster["transactions"].apply(_num) if "transactions" in cluster.columns else "—"
    cluster["Fraud rate"] = cluster["fraud_rate"].apply(lambda x: pct(x, 3)) if "fraud_rate" in cluster.columns else "—"
    cluster["High-risk queue rate"] = (
        cluster["high_risk_rate"].apply(lambda x: pct(x, 2)) if "high_risk_rate" in cluster.columns else "—"
    )

    if baseline_fraud_rate:
        cluster["Fraud vs. baseline"] = cluster["fraud_rate"].apply(
            lambda x: (f"{x / baseline_fraud_rate:.1f}x baseline" if pd.notna(x) else "—")
        )
    else:
        cluster["Fraud vs. baseline"] = "—"

    return cluster


# ---------------------------------------------------------------------------
# Data Explorer table prep — derives display-friendly columns once at load
# time so the filter/pagination callback never has to repeat this work.
# ---------------------------------------------------------------------------

def metrics_lookup(df: pd.DataFrame) -> dict:
    """Turn the long-format (metric, value) fraud_validation_metrics table into a dict."""
    if df is None or df.empty or "metric" not in df.columns:
        return {}
    return dict(zip(df["metric"], df["value"]))


def prepare_explorer_table(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if df.empty:
        return df
    if "step" in df.columns:
        df["Day"] = df["step"].apply(day_from_step)
    if "transaction_type" in df.columns:
        df["Transaction Type"] = df["transaction_type"].apply(humanize_transaction_type)
    if "amount" in df.columns:
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").round(2)
    if "isFraud" in df.columns:
        df["Historical Label"] = df["isFraud"].map({1: "Confirmed fraud", 0: "Not fraud"}).fillna("Unknown")
    return df


def add_rule_business_columns(rules: pd.DataFrame) -> pd.DataFrame:
    rules = rules.copy()
    if rules.empty:
        return rules
    for col in ["support", "confidence", "lift"]:
        if col in rules.columns:
            rules[col] = pd.to_numeric(rules[col], errors="coerce")
    if "antecedents_str" not in rules.columns and "antecedents" in rules.columns:
        rules["antecedents_str"] = rules["antecedents"].astype(str)
    if "consequents_str" not in rules.columns and "consequents" in rules.columns:
        rules["consequents_str"] = rules["consequents"].astype(str)
    rules["When this is seen"] = rules["antecedents_str"].apply(humanize_item_list)
    rules["This usually comes with"] = rules["consequents_str"].apply(humanize_item_list)
    rules["Coverage"] = rules["support"].apply(lambda x: pct(x, 3))
    rules["Hit rate inside that group"] = rules["confidence"].apply(lambda x: pct(x, 1))
    rules["Uplift vs normal"] = rules["lift"].apply(lambda x: f"{x:,.1f}x" if pd.notna(x) else "—")
    rules["Business takeaway"] = rules.apply(rule_takeaway, axis=1)
    rules["Rule group"] = rules.apply(rule_group, axis=1)
    return rules
