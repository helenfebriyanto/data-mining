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
    consequents = str(row.get("consequents_str", ""))
    lift = float(row.get("lift", 0) or 0)
    confidence = float(row.get("confidence", 0) or 0)

    if "isFraud_yes" in consequents:
        return (
            "Escalate this pattern. It is rare, but when it appears it is strongly concentrated around confirmed fraud."
            if confidence >= 0.5
            else "Monitor this pattern. It increases fraud concentration but still needs confirmation before action."
        )
    if "cluster_kmeans" in consequents:
        return "This rule explains which behaviors naturally belong to a customer-transaction segment."
    if "hdbscan_outlier" in consequents:
        return "This rule points to transactions that fall outside the normal structure of the population."
    if lift >= 10:
        return "This is a strong behavioral pattern and is useful for explaining how transaction attributes move together."
    return "This is a business pattern that helps describe common transaction behavior."


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
    return rules
