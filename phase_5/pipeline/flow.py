"""
pipeline/flow.py
==================
Pipeline Prefect Phase 5 - satu perintah untuk membangun seluruh data yang
dipakai dashboard, menyambung gaya pipeline Phase 1-4 kelompok sebelumnya
(@flow/@task Prefect yang sama).

CARA PAKAI
----------
1) Kalau kelompok sudah punya output Phase 1-4 asli di komputer sendiri:

     python -m pipeline.flow --mode real --data-root /path/ke/project

   `--data-root` diharapkan berisi struktur folder yang SAMA seperti dashboard
   versi sebelumnya (phase_2/, phase_3/, phase_4/, models/) - lihat README.
   Kalau tersedia, pipeline akan lebih memilih dataset skor PENUH (6,3 juta
   baris) bila kelompok menambahkan satu baris export di phase_4.py (lihat
   README bagian "Mengaktifkan pencarian atas seluruh 6,3 juta baris"). Kalau
   tidak ada, pipeline otomatis jalan dengan cakupan baris yang lebih sempit
   (20.000 transaksi paling mencurigakan dari top_suspicious_light.parquet)
   dan memberi tahu jelas lewat log + manifest.json.

2) Mode demo/pengembangan (dipakai saat proyek ini dibangun, TANPA data asli):

     python -m pipeline.flow --mode synthetic

   Menghasilkan dataset uji ~6,3 juta baris yang meniru statistik agregat
   asli (lihat tools/generate_synthetic_data.py) - PENTING dipakai HANYA
   untuk uji coba dashboard, bukan pengganti data asli kelompok.

Kedua mode berakhir di artefak yang sama: data/fance_dashboard.duckdb (selalu
ditulis) + index Elasticsearch (ditulis best-effort kalau ELASTICSEARCH_URL
bisa dihubungi; pipeline TIDAK gagal total kalau Elasticsearch mati).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import duckdb
import numpy as np
import pandas as pd
from prefect import flow, task, get_run_logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg
from pipeline.enrich import build_rule_pool, standardize_schema

REAL_TOP10_FALLBACK = pd.DataFrame([
    dict(antecedents_str="origError_very_low, orig_drained_yes", consequents_str="isFraud_yes",
         support=0.001259, confidence=1.000000, lift=776.211297),
    dict(antecedents_str="cluster_kmeans_2, orig_drained_yes", consequents_str="isFraud_yes",
         support=0.000154, confidence=1.000000, lift=776.211297),
    dict(antecedents_str="hdbscan_outlier, origError_very_low", consequents_str="isFraud_yes",
         support=0.000103, confidence=0.904432, lift=702.030439),
    dict(antecedents_str="cluster_kmeans_2, origError_very_low", consequents_str="isFraud_yes",
         support=0.000161, confidence=0.649746, lift=504.340335),
    dict(antecedents_str="type_DEBIT", consequents_str="amount_very_low, cluster_kmeans_1",
         support=0.005904, confidence=0.906618, lift=4.597684),
    dict(antecedents_str="destError_low", consequents_str="amount_very_low, cluster_kmeans_1",
         support=0.176434, confidence=0.882169, lift=4.473699),
    dict(antecedents_str="type_DEBIT", consequents_str="amount_very_low, destError_very_low",
         support=0.005420, confidence=0.832352, lift=47.200336),
    dict(antecedents_str="cluster_kmeans_3", consequents_str="oldbalanceOrg_very_high, type_CASH_IN",
         support=0.014070, confidence=0.998405, lift=7.325951),
    dict(antecedents_str="cluster_kmeans_2", consequents_str="oldbalanceOrg_very_high, type_CASH_IN",
         support=0.061243, confidence=0.995951, lift=7.307946),
    dict(antecedents_str="cluster_kmeans_2", consequents_str="destError_very_high, oldbalanceOrg_very_high",
         support=0.048769, confidence=0.793104, lift=7.197255),
])

CUBE_GROUP_COLS = [
    "wilayah", "transaction_type", "cluster_kmeans", "isFraud",
    "flag_IQR", "flag_ZScore", "flag_IsoForest", "flag_HDBSCAN", "flag_BalanceMismatch",
    "risk_score", "risk_level", "anomaly_type", "investigation_category", "high_risk",
]


@task(retries=1, log_prints=True)
def load_transaction_data(mode: str, data_root: Optional[str], synthetic_path: Optional[str],
                          work_dir: str) -> str:
    """Mengembalikan PATH ke parquet yang siap dipakai (bukan DataFrame di
    memori) - tabel transaksi bisa jutaan baris, meneruskannya sbg objek
    Python antar-task Prefect boros memori (pernah OOM saat dites, lihat
    catatan proses). DuckDB & Elasticsearch membaca file ini langsung."""
    logger = get_run_logger()
    if mode == "synthetic":
        path = Path(synthetic_path)
        logger.info(f"[mode=synthetic] Memakai dataset uji {path} (skema sudah lengkap, tanpa transformasi tambahan)")
        return str(path)

    root = Path(data_root)
    full_candidates = [
        root / "phase_4" / "paysim_full_scored.parquet",
        root / "phase_4" / "full_scored_transactions.parquet",
        root / "data" / "paysim_full_scored.parquet",
    ]
    source_path = None
    for p in full_candidates:
        if p.exists():
            logger.info(f"[mode=real] Dataset skor PENUH ditemukan: {p} (cakupan 6,3 juta baris)")
            source_path = p
            break
    if source_path is None:
        fallback = root / "phase_5" / "cache" / "top_suspicious_light.parquet"
        if fallback.exists():
            logger.warning(
                "Dataset skor penuh (6,3 juta baris) TIDAK ditemukan. Pipeline memakai "
                f"{fallback} (20.000 transaksi paling mencurigakan saja). Untuk mengaktifkan "
                "pencarian atas SELURUH data, tambahkan satu baris export di phase_4.py - "
                "lihat README bagian 'Mengaktifkan pencarian atas seluruh 6,3 juta baris'."
            )
            source_path = fallback
        else:
            raise FileNotFoundError(
                f"Tidak menemukan dataset transaksi di bawah {root}. Cek --data-root, atau "
                "gunakan --mode synthetic untuk data uji."
            )

    logger.info("[mode=real] Menerapkan lapisan presentasi (wilayah, label ID, alasan anomali) ...")
    df = standardize_schema(pd.read_parquet(source_path))
    out_path = Path(work_dir) / "transaksi_enriched.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    del df
    return str(out_path)


@task(log_prints=True)
def load_rule_pool_task(mode: str, data_root: Optional[str]) -> pd.DataFrame:
    logger = get_run_logger()
    if mode == "synthetic":
        sample_path = Path(synthetic_path_default()).parent / "sample_for_rule_mining.parquet"
        logger.info(f"[mode=synthetic] Menambang ulang pola dari sampel pra-hitung {sample_path}")
        from tools.build_rules_and_db import mine_rules
        sample = pd.read_parquet(sample_path)
        mined = mine_rules(sample)
        return _merge_mined(mined, logger)

    root = Path(data_root)
    return build_rule_pool(phase3_dir=root / "phase_3", top10_fallback=REAL_TOP10_FALLBACK, logger=logger)


def synthetic_path_default() -> str:
    return str(Path(__file__).resolve().parent.parent / "data" / "raw_synthetic" / "synthetic_transactions.parquet")


def _merge_mined(mined: pd.DataFrame, logger) -> pd.DataFrame:
    top10 = REAL_TOP10_FALLBACK.copy()
    top10["is_real"] = True
    mined = mined.copy()
    mined["is_real"] = False
    key = set(zip(top10["antecedents_str"], top10["consequents_str"]))
    mined = mined[~mined.apply(lambda r: (r["antecedents_str"], r["consequents_str"]) in key, axis=1)]
    combined = pd.concat([top10, mined], ignore_index=True)
    from pipeline.enrich import _rule_group_of, _takeaway_and_recommendation
    combined["rule_group"] = combined.apply(lambda r: _rule_group_of(r["antecedents_str"], r["consequents_str"]), axis=1)
    combined["when_text"] = combined["antecedents_str"].apply(cfg.humanize_item_list)
    combined["then_text"] = combined["consequents_str"].apply(cfg.humanize_item_list)
    combined["coverage_fmt"] = combined["support"].apply(lambda x: cfg.format_pct(x, 3))
    combined["confidence_fmt"] = combined["confidence"].apply(lambda x: cfg.format_pct(x, 1))
    combined["lift_fmt"] = combined["lift"].apply(cfg.format_multiplier)
    tk = combined.apply(_takeaway_and_recommendation, axis=1, result_type="expand")
    combined["takeaway"], combined["recommendation"] = tk[0], tk[1]
    combined = combined.sort_values(["is_real", "lift"], ascending=[False, False]).reset_index(drop=True)
    combined["is_top10"] = combined["is_real"]
    combined["rule_id"] = [f"POLA{i+1:04d}" for i in range(len(combined))]
    combined["penting"] = np.where(combined["is_top10"], "Insight utama", "Insight tambahan")
    return combined


@task(log_prints=True)
def write_duckdb(transaksi_path: str, rules: pd.DataFrame, db_path: str) -> dict:
    logger = get_run_logger()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    if Path(db_path).exists():
        Path(db_path).unlink()
    con = duckdb.connect(db_path)
    con.execute("PRAGMA memory_limit='900MB'")
    con.execute("PRAGMA threads=1")
    con.execute(f"PRAGMA temp_directory='{Path(db_path).parent / 'duckdb_tmp'}'")
    logger.info("  [checkpoint] koneksi DuckDB dibuat, mulai baca parquet ...")
    con.execute("CREATE TABLE transaksi AS SELECT * FROM read_parquet(?)", [transaksi_path])
    logger.info("  [checkpoint] tabel transaksi selesai ditulis")
    cols_present = set(con.execute("SELECT * FROM transaksi LIMIT 0").description and
                        [d[0] for d in con.execute("SELECT * FROM transaksi LIMIT 0").description])
    for col in ["wilayah", "transaction_type", "risk_level", "anomaly_type", "investigation_category", "transaction_id"]:
        if col in cols_present:
            con.execute(f"CREATE INDEX idx_{col} ON transaksi ({col})")
    if "risk_score" in cols_present:
        con.execute("CREATE INDEX idx_risk_score ON transaksi (risk_score)")
    if "amount" in cols_present:
        con.execute("CREATE INDEX idx_amount ON transaksi (amount)")
    logger.info("  [checkpoint] indeks tabel transaksi selesai")

    con.register("rules_view", rules)
    con.execute("CREATE TABLE pola AS SELECT * FROM rules_view")

    group_cols_present = [c for c in CUBE_GROUP_COLS if c in cols_present]
    group_sql = ", ".join(group_cols_present)
    logger.info(f"  [checkpoint] mulai bangun cube (group by {len(group_cols_present)} kolom) ...")
    con.execute(f"""
        CREATE TABLE cube AS
        SELECT {group_sql}, COUNT(*) AS n
        FROM transaksi GROUP BY {group_sql}
    """)
    logger.info("  [checkpoint] cube selesai dibangun")
    for col in ["wilayah", "transaction_type", "cluster_kmeans", "risk_level"]:
        if col in group_cols_present:
            con.execute(f"CREATE INDEX idx_cube_{col} ON cube ({col})")

    n_transaksi = con.execute("SELECT COUNT(*) FROM transaksi").fetchone()[0]
    n_cube = con.execute("SELECT COUNT(*) FROM cube").fetchone()[0]
    n_pola = con.execute("SELECT COUNT(*) FROM pola").fetchone()[0]
    con.close()
    logger.info(f"DuckDB ditulis: {db_path} | transaksi={n_transaksi:,} cube={n_cube:,} pola={n_pola}")
    return dict(n_transaksi=n_transaksi, n_cube=n_cube, n_pola=n_pola)


@task(log_prints=True)
def index_elasticsearch(db_path: str, es_url: str) -> dict:
    """Best-effort: kalau Elasticsearch tidak menyala, task ini TIDAK menggagalkan
    seluruh flow - dashboard tetap bisa jalan dgn DuckDB (lihat app.py). Membaca
    dari DuckDB dalam potongan (chunk) supaya tidak perlu menyimpan seluruh
    tabel transaksi di memori Python sekaligus."""
    logger = get_run_logger()
    try:
        from elasticsearch import Elasticsearch
        from pipeline.es_indexer import TRANSAKSI_MAPPING, POLA_MAPPING, recreate_index, bulk_index_dataframe
    except ImportError:
        logger.warning("Package 'elasticsearch' belum terpasang - lewati indexing (DuckDB tetap jadi sumber data).")
        return {"status": "skipped", "reason": "package elasticsearch tidak terpasang"}

    import logging as _logging
    _logging.getLogger("elastic_transport").setLevel(_logging.CRITICAL)  # redam log retry yg berisik saat ES belum nyala

    try:
        client = Elasticsearch(es_url, request_timeout=2, max_retries=0)
        if not client.ping():
            raise ConnectionError("ping gagal")
    except Exception as e:
        logger.warning(
            f"Elasticsearch tidak terjangkau di {es_url}. Melewati indexing - dashboard tetap "
            "berjalan penuh memakai DuckDB. Jalankan `docker-compose up -d` lalu ulangi pipeline "
            "kalau ingin memakai Elasticsearch."
        )
        return {"status": "skipped", "reason": str(e)}

    from pipeline.es_indexer import INDEX_TRANSAKSI, INDEX_POLA
    t0 = time.perf_counter()
    recreate_index(client, INDEX_TRANSAKSI, TRANSAKSI_MAPPING)
    recreate_index(client, INDEX_POLA, POLA_MAPPING)

    con = duckdb.connect(db_path, read_only=True)
    total_transaksi = con.execute("SELECT COUNT(*) FROM transaksi").fetchone()[0]
    n1 = 0
    chunk_size = 20_000
    for offset in range(0, total_transaksi, chunk_size):
        chunk_df = con.execute(f"SELECT * FROM transaksi LIMIT {chunk_size} OFFSET {offset}").df()
        n1 += bulk_index_dataframe(client, chunk_df, INDEX_TRANSAKSI, id_col="transaction_id", logger=None)
        if (offset // chunk_size) % 20 == 0:
            logger.info(f"  indexing transaksi: {min(offset + chunk_size, total_transaksi):,}/{total_transaksi:,}")
    rules_df = con.execute("SELECT * FROM pola").df()
    con.close()
    n2 = bulk_index_dataframe(client, rules_df, INDEX_POLA, id_col="rule_id", logger=logger)

    client.indices.refresh(index=INDEX_TRANSAKSI)
    client.indices.refresh(index=INDEX_POLA)
    dt = time.perf_counter() - t0
    logger.info(f"Elasticsearch: {n1:,} transaksi + {n2} pola ter-index dalam {dt:.1f}s")
    return {"status": "ok", "n_transaksi": n1, "n_pola": n2, "detik": round(dt, 1)}


@task
def write_manifest(db_stats: dict, es_stats: dict, mode: str, manifest_path: str):
    Path(manifest_path).parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "dibuat_pada": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "duckdb": db_stats,
        "elasticsearch": es_stats,
    }
    Path(manifest_path).write_text(json.dumps(manifest, indent=2, ensure_ascii=False))


@flow(name="phase5-dashboard-pipeline", log_prints=True)
def phase5_pipeline(
    mode: str = "synthetic",
    data_root: Optional[str] = None,
    synthetic_path: str = str(Path(__file__).resolve().parent.parent / "data" / "raw_synthetic" / "synthetic_transactions.parquet"),
    db_path: str = str(Path(__file__).resolve().parent.parent / "data" / "fance_dashboard.duckdb"),
    manifest_path: str = str(Path(__file__).resolve().parent.parent / "data" / "manifest.json"),
    work_dir: str = str(Path(__file__).resolve().parent.parent / "data" / "_work"),
    es_url: Optional[str] = None,
):
    logger = get_run_logger()
    logger.info(f"=== Pipeline Phase 5 (Kelompok Fance) - mode={mode} ===")
    es_url = es_url or cfg.ELASTICSEARCH_URL

    transaksi_path = load_transaction_data(mode, data_root, synthetic_path, work_dir)
    rules = load_rule_pool_task(mode, data_root)
    db_stats = write_duckdb(transaksi_path, rules, db_path)
    es_stats = index_elasticsearch(db_path, es_url)
    write_manifest(db_stats, es_stats, mode, manifest_path)
    logger.info("=== Pipeline selesai ===")
    return {"duckdb": db_stats, "elasticsearch": es_stats}


def _parse_args():
    p = argparse.ArgumentParser(description="Pipeline Phase 5 - Dashboard Kelompok Fance")
    p.add_argument("--mode", choices=["real", "synthetic"], default="synthetic")
    p.add_argument("--data-root", default=None, help="Folder root project Phase 1-4 asli (mode=real)")
    p.add_argument("--es-url", default=None)
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.mode == "real" and not args.data_root:
        print("--data-root wajib diisi utk --mode real", file=sys.stderr)
        sys.exit(1)
    phase5_pipeline(mode=args.mode, data_root=args.data_root, es_url=args.es_url)
