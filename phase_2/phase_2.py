import pandas as pd
import numpy as np
import gc
import os
from sklearn.cluster import KMeans, Birch, MiniBatchKMeans
from sklearn.decomposition import PCA
import hdbscan
from prefect import task, flow, get_run_logger

NON_FEATURE_COLS = ['isFraud', 'step']


# 1. Kmeans (segmentasi 4 cluster)
@task(name="1. Kmeans clustering", retries=1)
def task_kmeans(input_path, output_path):
    logger = get_run_logger()

    logger.info(f"Read data from {input_path}")
    df = pd.read_parquet(input_path)

    X_clean = df.drop(columns=NON_FEATURE_COLS, errors='ignore')
    X_clean = X_clean.astype(np.float32)

    logger.info(f"Run kmeans for 6.3 mio data")
    kmeans = KMeans(n_clusters=5, init='k-means++', random_state=42, n_init=10)
    df['cluster_kmeans'] = kmeans.fit_predict(X_clean)

    logger.info(f"Saving temporary result of kmeans")

    output_dir = os.path.dirname(output_path)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    df.to_parquet(output_path, index=False)

    logger.info(f"Saved temporary result of kmeans")

    del df, X_clean, kmeans
    gc.collect()

    return output_path


# 2. HDBSCAN direct (baseline)
@task(name="2. HDBSCAN outlier (baseline, direct)", retries=1)
def task_hdbscan(input_path, output_path):
    logger = get_run_logger()

    logger.info(f"Read data from {input_path}")
    df = pd.read_parquet(input_path)
    X_clean = df.drop(columns=NON_FEATURE_COLS + ['cluster_kmeans'], errors='ignore')

    # FIX: fit langsung di ruang fitur penuh (bukan PCA 2D). PCA sebelumnya membuang
    # sebagian besar sinyal fraud (fitur origError/destError variansinya kecil
    # dibanding amount/oldbalance, jadi tenggelam saat direduksi ke 2D) - salah satu
    # sebab utama HDBSCAN langsung dulu gagal total (71% noise).
    logger.info("Stratified sampling 300.000 baris (proporsional per tipe transaksi)")
    type_cols = ["type_CASH_IN", "type_CASH_OUT", "type_DEBIT", "type_PAYMENT", "type_TRANSFER"]
    transaction_type = df[type_cols].idxmax(axis=1)
    fractions = transaction_type.value_counts(normalize=True)

    sample_size = 300000
    sample_indices = []
    for t, frac in fractions.items():
        n = int(sample_size * frac)
        idx = transaction_type[transaction_type == t].sample(n=n, random_state=42).index
        sample_indices.extend(idx)
    sample_indices = np.array(sample_indices)
    X_clean_sample = X_clean.loc[sample_indices]

    hdbscan_cpu = hdbscan.HDBSCAN(
        min_cluster_size=3000,
        min_samples=20,
        prediction_data=True,
        core_dist_n_jobs=-1,
        cluster_selection_method="eom",
    )
    hdbscan_cpu.fit(X_clean_sample)

    logger.info(f"Predict 6.3 mio data with batch system")
    batch_size = 500000
    all_labels = []

    for i in range(0, len(X_clean), batch_size):
        X_batch = X_clean[i: i + batch_size]
        batch_labels, _ = hdbscan.approximate_predict(hdbscan_cpu, X_batch)
        all_labels.extend(batch_labels)

    df['cluster_hdbscan'] = all_labels

    outlier_count = (df['cluster_hdbscan'] == -1).sum()
    logger.info(
        f"[Baseline HDBSCAN] Outlier count (label -1): {outlier_count:,} of {len(df):,} rows "
        f"({outlier_count / len(df) * 100:.1f}%) - kept for report comparison, "
        f"NOT used downstream (Phase 3/4 pakai cluster_birch_hdbscan)."
    )

    output_dir = os.path.dirname(output_path)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    df.to_parquet(output_path, index=False)

    del (df, X_clean, X_clean_sample, transaction_type, fractions, sample_indices,
         hdbscan_cpu, all_labels, X_batch, batch_labels)
    gc.collect()

    return output_path


# 3. BIRCH + HDBSCAN (hybrid)
@task(name="3. BIRCH + HDBSCAN hybrid outlier", retries=1)
def task_birch_hdbscan(input_path, output_path):
    logger = get_run_logger()

    logger.info(f"Read data from {input_path}")
    df = pd.read_parquet(input_path)
    X_clean = df.drop(
        columns=NON_FEATURE_COLS + ['cluster_kmeans', 'cluster_hdbscan'],
        errors='ignore'
    )
    X_clean = X_clean.astype(np.float32)

    logger.info("Fit BIRCH on full 6.3 mio data (threshold=0.3, branching_factor=50)")
    birch = Birch(threshold=0.3, branching_factor=50, n_clusters=None)
    birch.fit(X_clean)
    subcluster_centers = birch.subcluster_centers_.astype(np.float32)
    logger.info(f"BIRCH produced {len(subcluster_centers)} subclusters")

    logger.info("Assign each row to nearest BIRCH subcluster")
    subcluster_labels = birch.predict(X_clean)

    logger.info("MiniBatchKMeans on subcluster centers -> cluster_birch")
    mbk = MiniBatchKMeans(n_clusters=5, random_state=42, batch_size=512)
    mbk.fit(subcluster_centers)
    df['cluster_birch'] = mbk.labels_[subcluster_labels]

    logger.info("HDBSCAN on subcluster centers -> cluster_birch_hdbscan")
    hdbscan_birch = hdbscan.HDBSCAN(
        min_cluster_size=30,
        min_samples=10,
        cluster_selection_method="eom",
    )
    subcluster_hdbscan_labels = hdbscan_birch.fit_predict(subcluster_centers)
    df['cluster_birch_hdbscan'] = subcluster_hdbscan_labels[subcluster_labels]

    # FIX: outlier bukan selalu label -1 (noise). Cari cluster dengan fraud rate
    # TERTINGGI secara eksplisit - itulah kelompok yang benar-benar presisi untuk
    # deteksi risiko, terlepas dari nomor labelnya. Kolom ini yang dipakai Phase 3 & 4,
    # BUKAN pengecekan cluster_birch_hdbscan == -1 secara langsung.
    cluster_fraud_rate = df.groupby('cluster_birch_hdbscan')['isFraud'].mean()
    high_risk_cluster_id = cluster_fraud_rate.idxmax()
    df['is_birch_hdbscan_outlier'] = (
        df['cluster_birch_hdbscan'] == high_risk_cluster_id
    ).astype(int)

    outlier_count = int(df['is_birch_hdbscan_outlier'].sum())
    logger.info(
        f"[BIRCH+HDBSCAN] Highest fraud-rate cluster: {high_risk_cluster_id} "
        f"({cluster_fraud_rate.loc[high_risk_cluster_id] * 100:.2f}% fraud) | "
        f"Outlier count: {outlier_count:,} of {len(df):,} rows "
        f"({outlier_count / len(df) * 100:.2f}%)"
    )

    logger.info("Saving to parquet")
    output_dir = os.path.dirname(output_path)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    df.to_parquet(output_path, index=False)
    logger.info("Saved to parquet")

    del (df, X_clean, birch, subcluster_centers, subcluster_labels, mbk,
         hdbscan_birch, subcluster_hdbscan_labels)
    gc.collect()

    return output_path


# 4. Export data for next phase
@task(name="4. Export data for phase 3 and 4", retries=1)
def task_export(final_input_path):
    logger = get_run_logger()

    folder_path = "../datasets/phase_2"

    if not os.path.exists(folder_path):
        os.makedirs(folder_path)

    logger.info("Split data outlier and profiling")
    df_final = pd.read_parquet(final_input_path)

    df_outliers = df_final[df_final['is_birch_hdbscan_outlier'] == 1].copy()
    df_outliers.to_parquet(os.path.join(folder_path, 'paysim-outliers-phase4.parquet'), index=False)

    cluster_profiles = df_final.groupby('cluster_kmeans').mean(numeric_only=True)
    cluster_profiles.to_csv(os.path.join(folder_path, 'cluster-summary-phase2.csv'))

    logger.info(f"Exported {len(df_outliers):,} outlier rows to paysim-outliers-phase4.parquet")
    logger.info("Export finished")

    del df_final, df_outliers, cluster_profiles
    gc.collect()


# Flow
@flow(name="Data Mining Phase 2: Full Pipeline")
def phase2_pipeline():
    logger = get_run_logger()

    file_raw = "../datasets/phase_1/paysim-dataset.parquet"
    file_kmeans_temp = "../datasets/phase_2/temp_kmeans.parquet"
    file_hdbscan_temp = "../datasets/phase_2/temp_hdbscan.parquet"
    file_final_out = "../datasets/phase_2/paysim-dataset-phase2.parquet"

    logger.info("Start pipeline phase 2")

    path_kmeans = task_kmeans(input_path=file_raw, output_path=file_kmeans_temp)
    path_hdbscan = task_hdbscan(input_path=path_kmeans, output_path=file_hdbscan_temp)
    path_final = task_birch_hdbscan(input_path=path_hdbscan, output_path=file_final_out)
    task_export(final_input_path=path_final)

    for temp_file in (file_kmeans_temp, file_hdbscan_temp):
        if os.path.exists(temp_file):
            os.remove(temp_file)

    logger.info("All pipeline finished successfully")


if __name__ == "__main__":
    phase2_pipeline()