from prefect import flow, task, get_run_logger
import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest


# LOAD DATA
@task
def load_data(path, path_outlier):
    logger = get_run_logger()
    df = pd.read_parquet(path)
    df_outliers = pd.read_parquet(path_outlier)
    logger.info(f"Data Shape: {df.shape}")
    logger.info(f"Data Outliers Shape: {df_outliers.shape}")
    logger.info(f"Columns: {list(df.columns)}")
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
    print(f"IQR {column} anomalies:", flag.sum())

    logger.info(
    f"""
        IQR Detection - {column}
        Q1: {Q1:.2f}
        Q3: {Q3:.2f}
        IQR: {IQR:.2f}
        Lower Bound: {lower:.2f}
        Upper Bound: {upper:.2f}
        Total Anomalies: {flag.sum()} ({(flag.mean()*100):.2f}%)""")
    
    extreme_values = df.loc[flag == 1, column]

    logger.info(
        f"Max anomaly value: {extreme_values.max():.2f}, "
        f"Min anomaly value: {extreme_values.min():.2f}"
    )
    return flag

@task
def detect_zscore(df, column):
    logger = get_run_logger()

    mean = df[column].mean()
    std = df[column].std()

    z = (df[column] - mean) / std
    flag = (np.abs(z) > 3).astype(int)

    logger.info(
        f"""
        Z-Score Detection - {column}
        Mean: {mean:.4f}
        Std Dev: {std:.4f}
        Threshold: |Z| > 3
        Total Anomalies: {flag.sum()} ({(flag.mean()*100):.2f}%)""")

    # ambil nilai ekstrem
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

    combined = (iqr_flag + z_flag)

    logger.info(f"Total combined anomalies (>=1): {(combined >= 1).sum()}")
    logger.info(f"High risk (>=2 methods): {(combined >= 2).sum()}")

    return combined

@task #multivariate anomaly detection, jadi tujuannya untuk mendeteksi anomali tersembunyi berdasarkan kombinasi fitur transaksi, bukan hanya nilai ekstrem individual
def detect_isolation_forest(df):
    logger = get_run_logger()

    # copy dataframe untuk keamanan
    df = df.copy()

    # fitur untuk anomaly detection
    feature_cols = ["amount", "balanceDiffOrig"]

    # handle missing values
    features = df[feature_cols].fillna(0)

    # model Isolation Forest
    model = IsolationForest(
        contamination=0.01,
        random_state=42
    )

    # prediksi anomaly
    preds = model.fit_predict(features)

    # convert:
    # -1 = anomaly -> 1
    #  1 = normal  -> 0
    flag = (preds == -1).astype(int)

    # logging summary
    logger.info(
        (
            "Isolation Forest Detection\n"
            f"Features Used      : {', '.join(feature_cols)}\n"
            "Contamination      : 0.01\n"
            f"Total Anomalies    : {flag.sum()} "
            f"({(flag.mean() * 100):.2f}%)"
        )
    )

    # ambil data anomaly
    anomaly_data = df.loc[
        flag == 1,
        ["amount", "balanceDiffOrig"]
    ]

    # logging nilai ekstrem
    if not anomaly_data.empty:
        logger.info(
            (
                "Isolation Forest Extreme Values\n"
                f"Max Amount Anomaly      : "
                f"{anomaly_data['amount'].max():.2f}\n"
                f"Min Amount Anomaly      : "
                f"{anomaly_data['amount'].min():.2f}\n"
                f"Max BalanceDiffOrig    HDBSCAN Colum : "
                f"{anomaly_data['balanceDiffOrig'].max():.2f}\n"
                f"Min BalanceDiffOrig     : "
                f"{anomaly_data['balanceDiffOrig'].min():.2f}"
            )
        )

    return flag

@task
#tujuan untuk menggabungkan anomaly detection karena disinilah semua hasil anomaly detection digabungkan jadi sinyal risiko tinggi
def cross_reference(df, df_outliers, iqr_flag, z_flag, iso_flag):
    logger = get_run_logger()

    # copy dataframe agar aman
    df = df.copy()

    # simpan hasil anomaly detection
    df["flag_IQR"] = iqr_flag
    df["flag_ZScore"] = z_flag
    df["flag_IsoForest"] = iso_flag

    # CEK nama kolom dataframe outlier
    logger.info(f"HDBSCAN Columns: {list(df_outliers.columns)}")

    # DEBUG isi dataframe outlier
    logger.info(f"ns: {list(df_outliers.columns)}")
    logger.info(f"\n{df_outliers.head()}")

    # sementara disable HDBSCAN
    # karena kolom cluster belum ada
    df["flag_HDBSCAN"] = (df["cluster_hdbscan"] == -1).astype(int)

    # hitung risk score
    df["risk_score"] = (
        df["flag_IQR"] +
        df["flag_ZScore"] +
        df["flag_IsoForest"] +
        df["flag_HDBSCAN"]
    )

    # transaksi high risk jika kena >= 2 metode
    df["high_risk"] = (
        df["risk_score"] >= 2
    ).astype(int)

    # logging summary
    logger.info(
        (
            "Cross Reference Detection\n"
            f"Total Transactions      : {len(df)}\n"
            f"IQR Anomalies           : {df['flag_IQR'].sum()}\n"
            f"Z-Score Anomalies       : {df['flag_ZScore'].sum()}\n"
            f"Isolation Forest        : {df['flag_IsoForest'].sum()}\n"
            f"HDBSCAN Outliers        : {df['flag_HDBSCAN'].sum()}\n"
            f"High Risk Transactions  : {df['high_risk'].sum()} "
            f"({(df['high_risk'].mean() * 100):.2f}%)"
        )
    )

    # distribusi risk score
    logger.info(
        (
            "Risk Score Distribution\n"
            f"{df['risk_score'].value_counts().sort_index()}"
        )
    )

    return df

@task
#membuktikan apakah transaksi high risk memang fraud, penting karena Anomaly ≠ selalu fraud.
def validate_fraud(df):
    logger = get_run_logger()

    fraud_rate = df[df["high_risk"] == 1]["isFraud"].mean()

    logger.info(
        (
            "Fraud Validation\n"
            f"High Risk Transactions : {df['high_risk'].sum()}\n"
            f"Fraud Match Rate       : {(fraud_rate * 100):.2f}%"
        )
    )

    return df

@task
#memilih transaksi yang paling mencurigakan berdasarkan risk_score, karena dataframenya isinya masih banyak trs kita ambil sebagian yang paling ekstrem
def select_top_anomalies(df, top_n=20000):
    logger = get_run_logger()

    top_df = df.sort_values(
        by="risk_score",
        ascending=False
    ).head(top_n)

    logger.info(
        (
            "Top Suspicious Transactions\n"
            f"Selected Rows : {len(top_df)}"
        )
    )

    return top_df

@task
def export_results(df, output_path):
    logger = get_run_logger()

    df.to_parquet(output_path, index=False)

    logger.info(f"Exported Result: {output_path}")

@flow
def handling_outlier_pipeline():
    path_1 = "../datasets/phase_2/paysim-dataset-phase2.parquet"
    path_2 = "../datasets/phase_2/paysim-outliers-phase4.parquet"
    # output_path = "../datasets/phase_1/paysim-dataset.parquet"
    df, df_outliers = load_data(path_1, path_2)

    #anomaly detection
    iqr_flag = detect_iqr(df, "amount")
    z_flag = detect_zscore(df, "amount")
    combined = combine_flags(iqr_flag, z_flag)
    iso_flag = detect_isolation_forest(df)

    #cross reference
    df = cross_reference(
        df,
        df_outliers,
        iqr_flag,
        z_flag,
        iso_flag
    )

    #validation
    df = validate_fraud(df)

    # select top suspicious transactions
    top_df = select_top_anomalies(df)

    # export result
    export_results(
        top_df,
        "../datasets/phase_4/paysim-suspicious-transactions.parquet"
    )

if __name__ == "__main__":
    handling_outlier_pipeline()