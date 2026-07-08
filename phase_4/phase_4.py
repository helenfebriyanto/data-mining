from prefect import flow, task, get_run_logger
import os
import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest


# Bobot dibuat tidak sama karena Isolation Forest dan HDBSCAN/BIRCH menangkap pola
# multivariate/cluster outlier, sedangkan IQR dan Z-Score hanya membaca amount.
SIGNAL_WEIGHTS = {
    "flag_IQR": 1,
    "flag_ZScore": 1,
    "flag_IsoForest": 2,
    "flag_HDBSCAN": 2,
}
HIGH_RISK_THRESHOLD = 3
CRITICAL_RISK_THRESHOLD = 5


@task
def load_data(path, path_outlier):
    logger = get_run_logger()
    df = pd.read_parquet(path)
    df_outliers = pd.read_parquet(path_outlier)

    logger.info(f"Data Shape: {df.shape}")
    logger.info(f"Data Outliers Shape: {df_outliers.shape}")
    logger.info(f"Columns: {list(df.columns)}")

    if "cluster_birch_hdbscan" in df.columns:
        expected_outlier_count = int((df["cluster_birch_hdbscan"] == -1).sum())
        logger.info(
            "Sanity Check BIRCH+HDBSCAN Outlier Export\n"
            f"Rows cluster_birch_hdbscan == -1 : {expected_outlier_count}\n"
            f"Rows in outlier parquet          : {len(df_outliers)}\n"
            f"Status                           : {'KONSISTEN' if expected_outlier_count == len(df_outliers) else 'TIDAK KONSISTEN'}"
        )

    return df, df_outliers


@task
def detect_iqr(df, column):
    logger = get_run_logger()
    Q1 = df[column].quantile(0.25)
    Q3 = df[column].quantile(0.75)
    IQR = Q3 - Q1

    lower = Q1 - 1.5 * IQR
    upper = Q3 + 1.5 * IQR

    flag = ((df[column] < lower) | (df[column] > upper)).astype(int)

    logger.info(
        f"""
        IQR Detection - {column}
        Q1: {Q1:.4f}
        Q3: {Q3:.4f}
        IQR: {IQR:.4f}
        Lower Bound: {lower:.4f}
        Upper Bound: {upper:.4f}
        Total Anomalies: {flag.sum()} ({(flag.mean() * 100):.2f}%)"""
    )

    extreme_values = df.loc[flag == 1, column]
    if not extreme_values.empty:
        logger.info(
            f"Max anomaly value: {extreme_values.max():.2f}, "
            f"Min anomaly value: {extreme_values.min():.2f}"
        )

    return flag


@task
def detect_zscore(df, column, threshold=3):
    logger = get_run_logger()
    mean = df[column].mean()
    std = df[column].std()

    z = (df[column] - mean) / std
    flag = (np.abs(z) > threshold).astype(int)

    logger.info(
        f"""
        Z-Score Detection - {column}
        Mean: {mean:.4f}
        Std Dev: {std:.4f}
        Threshold: |Z| > {threshold}
        Total Anomalies: {flag.sum()} ({(flag.mean() * 100):.2f}%)"""
    )

    extreme_values = df.loc[flag == 1, column]
    if not extreme_values.empty:
        logger.info(
            f"Max anomaly value: {extreme_values.max():.2f}, "
            f"Min anomaly value: {extreme_values.min():.2f}"
        )

    return flag


@task
def combine_flags(iqr_flag, z_flag):
    logger = get_run_logger()
    combined = iqr_flag + z_flag

    logger.info(f"Total combined univariate anomalies (>=1): {(combined >= 1).sum()}")
    logger.info(f"IQR and Z-Score overlap (>=2): {(combined >= 2).sum()}")

    return combined


@task
def detect_isolation_forest(df):
    logger = get_run_logger()
    df = df.copy()

    # Multivariate anomaly detection. amount menangkap nominal ekstrem, sedangkan
    # origError/destError menangkap ketidakwajaran perubahan saldo. Ketiganya sudah
    # terbukti relevan dari Phase 1 dan Phase 2.
    feature_cols = ["amount", "origError", "destError"]
    features = df[feature_cols].fillna(0)

    model = IsolationForest(
        contamination=0.01,
        random_state=42
    )
    preds = model.fit_predict(features)

    flag = pd.Series((preds == -1).astype(int), index=df.index, name="flag_IsoForest")

    logger.info(
        "Isolation Forest Detection\n"
        f"Features Used      : {', '.join(feature_cols)}\n"
        "Contamination      : 0.01\n"
        f"Total Anomalies    : {flag.sum()} ({(flag.mean() * 100):.2f}%)"
    )

    anomaly_data = df.loc[flag == 1, feature_cols]
    if not anomaly_data.empty:
        extreme_lines = "\n".join(
            f"Max {col} Anomaly : {anomaly_data[col].max():.2f}  |  "
            f"Min {col} Anomaly : {anomaly_data[col].min():.2f}"
            for col in feature_cols
        )
        logger.info("Isolation Forest Extreme Values\n" + extreme_lines)

    return flag


@task
def detect_balance_mismatch(df, columns=("origError", "destError")):
    """Menandai balance mismatch ekstrem sebagai bahan investigasi.

    Kolom origError/destError pada input Phase 4 sudah diskalakan dari Phase 1.
    Karena itu, threshold dihitung ulang secara empiris memakai IQR pada data Phase 4,
    bukan memakai angka absolut mentah.
    """
    logger = get_run_logger()
    flags = []
    bounds = {}

    for col in columns:
        if col not in df.columns:
            continue

        Q1 = df[col].quantile(0.25)
        Q3 = df[col].quantile(0.75)
        IQR = Q3 - Q1
        lower = Q1 - 1.5 * IQR
        upper = Q3 + 1.5 * IQR

        col_flag = ((df[col] < lower) | (df[col] > upper)).astype(int)
        flags.append(col_flag)
        bounds[col] = {"lower": lower, "upper": upper, "count": int(col_flag.sum())}

    if flags:
        balance_flag = pd.concat(flags, axis=1).max(axis=1).astype(int)
    else:
        balance_flag = pd.Series(0, index=df.index)

    logger.info(
        "Balance Mismatch Investigation Flag\n"
        f"Columns Checked         : {list(columns)}\n"
        f"Total Balance Mismatch  : {balance_flag.sum()} ({balance_flag.mean() * 100:.2f}%)\n"
        f"Bounds                  : {bounds}"
    )

    return balance_flag, bounds


def _build_reason_lookup():
    lookup = {}
    for mask in range(64):
        reasons = []
        if mask & 1:
            reasons.append("High amount anomaly by IQR")
        if mask & 2:
            reasons.append("Extreme amount anomaly by Z-Score")
        if mask & 4:
            reasons.append("Multivariate anomaly by Isolation Forest")
        if mask & 8:
            reasons.append("Cluster outlier from BIRCH+HDBSCAN")
        if mask & 16:
            reasons.append("Extreme balance mismatch in origError/destError")
        if mask & 32:
            reasons.append("Origin account drained to zero")
        lookup[mask] = "; ".join(reasons) if reasons else "No anomaly detected"
    return lookup


@task
def cross_reference(df, df_outliers, iqr_flag, z_flag, iso_flag, balance_flag):
    logger = get_run_logger()
    df = df.copy()

    df["flag_IQR"] = pd.Series(iqr_flag, index=df.index).astype(int)
    df["flag_ZScore"] = pd.Series(z_flag, index=df.index).astype(int)
    df["flag_IsoForest"] = pd.Series(iso_flag, index=df.index).astype(int)
    df["flag_BalanceMismatch"] = pd.Series(balance_flag, index=df.index).astype(int)

    # Pakai cluster_birch_hdbscan (hasil BIRCH+HDBSCAN dari Phase 2), BUKAN cluster_hdbscan.
    # cluster_hdbscan langsung menandai mayoritas baris sebagai outlier sehingga kurang layak
    # dijadikan sinyal risiko utama.
    df["flag_HDBSCAN"] = (df["cluster_birch_hdbscan"] == -1).astype(int)

    flag_cols = ["flag_IQR", "flag_ZScore", "flag_IsoForest", "flag_HDBSCAN"]
    df["risk_indicator_count"] = df[flag_cols].sum(axis=1).astype(int)

    # Weighted risk score: IF dan HDBSCAN diberi bobot 2 karena lebih kuat untuk pola
    # multivariate/cluster; IQR dan Z-Score tetap bobot 1 karena univariate.
    df["risk_score"] = (
        df["flag_IQR"] * SIGNAL_WEIGHTS["flag_IQR"] +
        df["flag_ZScore"] * SIGNAL_WEIGHTS["flag_ZScore"] +
        df["flag_IsoForest"] * SIGNAL_WEIGHTS["flag_IsoForest"] +
        df["flag_HDBSCAN"] * SIGNAL_WEIGHTS["flag_HDBSCAN"]
    ).astype(int)

    df["high_risk"] = (df["risk_score"] >= HIGH_RISK_THRESHOLD).astype(int)
    df["critical_risk"] = (df["risk_score"] >= CRITICAL_RISK_THRESHOLD).astype(int)

    df["risk_level"] = pd.Categorical(
        np.select(
            [
                df["risk_score"] >= CRITICAL_RISK_THRESHOLD,
                df["risk_score"] >= HIGH_RISK_THRESHOLD,
                df["risk_score"] == 2,
                df["risk_score"] == 1,
            ],
            ["Critical", "High", "Medium", "Low"],
            default="Normal",
        ),
        categories=["Normal", "Low", "Medium", "High", "Critical"],
        ordered=True,
    )

    df["anomaly_type"] = pd.Categorical(
        np.select(
            [
                df["risk_indicator_count"] >= 3,
                (df["flag_IsoForest"] == 1) & (df["flag_HDBSCAN"] == 1),
                df["flag_BalanceMismatch"] == 1,
                df["flag_IsoForest"] == 1,
                df["flag_HDBSCAN"] == 1,
                (df["flag_IQR"] == 1) | (df["flag_ZScore"] == 1),
            ],
            [
                "Multiple Indicators",
                "Behavioral and Cluster Outlier",
                "Balance Mismatch",
                "Behavioral Outlier",
                "Cluster Outlier",
                "Extreme Transaction Amount",
            ],
            default="No Statistical Anomaly",
        )
    )

    df["investigation_category"] = pd.Categorical(
        np.select(
            [
                ((df["isFraud"] == 1) & (df["high_risk"] == 1)) | (df["risk_score"] >= CRITICAL_RISK_THRESHOLD),
                (df["flag_BalanceMismatch"] == 1) & (df["isFraud"] == 0),
                (df["isFraud"] == 0) & (df["high_risk"] == 1),
                df["risk_indicator_count"] >= 1,
            ],
            [
                "Potential Fraud",
                "Possible Data Quality Issue",
                "Rare Legitimate Transaction",
                "Potential Risk / Monitor",
            ],
            default="Normal / Low Concern",
        )
    )

    drained_flag = df["origDrainedToZero"].astype(int) if "origDrainedToZero" in df.columns else 0
    reason_mask = (
        df["flag_IQR"] * 1 +
        df["flag_ZScore"] * 2 +
        df["flag_IsoForest"] * 4 +
        df["flag_HDBSCAN"] * 8 +
        df["flag_BalanceMismatch"] * 16 +
        drained_flag * 32
    ).astype(int)
    df["anomaly_reason"] = pd.Categorical(reason_mask.map(_build_reason_lookup()))

    logger.info(
        "Cross Reference Detection with Business Interpretation\n"
        f"Total Transactions      : {len(df)}\n"
        f"IQR Anomalies           : {df['flag_IQR'].sum()}\n"
        f"Z-Score Anomalies       : {df['flag_ZScore'].sum()}\n"
        f"Isolation Forest        : {df['flag_IsoForest'].sum()}\n"
        f"BIRCH+HDBSCAN Outliers  : {df['flag_HDBSCAN'].sum()}\n"
        f"Balance Mismatch Flag   : {df['flag_BalanceMismatch'].sum()}\n"
        f"High Risk Transactions  : {df['high_risk'].sum()} ({df['high_risk'].mean() * 100:.2f}%)\n"
        f"Critical Transactions   : {df['critical_risk'].sum()} ({df['critical_risk'].mean() * 100:.2f}%)"
    )

    logger.info("Weighted Risk Score Distribution\n" + str(df["risk_score"].value_counts().sort_index()))
    logger.info("Risk Level Distribution\n" + str(df["risk_level"].value_counts().sort_index()))
    logger.info("Anomaly Type Distribution\n" + str(df["anomaly_type"].value_counts()))
    logger.info("Investigation Category Distribution\n" + str(df["investigation_category"].value_counts()))

    return df


@task
def validate_fraud(df):
    logger = get_run_logger()

    y_true = df["isFraud"].astype(int)
    y_pred = df["high_risk"].astype(int)

    tp = int(((y_true == 1) & (y_pred == 1)).sum())
    fp = int(((y_true == 0) & (y_pred == 1)).sum())
    fn = int(((y_true == 1) & (y_pred == 0)).sum())
    tn = int(((y_true == 0) & (y_pred == 0)).sum())

    precision = tp / (tp + fp) if (tp + fp) else 0
    recall = tp / (tp + fn) if (tp + fn) else 0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0

    overall_fraud_rate = y_true.mean()
    high_risk_fraud_rate = df.loc[df["high_risk"] == 1, "isFraud"].mean()
    enrichment = (high_risk_fraud_rate / overall_fraud_rate) if overall_fraud_rate else 0

    metrics = pd.DataFrame([
        {"metric": "TP", "value": tp},
        {"metric": "FP", "value": fp},
        {"metric": "FN", "value": fn},
        {"metric": "TN", "value": tn},
        {"metric": "Precision", "value": precision},
        {"metric": "Recall", "value": recall},
        {"metric": "F1", "value": f1},
        {"metric": "Overall Fraud Rate", "value": overall_fraud_rate},
        {"metric": "High Risk Fraud Rate", "value": high_risk_fraud_rate},
        {"metric": "Fraud Enrichment", "value": enrichment},
    ])

    logger.info(
        "Fraud Validation and Confusion Matrix\n"
        f"High Risk Transactions : {df['high_risk'].sum()}\n"
        f"TP: {tp} | FP: {fp} | FN: {fn} | TN: {tn}\n"
        f"Precision              : {precision:.4f}\n"
        f"Recall                 : {recall:.4f}\n"
        f"F1                     : {f1:.4f}\n"
        f"High Risk Fraud Rate   : {high_risk_fraud_rate * 100:.2f}%\n"
        f"Enrichment             : {enrichment:.1f}x baseline"
    )

    return df, metrics


@task
def summarize_investigation(df):
    logger = get_run_logger()

    flag_cols = ["flag_IQR", "flag_ZScore", "flag_IsoForest", "flag_HDBSCAN"]

    risk_summary = (
        df["risk_level"]
        .value_counts()
        .sort_index()
        .rename_axis("risk_level")
        .reset_index(name="transactions")
    )
    risk_summary["percentage"] = risk_summary["transactions"] / len(df)

    anomaly_type_summary = (
        df["anomaly_type"]
        .value_counts()
        .rename_axis("anomaly_type")
        .reset_index(name="transactions")
    )
    anomaly_type_summary["percentage"] = anomaly_type_summary["transactions"] / len(df)

    investigation_summary = (
        df["investigation_category"]
        .value_counts()
        .rename_axis("investigation_category")
        .reset_index(name="transactions")
    )
    investigation_summary["percentage"] = investigation_summary["transactions"] / len(df)

    fraud_by_score = (
        df.groupby("risk_score")["isFraud"]
        .agg(transactions="count", fraud_count="sum", fraud_rate="mean")
        .reset_index()
    )

    method_overlap = pd.DataFrame(index=flag_cols, columns=flag_cols, dtype=int)
    for row_col in flag_cols:
        for col_col in flag_cols:
            method_overlap.loc[row_col, col_col] = int(((df[row_col] == 1) & (df[col_col] == 1)).sum())
    method_overlap = method_overlap.reset_index().rename(columns={"index": "method"})

    summary_tables = {
        "risk_summary": risk_summary,
        "anomaly_type_summary": anomaly_type_summary,
        "investigation_summary": investigation_summary,
        "fraud_by_score": fraud_by_score,
        "method_overlap": method_overlap,
    }

    if "cluster_kmeans" in df.columns:
        cluster_summary = (
            df.groupby("cluster_kmeans")
            .agg(
                transactions=("isFraud", "size"),
                fraud_count=("isFraud", "sum"),
                fraud_rate=("isFraud", "mean"),
                avg_risk_score=("risk_score", "mean"),
                high_risk_count=("high_risk", "sum"),
                critical_count=("critical_risk", "sum"),
            )
            .reset_index()
        )
        cluster_summary["high_risk_rate"] = cluster_summary["high_risk_count"] / cluster_summary["transactions"]
        summary_tables["cluster_kmeans_risk_summary"] = cluster_summary

    type_cols = [col for col in df.columns if col.startswith("type_")]
    if type_cols:
        high_risk_type_breakdown = (
            df.loc[df["high_risk"] == 1, type_cols]
            .sum()
            .sort_values(ascending=False)
            .rename_axis("transaction_type")
            .reset_index(name="high_risk_count")
        )
        summary_tables["high_risk_type_breakdown"] = high_risk_type_breakdown

    logger.info("Risk Summary\n" + str(risk_summary))
    logger.info("Fraud by Weighted Risk Score\n" + str(fraud_by_score))
    if "cluster_kmeans_risk_summary" in summary_tables:
        logger.info("K-Means Cluster Risk Summary\n" + str(summary_tables["cluster_kmeans_risk_summary"]))

    return summary_tables


@task
def select_top_anomalies(df, top_n=20000):
    logger = get_run_logger()

    sort_cols = ["risk_score", "risk_indicator_count", "flag_BalanceMismatch", "amount"]
    sort_cols = [col for col in sort_cols if col in df.columns]

    top_df = df.sort_values(
        by=sort_cols,
        ascending=[False] * len(sort_cols)
    ).head(top_n)

    logger.info(
        "Top Suspicious Transactions\n"
        f"Selected Rows             : {len(top_df)}\n"
        f"Fraud Rate in Selection   : {top_df['isFraud'].mean() * 100:.2f}%\n"
        f"Main Investigation Groups :\n{top_df['investigation_category'].value_counts()}"
    )

    return top_df


@task
def export_results(top_df, output_path):
    logger = get_run_logger()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    top_df.to_parquet(output_path, index=False)
    logger.info(f"Exported Suspicious Transactions: {output_path}")


@task
def export_summary_tables(summary_tables, output_dir):
    logger = get_run_logger()
    os.makedirs(output_dir, exist_ok=True)

    for name, table in summary_tables.items():
        path = os.path.join(output_dir, f"{name}.csv")
        table.to_csv(path, index=False)
        logger.info(f"Exported Summary Table: {path}")


@flow
def handling_outlier_pipeline():
    path_1 = "../datasets/phase_2/paysim-dataset-phase2.parquet"
    path_2 = "../datasets/phase_2/paysim-outliers-phase4.parquet"

    df, df_outliers = load_data(path_1, path_2)

    # 1) Statistical anomaly detection
    iqr_flag = detect_iqr(df, "amount")
    z_flag = detect_zscore(df, "amount")
    _ = combine_flags(iqr_flag, z_flag)

    # 2) Multivariate anomaly detection
    iso_flag = detect_isolation_forest(df)

    # 3) Balance mismatch flag untuk investigasi data quality/rare case
    balance_flag, _ = detect_balance_mismatch(df)

    # 4) Cross-reference dengan cluster outlier Phase 2 dan interpretasi bisnis
    df = cross_reference(
        df,
        df_outliers,
        iqr_flag,
        z_flag,
        iso_flag,
        balance_flag,
    )

    # 5) Fraud validation + confusion matrix
    df, metrics = validate_fraud(df)

    # 6) Ringkasan untuk laporan/dashboard Phase 5
    summary_tables = summarize_investigation(df)
    summary_tables["fraud_validation_metrics"] = metrics

    # 7) Export transaksi mencurigakan dengan reason, risk level, anomaly type, dan category
    top_df = select_top_anomalies(df)
    export_results(
        top_df,
        "../datasets/phase_4/paysim-suspicious-transactions.parquet"
    )
    export_summary_tables(
        summary_tables,
        "../datasets/phase_4"
    )


if __name__ == "__main__":
    handling_outlier_pipeline()
