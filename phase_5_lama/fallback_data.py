"""Fallback summary data for the Phase 5 dashboard.

The dashboard first tries to read generated cache files from dashboard/cache.
These fallback values are derived from the executed notebook outputs embedded in
this project archive, so the dashboard can still open before local parquet cache
files are generated. For final submission, run build_dashboard_cache.py after
Phase 1-4 have been executed.
"""
from __future__ import annotations

import pandas as pd

TOTAL_TRANSACTIONS = 6_362_604


def risk_summary() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"risk_level": "Normal", "transactions": 6_023_646, "percentage": 94.672653},
            {"risk_level": "Low", "transactions": 273_596, "percentage": 4.300063},
            {"risk_level": "Medium", "transactions": 1_645, "percentage": 0.025854},
            {"risk_level": "High", "transactions": 60_776, "percentage": 0.955206},
            {"risk_level": "Critical", "transactions": 2_941, "percentage": 0.046223},
        ]
    )


def anomaly_type_summary() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"anomaly_type": "No Statistical Anomaly", "transactions": 4_793_091, "percentage": 75.332222},
            {"anomaly_type": "Balance Mismatch", "transactions": 1_439_370, "percentage": 22.622341},
            {"anomaly_type": "Extreme Transaction Amount", "transactions": 85_685, "percentage": 1.346697},
            {"anomaly_type": "Multiple Indicators", "transactions": 44_265, "percentage": 0.695706},
            {"anomaly_type": "Cluster Outlier", "transactions": 185, "percentage": 0.002908},
            {"anomaly_type": "Behavioral and Cluster Outlier", "transactions": 8, "percentage": 0.000126},
        ]
    )


def investigation_summary() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"investigation_category": "Normal / Low Concern", "transactions": 4_794_398, "percentage": 75.352764},
            {"investigation_category": "Possible Data Quality Issue", "transactions": 1_477_915, "percentage": 23.228147},
            {"investigation_category": "Potential Risk / Monitor", "transactions": 86_508, "percentage": 1.359632},
            {"investigation_category": "Potential Fraud", "transactions": 3_780, "percentage": 0.059410},
            {"investigation_category": "Rare Legitimate Transaction", "transactions": 3, "percentage": 0.000047},
        ]
    )


def fraud_by_score() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"risk_score": 0, "transactions": 6_023_646, "fraud_count": 4_342, "fraud_rate": 0.00072083},
            {"risk_score": 1, "transactions": 273_596, "fraud_count": 1_697, "fraud_rate": 0.00620258},
            {"risk_score": 2, "transactions": 1_645, "fraud_count": 729, "fraud_rate": 0.44316109},
            {"risk_score": 3, "transactions": 19_444, "fraud_count": 471, "fraud_rate": 0.02422341},
            {"risk_score": 4, "transactions": 41_332, "fraud_count": 368, "fraud_rate": 0.00890351},
            {"risk_score": 5, "transactions": 92, "fraud_count": 0, "fraud_rate": 0.0},
            {"risk_score": 6, "transactions": 2_849, "fraud_count": 590, "fraud_rate": 0.20709021},
        ]
    )


def method_overlap() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"method": "flag_IQR", "flag_IQR": 338_077, "flag_ZScore": 44_945, "flag_IsoForest": 63_599, "flag_HDBSCAN": 3_051},
            {"method": "flag_ZScore", "flag_IQR": 44_945, "flag_ZScore": 44_945, "flag_IsoForest": 44_099, "flag_HDBSCAN": 2_923},
            {"method": "flag_IsoForest", "flag_IQR": 63_599, "flag_ZScore": 44_099, "flag_IsoForest": 63_616, "flag_HDBSCAN": 2_949},
            {"method": "flag_HDBSCAN", "flag_IQR": 3_051, "flag_ZScore": 2_923, "flag_IsoForest": 2_949, "flag_HDBSCAN": 3_923},
        ]
    )


def fraud_validation_metrics() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"metric": "TP", "value": 1_429},
            {"metric": "FP", "value": 62_288},
            {"metric": "FN", "value": 6_768},
            {"metric": "TN", "value": 6_292_119},
            {"metric": "Precision", "value": 0.02242730},
            {"metric": "Recall", "value": 0.17433210},
            {"metric": "F1", "value": 0.03974191},
            {"metric": "Overall Fraud Rate", "value": 0.001288309},
            {"metric": "High Risk Fraud Rate", "value": 0.02242730},
            {"metric": "Fraud Enrichment", "value": 17.40832},
        ]
    )


def cluster_summary() -> pd.DataFrame:
    rows = [
        {
            "cluster_kmeans": 0,
            "segment_name": "Exceptional High-Value Transfer Segment",
            "business_profile": "Very small segment dominated by unusual high-value transfer behavior and balance mismatches. It is not labelled as fraud, but it deserves operational review because most records are high-risk anomalies.",
            "business_value": "Use as an exception-monitoring queue, not a mass customer segment.",
            "transactions": 1_648,
            "fraud_count": 0,
            "fraud_rate": 0.0,
            "avg_risk_score": 4.656553,
            "high_risk_count": 1_304,
            "critical_count": 982,
            "high_risk_rate": 0.79126214,
            "main_behavior": "Large transfer size, high destination balance mismatch, mostly TRANSFER activity",
        },
        {
            "cluster_kmeans": 1,
            "segment_name": "Mainstream Everyday Banking Segment",
            "business_profile": "The core transaction population. It contains mixed payments, cash-out, cash-in and transfer behavior with low average risk. Fraud is present because this segment is very large, but the rate is close to the baseline.",
            "business_value": "Use as the baseline population for monitoring and policy comparison.",
            "transactions": 5_880_042,
            "fraud_count": 7_065,
            "fraud_rate": 0.001202,
            "avg_risk_score": 0.083410,
            "high_risk_count": 58_726,
            "critical_count": 1_322,
            "high_risk_rate": 0.00998734,
            "main_behavior": "Mixed ordinary transaction activity with merchant and customer destinations",
        },
        {
            "cluster_kmeans": 2,
            "segment_name": "High-Balance Cash-In Segment",
            "business_profile": "A customer-transaction group dominated by cash-in activity and very high origin balances. Fraud rate is higher than the baseline, but the segment is better interpreted as a liquidity behavior group than as a fraud group.",
            "business_value": "Useful for understanding high-balance funding behavior and monitoring balance-related rules.",
            "transactions": 391_249,
            "fraud_count": 1_032,
            "fraud_rate": 0.002638,
            "avg_risk_score": 0.039670,
            "high_risk_count": 2_790,
            "critical_count": 503,
            "high_risk_rate": 0.00713101,
            "main_behavior": "Cash-in transactions with very high origin balances",
        },
        {
            "cluster_kmeans": 3,
            "segment_name": "Very High-Balance Cash-In Segment",
            "business_profile": "A smaller cash-in segment with even higher starting balances. Its fraud rate is low, but its financial size makes it useful for segmentation and reporting.",
            "business_value": "Useful for separating very high-balance cash-in behavior from ordinary transactions.",
            "transactions": 89_665,
            "fraud_count": 100,
            "fraud_rate": 0.001115,
            "avg_risk_score": 0.049629,
            "high_risk_count": 897,
            "critical_count": 134,
            "high_risk_rate": 0.01000390,
            "main_behavior": "Cash-in transactions with very high origin balances and low merchant involvement",
        },
    ]
    df = pd.DataFrame(rows)
    df["population_share"] = df["transactions"] / TOTAL_TRANSACTIONS
    return df


def rules() -> pd.DataFrame:
    rows = [
        {"antecedents_str": "origError_very_low, orig_drained_yes", "consequents_str": "isFraud_yes", "support": 0.001259, "confidence": 1.000000, "lift": 776.211297, "leverage": 0.001257, "conviction": float("inf")},
        {"antecedents_str": "cluster_kmeans_2, orig_drained_yes", "consequents_str": "isFraud_yes", "support": 0.000154, "confidence": 1.000000, "lift": 776.211297, "leverage": 0.000154, "conviction": float("inf")},
        {"antecedents_str": "hdbscan_outlier, origError_very_low", "consequents_str": "isFraud_yes", "support": 0.000103, "confidence": 0.904432, "lift": 702.030439, "leverage": 0.000102, "conviction": 10.450288},
        {"antecedents_str": "cluster_kmeans_2, origError_very_low", "consequents_str": "isFraud_yes", "support": 0.000161, "confidence": 0.649746, "lift": 504.340335, "leverage": 0.000161, "conviction": 2.851394},
        {"antecedents_str": "type_DEBIT", "consequents_str": "amount_very_low, cluster_kmeans_1", "support": 0.005904, "confidence": 0.906618, "lift": 4.597684, "leverage": 0.004620, "conviction": 8.597058},
        {"antecedents_str": "destError_low", "consequents_str": "amount_very_low, cluster_kmeans_1", "support": 0.176434, "confidence": 0.882169, "lift": 4.473699, "leverage": 0.136996, "conviction": 6.813256},
        {"antecedents_str": "type_DEBIT", "consequents_str": "amount_very_low, destError_very_low", "support": 0.005420, "confidence": 0.832352, "lift": 47.200336, "leverage": 0.005305, "conviction": 5.859685},
        {"antecedents_str": "cluster_kmeans_3", "consequents_str": "oldbalanceOrg_very_high, type_CASH_IN", "support": 0.014070, "confidence": 0.998405, "lift": 7.325951, "leverage": 0.012149, "conviction": 541.574498},
        {"antecedents_str": "cluster_kmeans_2", "consequents_str": "oldbalanceOrg_very_high, type_CASH_IN", "support": 0.061243, "confidence": 0.995951, "lift": 7.307946, "leverage": 0.052863, "conviction": 213.338557},
        {"antecedents_str": "cluster_kmeans_2", "consequents_str": "destError_very_high, oldbalanceOrg_very_high", "support": 0.048769, "confidence": 0.793104, "lift": 7.197255, "leverage": 0.041993, "conviction": 4.300726},
    ]
    return pd.DataFrame(rows)


def top_suspicious() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "step",
            "transaction_type",
            "amount",
            "risk_score",
            "risk_level",
            "anomaly_type",
            "investigation_category",
            "anomaly_reason",
            "cluster_kmeans",
            "isFraud",
        ]
    )


def data_quality_findings() -> list[dict[str, str]]:
    return [
        {"finding": "No self-transactions", "business_meaning": "The sender and receiver accounts are different, so transaction direction is valid."},
        {"finding": "No exact duplicate records", "business_meaning": "The dataset does not contain repeated rows that would inflate patterns."},
        {"finding": "No negative amount or balance values", "business_meaning": "Transaction values follow basic accounting constraints."},
        {"finding": "Merchant destination balances are recorded as zero", "business_meaning": "This is a PaySim data design feature and should not be treated as missing data."},
        {"finding": "Fraud appears only in TRANSFER and CASH_OUT", "business_meaning": "Fraud monitoring should focus on customer-to-customer movement and cash-out behavior, not merchant payments."},
    ]
