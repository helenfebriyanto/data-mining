import pandas as pd 
import numpy as np 
import gc 
import os 
from sklearn.cluster import KMeans 
from sklearn.decomposition import PCA
import hdbscan 
from prefect import task, flow, get_run_logger

# Kmeans
@task(name="1. Kmeans clustering", retries=1)
def task_kmeans(input_path, output_path):
    logger = get_run_logger()


    logger.info(f"Read data from {input_path}")
    df = pd.read_parquet(input_path)
    X_clean = df.drop(columns=['isFraud'], errors='ignore')
    
    logger.info(f"Run kmeans for 6.3 mio data")
    kmeans = KMeans(n_clusters=4, init='k-means++', random_state=42, n_init=10)
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

# HDBSCAN 
@task(name="2. HDBSCAN outlier", retries=1)
def task_hdbscan(input_path, output_path):
    logger = get_run_logger()

    logger.info(f"Read data from {input_path}")
    df = pd.read_parquet(input_path)
    X_clean = df.drop(columns=['isFraud', 'cluster_kmeans'], errors='ignore')

    logger.info(f"PCA for dimensionality reduction")
    pca = PCA(n_components=0.95)
    X_reduced = pca.fit_transform(X_clean).astype('float32')

    logger.info(f"Train HDBSCAN model with 100.000 random sample")
    np.random.seed(42)
    sample_indices = np.random.choice(X_reduced.shape[0], size=100000, replace=False)
    X_reduced_sample = X_reduced[sample_indices]

    hdbscan_cpu = hdbscan.HDBSCAN(
        min_cluster_size=1000,
        min_samples=50,
        prediction_data=True,
        core_dist_n_jobs=-1
    )
    hdbscan_cpu.fit(X_reduced_sample)

    logger.info(f"Predict 6.3 mio data with batch system")
    batch_size = 500000
    all_labels = []

    for i in range(0, len(X_reduced), batch_size):
        X_batch = X_reduced[i : i+ batch_size]
        batch_labels, _ = hdbscan.approximate_predict(hdbscan_cpu, X_batch)
        all_labels.extend(batch_labels)

    df['cluster_dbscan'] = all_labels

    outlier_count = (df['cluster_dbscan'] == -1).sum()
    print(f'Outlier count from hDBCSAN (label -1): {outlier_count} dots')

    # We save this file in task 2 so the task 3 doesnt need to re read the whole file
    logger.info("Saving to parquet")

    output_dir = os.path.dirname(output_path)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    df.to_parquet(output_path, index=False)

    logger.info("Saved to parquet")

    del df, X_clean, X_reduced, X_reduced_sample, hdbscan_cpu, all_labels, X_batch, batch_labels
    gc.collect()

    return output_path

# Export and split data for next phase 
@task(name="3. Export data for phase 3 and 4", retries=1)
def task_export(final_input_path):
    logger = get_run_logger()

    folder_path = "../datasets/phase_2"

    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    
    logger.info("Split data outlier and profiling")
    df_final = pd.read_parquet(final_input_path)

    # Outlier dataset
    df_outliers = df_final[df_final['cluster_dbscan'] == -1].copy()
    df_outliers.to_parquet(os.path.join(folder_path, 'paysim-outliers-phase4.parquet'), index=False)

    # Profiling cluster
    cluster_profiles = df_final.groupby('cluster_kmeans').mean()
    cluster_profiles.to_csv(os.path.join(folder_path, 'cluster-summary-phase2.csv'))

    logger.info("Export finished")

    del df_final, df_outliers, cluster_profiles
    gc.collect()

# Flow
@flow(name="Data Mining Phase 2: Full Pipeline")
def phase2_pipeline():
    logger = get_run_logger()

    file_raw = "../datasets/phase_1/paysim-dataset.parquet"
    file_kmeans_temp = "../datasets/phase_2/temp_kmeans.parquet"
    file_final_out =  "../datasets/phase_2/paysim-dataset-phase2.parquet"

    logger.info("Start pipeline phase 2")

    path_kmeans = task_kmeans(input_path=file_raw, output_path=file_kmeans_temp)
    path_final = task_hdbscan(input_path=path_kmeans, output_path=file_final_out)
    task_export(final_input_path=path_final)

    if os.path.exists(file_kmeans_temp):
        os.remove(file_kmeans_temp)
    
    logger.info("All pipeline finished successfully")

if __name__ == "__main__":
    phase2_pipeline()