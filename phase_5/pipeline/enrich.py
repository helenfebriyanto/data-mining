"""
pipeline/enrich.py
====================
Fungsi transformasi "lapisan presentasi" yang dipakai pipeline/flow.py.

PENTING - batas tanggung jawab: modul ini TIDAK menghitung ulang clustering,
association rules, atau anomaly detection (itu tugas Phase 2-4 kelompok yang
sudah selesai dan HASILNYA dianggap final/benar). Modul ini HANYA menambah
lapisan presentasi di atas hasil tsb: label Indonesia, dimensi wilayah
(spasial ilustratif), teks alasan anomali, dan penggabungan pool aturan
asosiasi - supaya angka hasil analisis asli tidak pernah diubah/ditimpa.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

import config as cfg

WILAYAH_BASE_W = np.array([0.22, 0.15, 0.12, 0.14, 0.18, 0.08, 0.07, 0.04])


def assign_wilayah(df: pd.DataFrame, seed: int = 42) -> pd.Series:
    """Tempelkan dimensi 'wilayah' (spasial ILUSTRATIF, lihat WILAYAH_DISCLOSURE
    di config.py) secara deterministik: hash dari kombinasi kolom numerik yang
    ada pada baris itu sendiri (bukan indeks baris) supaya hasilnya stabil
    walau urutan baris berubah, dan tidak bergantung pada kolom ID apa pun
    (nameOrig/nameDest sudah didrop sejak Phase 1).
    """
    cols_for_hash = [c for c in ["amount", "oldbalanceOrg", "oldbalanceDest", "origError", "destError", "step"]
                      if c in df.columns]
    if not cols_for_hash:
        basis = pd.Series(np.arange(len(df)))
    else:
        basis = df[cols_for_hash].astype(str).agg("|".join, axis=1)

    def _hash_to_unit(s: str) -> float:
        h = hashlib.md5(f"{seed}|{s}".encode()).hexdigest()
        return int(h[:8], 16) / 0xFFFFFFFF

    u = basis.apply(_hash_to_unit).values
    # sedikit pemiringan berdasar segmen supaya pola spasial ada saat difilter
    # (murni utk demo interaktivitas - lihat WILAYAH_DISCLOSURE)
    tilt = np.ones(len(df))
    if "cluster_kmeans" in df.columns:
        tilt = np.where(df["cluster_kmeans"].values == 0, 1.4, 1.0)
    u = (u * tilt) % 1.0
    edges = np.cumsum(WILAYAH_BASE_W / WILAYAH_BASE_W.sum())
    idx = np.searchsorted(edges, u)
    idx = np.clip(idx, 0, len(cfg.WILAYAH_LIST) - 1)
    return pd.Series(np.array(cfg.WILAYAH_LIST)[idx], index=df.index)


def translate_categories(df: pd.DataFrame) -> pd.DataFrame:
    """Terjemahkan string kategori Phase 4 (Inggris) -> Indonesia. Aman dipanggil
    berkali-kali (no-op kalau kolom sudah berbahasa Indonesia). Memodifikasi df
    di tempat (TIDAK copy) - baris bisa jutaan, copy berulang = boros memori."""
    if "risk_level" in df.columns and set(df["risk_level"].unique()) & set(cfg.RISK_LEVEL_EN_TO_ID):
        df["risk_level"] = df["risk_level"].astype(str).map(lambda v: cfg.RISK_LEVEL_EN_TO_ID.get(v, v))
    if "anomaly_type" in df.columns and set(df["anomaly_type"].unique()) & set(cfg.ANOMALY_TYPE_EN_TO_ID):
        df["anomaly_type"] = df["anomaly_type"].astype(str).map(lambda v: cfg.ANOMALY_TYPE_EN_TO_ID.get(v, v))
    if "investigation_category" in df.columns and set(df["investigation_category"].unique()) & set(cfg.INVESTIGATION_CATEGORY_EN_TO_ID):
        df["investigation_category"] = df["investigation_category"].astype(str).map(
            lambda v: cfg.INVESTIGATION_CATEGORY_EN_TO_ID.get(v, v)
        )
    return df


_REASON_LOOKUP_CACHE = None


def _reason_lookup() -> np.ndarray:
    global _REASON_LOOKUP_CACHE
    if _REASON_LOOKUP_CACHE is not None:
        return _REASON_LOOKUP_CACHE
    labels = [
        "Nominal tinggi tak wajar (IQR)",
        "Nominal ekstrem (Z-Score)",
        "Kombinasi perilaku tak wajar (Isolation Forest)",
        "Menyimpang dari struktur klaster (BIRCH+HDBSCAN)",
        "Ketidaksesuaian saldo asal/tujuan",
    ]
    lookup = np.empty(32, dtype=object)
    for c in range(32):
        bits = [(c >> b) & 1 for b in range(5)]
        parts = [lbl for bit, lbl in zip(bits, labels) if bit]
        lookup[c] = "; ".join(parts) if parts else "Tidak ada indikator yang terpicu"
    _REASON_LOOKUP_CACHE = lookup
    return lookup


def compute_anomaly_reason(df: pd.DataFrame) -> pd.Series:
    """Vectorized (lookup 32 kombinasi) - JANGAN pakai df.apply(axis=1) di sini,
    terbukti lambat/OOM pada 6+ juta baris (lihat catatan proses)."""
    code = (
        df["flag_IQR"].astype(int).values * 1
        + df["flag_ZScore"].astype(int).values * 2
        + df["flag_IsoForest"].astype(int).values * 4
        + df["flag_HDBSCAN"].astype(int).values * 8
        + df.get("flag_BalanceMismatch", pd.Series(0, index=df.index)).astype(int).values * 16
    )
    return pd.Series(_reason_lookup()[code], index=df.index)


def ensure_transaction_id(df: pd.DataFrame) -> pd.Series:
    if "transaction_id" in df.columns:
        return df["transaction_id"]
    return pd.Series([f"TX{i:08d}" for i in range(len(df))], index=df.index)


def standardize_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Selaraskan nama kolom dari output Phase 1-4 asli (mis. 'type') ke skema
    yang dipakai dashboard ('transaction_type'). Aman dipanggil di data apa pun.
    TIDAK copy df (baris bisa jutaan) - pemanggil diharapkan sudah punya
    referensi frame yang aman dimodifikasi (baru dibaca dari parquet/CSV)."""
    rename_map = {"type": "transaction_type"}
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns and v not in df.columns})
    if "high_risk" not in df.columns and "risk_score" in df.columns:
        hdb = df["flag_HDBSCAN"] if "flag_HDBSCAN" in df.columns else 0
        df["high_risk"] = (df["risk_score"] >= cfg.HIGH_RISK_THRESHOLD) | (hdb == 1)
    if "wilayah" not in df.columns:
        df["wilayah"] = assign_wilayah(df)
    if "transaction_id" not in df.columns:
        df["transaction_id"] = ensure_transaction_id(df)
    df = translate_categories(df)
    if "anomaly_reason" not in df.columns and all(
        c in df.columns for c in ["flag_IQR", "flag_ZScore", "flag_IsoForest", "flag_HDBSCAN"]
    ):
        df["anomaly_reason"] = compute_anomaly_reason(df)
    return df


# ---------------------------------------------------------------------------
# Pool aturan asosiasi: gabungkan file top-10 (final) dengan pool yang lebih
# besar (report_worthy_rules.csv / fraud_focused_rules.csv) kalau tersedia,
# supaya fitur "10 utama + selebihnya tetap bisa diakses" punya isi yang nyata.
# ---------------------------------------------------------------------------
RULE_FILE_CANDIDATES_TOP10 = ["top_10_final_rules.csv", "top_rules_business.csv"]
RULE_FILE_CANDIDATES_POOL = ["report_worthy_rules.csv", "fraud_focused_rules.csv", "meaningful_rules.csv"]


def _rule_group_of(antecedents: str, consequents: str) -> str:
    both = f"{antecedents} {consequents}"
    if "isFraud_yes" in consequents:
        return cfg.RULE_GROUP_FRAUD
    if "cluster_kmeans" in both:
        return cfg.RULE_GROUP_SEGMENT
    if "hdbscan_outlier" in both:
        return cfg.RULE_GROUP_OUTLIER
    return cfg.RULE_GROUP_GENERAL


def _takeaway_and_recommendation(row) -> tuple[str, str]:
    ante, cons = row["antecedents_str"], row["consequents_str"]
    both = f"{ante} {cons}"
    lift, conf = row["lift"], row["confidence"]
    if "isFraud_yes" in cons:
        takeaway = ("Pola langka, tapi begitu muncul sangat terkonsentrasi ke fraud terkonfirmasi."
                    if conf >= 0.5 else "Pola ini menaikkan konsentrasi fraud namun masih perlu konfirmasi lebih lanjut.")
        rekomendasi = ("Jadikan kombinasi ini sebagai aturan pemblokiran/review otomatis pada sistem monitoring "
                       "transaksi real-time, bukan sekadar laporan pasif. Prioritaskan tim investigasi fraud untuk "
                       "transaksi yang cocok pola ini sebelum dana keluar dari sistem.")
    elif "cluster_kmeans" in both:
        takeaway = "Pola ini menjelaskan perilaku yang secara alami melekat pada satu segmen nasabah/transaksi."
        rekomendasi = ("Pakai pola ini untuk menyusun kebijakan khusus per segmen (mis. limit transaksi atau ambang "
                       "verifikasi berbeda), bukan kebijakan seragam untuk semua nasabah.")
    elif "hdbscan_outlier" in both:
        takeaway = "Pola ini mengarah ke transaksi yang berada di luar struktur normal populasi."
        rekomendasi = "Gunakan sebagai sinyal tambahan (bukan tunggal) untuk memicu peninjauan manual."
    elif lift >= 10:
        takeaway = "Pola perilaku yang kuat, berguna untuk menjelaskan bagaimana atribut transaksi bergerak bersama."
        rekomendasi = "Manfaatkan sebagai fitur tambahan pada aturan bisnis atau model deteksi berikutnya."
    else:
        takeaway = "Pola bisnis umum yang membantu menjelaskan perilaku transaksi yang sering terjadi."
        rekomendasi = "Cocok sebagai konteks/latar belakang, bukan prioritas tindakan investigasi."
    return takeaway, rekomendasi


def build_rule_pool(phase3_dir: Optional[Path], top10_fallback: Optional[pd.DataFrame] = None,
                     logger=None) -> pd.DataFrame:
    """Muat & gabungkan pool aturan asosiasi. `top10_fallback` dipakai bila
    tidak ada berkas top-10 yang ditemukan (mis. hanya cache lama yang ada)."""
    def _log(msg):
        if logger:
            logger.info(msg)

    top10 = None
    pool_frames = []
    if phase3_dir and Path(phase3_dir).exists():
        for name in RULE_FILE_CANDIDATES_TOP10:
            p = Path(phase3_dir) / name
            if p.exists():
                top10 = pd.read_csv(p)
                _log(f"  pola 10 utama dimuat dari {p.name}")
                break
        for name in RULE_FILE_CANDIDATES_POOL:
            p = Path(phase3_dir) / name
            if p.exists():
                pool_frames.append(pd.read_csv(p))
                _log(f"  pool pola tambahan dimuat dari {p.name} ({len(pool_frames[-1])} baris)")

    if top10 is None:
        if top10_fallback is None:
            raise FileNotFoundError(
                "Tidak menemukan berkas pola 10 utama (top_10_final_rules.csv / top_rules_business.csv) "
                "maupun fallback. Sertakan salah satunya."
            )
        top10 = top10_fallback
        _log("  pola 10 utama dimuat dari cache lama (top_rules_business.parquet)")

    top10 = top10.copy()
    top10["is_real"] = True
    if pool_frames:
        pool = pd.concat(pool_frames, ignore_index=True)
        pool["is_real"] = False
        key_top10 = set(zip(top10["antecedents_str"], top10["consequents_str"]))
        pool = pool[~pool.apply(lambda r: (r["antecedents_str"], r["consequents_str"]) in key_top10, axis=1)]
        all_rules = pd.concat([top10, pool], ignore_index=True)
    else:
        _log("  tidak ada pool pola tambahan (report_worthy_rules.csv dkk) - hanya 10 pola utama tersedia")
        all_rules = top10

    all_rules["rule_group"] = all_rules.apply(lambda r: _rule_group_of(r["antecedents_str"], r["consequents_str"]), axis=1)
    all_rules["when_text"] = all_rules["antecedents_str"].apply(cfg.humanize_item_list)
    all_rules["then_text"] = all_rules["consequents_str"].apply(cfg.humanize_item_list)
    all_rules["coverage_fmt"] = all_rules["support"].apply(lambda x: cfg.format_pct(x, 3))
    all_rules["confidence_fmt"] = all_rules["confidence"].apply(lambda x: cfg.format_pct(x, 1))
    all_rules["lift_fmt"] = all_rules["lift"].apply(cfg.format_multiplier)
    tk = all_rules.apply(_takeaway_and_recommendation, axis=1, result_type="expand")
    all_rules["takeaway"], all_rules["recommendation"] = tk[0], tk[1]
    all_rules = all_rules.sort_values(["is_real", "lift"], ascending=[False, False]).reset_index(drop=True)
    all_rules["is_top10"] = all_rules["is_real"]
    all_rules["rule_id"] = [f"POLA{i+1:04d}" for i in range(len(all_rules))]
    all_rules["penting"] = np.where(all_rules["is_top10"], "Insight utama", "Insight tambahan")
    return all_rules
