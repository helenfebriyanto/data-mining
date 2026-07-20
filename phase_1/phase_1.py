import os
from prefect import flow, task, get_run_logger
import pandas as pd
import numpy as np
from sklearn.preprocessing import RobustScaler
from scipy.stats import entropy as scipy_entropy
from joblib import dump

# LOAD DATA
@task
def load_data(path):
    logger = get_run_logger()
    df = pd.read_csv(path)
    
    describe = df.describe()

    logger.info(f"Loaded shape: {df.shape}")
    logger.info(f"Loaded describe:\n{describe}")
    logger.info(f"Loaded types: \n{df.dtypes}")
    return df

# DATA QUALITY CHECK
@task
def check_data(df):
    logger = get_run_logger()

    missing = df.isnull().sum()
    duplicates = df.duplicated().sum()
    unique = df.nunique()
    isFraudCount = df["isFraud"].value_counts()
    fraud_analysis = df.groupby("type")["isFraud"].agg(["sum", "mean", "count"])

    # Balance consistency errors
    origin_error = (
        df["oldbalanceOrg"]
        - df["amount"]
        - df["newbalanceOrig"]
    ).abs()

    destination_error = (
        df["oldbalanceDest"]
        + df["amount"]
        - df["newbalanceDest"]
    ).abs()

    origin_error_count = (origin_error > 0.01).sum()
    destination_error_count = (destination_error > 0.01).sum()

    # Origin by account type
    orig_err_C = (
        df[df["nameOrig"].str.startswith("C")]
        ["oldbalanceOrg"]
        .sub(df["amount"])
        .sub(df["newbalanceOrig"])
        .abs()
        .gt(0.01)
        .sum()
    )

    orig_err_M = (
        df[df["nameOrig"].str.startswith("M")]
        ["oldbalanceOrg"]
        .sub(df["amount"])
        .sub(df["newbalanceOrig"])
        .abs()
        .gt(0.01)
        .sum()
    )

    # Destination by account type
    dest_err_C = (
        df[df["nameDest"].str.startswith("C")]
        ["oldbalanceDest"]
        .add(df["amount"])
        .sub(df["newbalanceDest"])
        .abs()
        .gt(0.01)
        .sum()
    )

    dest_err_M = (
        df[df["nameDest"].str.startswith("M")]
        ["oldbalanceDest"]
        .add(df["amount"])
        .sub(df["newbalanceDest"])
        .abs()
        .gt(0.01)
        .sum()
    )

    nameDest_count = df["nameDest"].str[0].value_counts()

    logger.info(f"Missing values:\n{missing}")
    logger.info(f"Unique values:\n{unique}")
    logger.info(f"Duplicates: {duplicates}")
    logger.info(f"isFraud Count:\n{isFraudCount}")
    logger.info(f"Fraud analysis by transaction type:\n{fraud_analysis}")

    logger.info(f"Origin error transactions: {origin_error_count}")
    logger.info(f"Destination error transactions: {destination_error_count}")

    logger.info(f"Origin error statistics:\n{origin_error.describe()}")
    logger.info(f"Destination error statistics:\n{destination_error.describe()}")

    logger.info(f"Origin error (Customer): {orig_err_C}")
    logger.info(f"Origin error (Merchant): {orig_err_M}")

    logger.info(f"Destination error (Customer): {dest_err_C}")
    logger.info(f"Destination error (Merchant): {dest_err_M}")

    logger.info(f"Name Destination Count:\n{nameDest_count}")

    return df

# CLEANING
@task
def clean_data(df):
    logger = get_run_logger()
    
    before = len(df)
    df = df.drop_duplicates()
    logger.info(f"Duplicates removed: {before - len(df)}")
    
    before = len(df)
    df = df[df["amount"] > 0].copy()
    logger.info(f"Zero amount removed: {before - len(df)}")
    
    df = df.drop(columns=["isFlaggedFraud"], errors="ignore")
    df = df.drop(columns=["nameOrig"], errors="ignore")
    
    logger.info("Dropped unnecessary columns")
    
    return df

# FEATURE ENGINEERING
@task
def feature_engineering(df):
    logger = get_run_logger()

    df["origError"] = (
        df["oldbalanceOrg"]
        - df["amount"]
        - df["newbalanceOrig"]
    ).abs()

    df["destError"] = (
        df["oldbalanceDest"]
        + df["amount"]
        - df["newbalanceDest"]
    ).abs()

    df["isDestMerchant"] = (
        df["nameDest"].str.startswith("M")
    ).astype(np.int8)

    df["origDrainedToZero"] = (
        (df["oldbalanceOrg"] > 0)
        & (df["newbalanceOrig"] == 0)
    ).astype(np.int8)

    df = df.drop(columns=["nameDest"], errors="ignore")

    logger.info("Feature engineering complete")

    return df

# TRANSFORM (ENCODING + SCALING)
@task
def transform_data(df):
    logger = get_run_logger()

    df = pd.concat(
        [
            df.drop(columns=["type"]),
            pd.get_dummies(
                df["type"],
                prefix="type",
                dtype=np.int8
            )
        ],
        axis=1
    )

    scale_cols = [
        "amount",
        "oldbalanceOrg",
        "oldbalanceDest",
        "origError",
        "destError",
        "step"
    ]

    # 1. Aplikasikan Log1p terlebih dahulu untuk meredam skewness ekstrem
    # (Semua nilai di dalam scale_cols sudah pasti positif atau 0, jadi np.log1p aman digunakan)
    for col in scale_cols:
        df[col] = np.log1p(df[col])

    # 2. Aplikasikan RobustScaler pada data yang sudah ditransformasi logaritmik
    scaler = RobustScaler()
    df[scale_cols] = scaler.fit_transform(df[scale_cols])

    # Mengurangi penggunaan memori
    df[scale_cols] = df[scale_cols].astype(np.float32)

    models_dir = "../models"
    os.makedirs(models_dir, exist_ok=True)

    scaler_path = os.path.join(
        models_dir,
        "robust_scaler.pkl"
    )

    dump(scaler, scaler_path)

    logger.info(f"Scaler saved to: {scaler_path}")
    logger.info("Log1p Transformation + Robust Scaling done")

    return df

# FEATURE SELECTION
@task
def feature_selection(df):
    logger = get_run_logger()
    
    cols_to_drop = ["newbalanceOrig", "newbalanceDest"]
    df = df.drop(columns=cols_to_drop, errors="ignore")
    
    logger.info("Dropped multicollinear features")
    
    return df

# SAVE
@task
def save_data(df, path):
    df.to_parquet(path, index=False)
    
    logger = get_run_logger()
    logger.info(f"Saved to {path}")

# FLOW
@flow(name="Phase 1")
def preprocessing_pipeline():
    
    raw_path = "../datasets/paysim-dataset.csv"
    output_path = "../datasets/phase_1/paysim-dataset.parquet"
    
    df = load_data(raw_path)
    df = check_data(df)
    df = clean_data(df)
    df = feature_engineering(df)
    df = transform_data(df)
    df = feature_selection(df)
    
    save_data(df, output_path)

# RUN
if __name__ == "__main__":
    preprocessing_pipeline()