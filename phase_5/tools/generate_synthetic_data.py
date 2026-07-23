"""
generate_synthetic_data.py
===========================
INI BUKAN BAGIAN DARI DASHBOARD PRODUKSI. Skrip ini hanya dipakai untuk membuat
dataset uji (~6.3 juta baris) yang meniru statistik AGREGAT asli dari cache
Phase 5 kelompok (cluster_summary, risk_summary, anomaly_type_summary,
fraud_by_score, method_overlap, dst - lihat NOTES.md) karena file mentah
Phase 1-4 (6.3 juta baris) tidak ikut ter-upload, hanya ringkasannya.

Tujuannya SEMATA untuk:
1. Menguji pipeline Prefect + backend DuckDB/Elasticsearch end-to-end dengan
   volume data yang sebenarnya (6.3 juta), termasuk mengukur performa nyata.
2. Menjalankan ulang apriori (mlxtend) secara REAL di atas data ini supaya fitur
   "10 pola utama + sisanya tetap bisa diakses" bisa diuji dengan pool pola yang
   benar-benar dihitung (bukan dikarang manual).

Begitu kelompok menjalankan pipeline asli (pipeline/flow.py) terhadap output
Phase 1-4 mereka sendiri, skrip ini tidak lagi relevan/dipakai.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

RNG_SEED = 42
N_ROWS = 6_362_604  # sama persis dgn total baris asli (lihat NOTES.md)

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw_synthetic"
OUT_DIR.mkdir(parents=True, exist_ok=True)

rng = np.random.default_rng(RNG_SEED)

# ---------------------------------------------------------------------------
# 1) SEGMEN (proporsi & karakteristik PERSIS dari cluster_summary.parquet asli)
# ---------------------------------------------------------------------------
SEGMENTS = [
    dict(id=0, n=1_648, fraud_rate=0.0, avg_risk=4.656553, high_risk_rate=0.791262,
         dominant_types={"TRANSFER": 0.85, "CASH_OUT": 0.15}),
    dict(id=1, n=5_880_042, fraud_rate=0.0012015, avg_risk=0.083410, high_risk_rate=0.009987,
         dominant_types={"CASH_OUT": 0.35, "PAYMENT": 0.34, "CASH_IN": 0.22, "TRANSFER": 0.084, "DEBIT": 0.006}),
    dict(id=2, n=391_249, fraud_rate=0.0026377, avg_risk=0.039670, high_risk_rate=0.007131,
         dominant_types={"CASH_IN": 0.93, "TRANSFER": 0.07}),
    dict(id=3, n=89_665, fraud_rate=0.0011153, avg_risk=0.049629, high_risk_rate=0.010004,
         dominant_types={"CASH_IN": 0.95, "TRANSFER": 0.05}),
]
assert sum(s["n"] for s in SEGMENTS) == N_ROWS

# ---------------------------------------------------------------------------
# 2) WILAYAH SINTETIS (dimensi spasial ilustratif - dataset asli TIDAK punya
#    atribut geografis, lihat NOTES.md / README). Dibuat deterministik & sedikit
#    berkorelasi dgn risiko supaya filter spasial terasa nyata saat didemokan,
#    tapi ditandai jelas di UI sbg simulasi.
# ---------------------------------------------------------------------------
WILAYAH_LIST = [
    "Jabodetabek", "Jawa Barat", "Jawa Tengah & DIY", "Jawa Timur",
    "Sumatera", "Kalimantan", "Sulawesi & Maluku", "Bali & Nusa Tenggara",
]
WILAYAH_BASE_W = np.array([0.22, 0.15, 0.12, 0.14, 0.18, 0.08, 0.07, 0.04])
# sedikit pemiringan per segmen supaya pola spasial ada saat difilter
WILAYAH_TILT = {
    0: np.array([1.6, 1.1, 0.8, 0.9, 1.3, 0.6, 0.5, 0.4]),   # transfer besar -> condong kota besar
    1: np.ones(8),
    2: np.array([0.9, 1.0, 1.1, 1.0, 1.2, 1.0, 0.9, 0.8]),
    3: np.array([0.9, 1.0, 1.1, 1.0, 1.2, 1.0, 0.9, 0.8]),
}


def sample_wilayah(seg_id: int, n: int) -> np.ndarray:
    w = WILAYAH_BASE_W * WILAYAH_TILT[seg_id]
    w = w / w.sum()
    return rng.choice(WILAYAH_LIST, size=n, p=w)


# ---------------------------------------------------------------------------
# 3) RISK SCORE per segmen (kalibrasi manual supaya avg & high_risk_rate per
#    segmen MENDEKATI angka asli, sekaligus reproduksi temuan "score=2 (Sedang)
#    fraud rate-nya lebih tinggi dari score=6 (Kritis)")
# ---------------------------------------------------------------------------
# distribusi score 0-6 per segmen, dikalibrasi lewat trial supaya rata2 & high-risk rate cocok
SCORE_DIST = {
    0: np.array([0.05, 0.05, 0.11, 0.05, 0.08, 0.05, 0.61]),   # avg~4.65, P(score>=3)~79%
    1: np.array([0.9542, 0.0350, 0.00030, 0.00320, 0.00650, 0.0000145, 0.00079]),
    2: np.array([0.9700, 0.0100, 0.00013, 0.01260, 0.00600, 0.0000, 0.00127]),
    3: np.array([0.9714, 0.0120, 0.00013, 0.00960, 0.00560, 0.0000, 0.00127]),
}
for k in SCORE_DIST:
    SCORE_DIST[k] = SCORE_DIST[k] / SCORE_DIST[k].sum()

# fraud rate KONDISIONAL per risk_score, dari fraud_by_score.parquet ASLI
FRAUD_RATE_BY_SCORE = {
    0: 0.000721, 1: 0.006203, 2: 0.443161, 3: 0.024223,
    4: 0.008904, 5: 0.0, 6: 0.207090,
}

RISK_LEVEL_ID = {0: "Normal", 1: "Rendah", 2: "Sedang", 3: "Tinggi", 4: "Tinggi", 5: "Kritis", 6: "Kritis"}

# Dekomposisi score -> kombinasi flag (bobot IQR=1, ZScore=1, IsoForest=2, HDBSCAN=2),
# proporsi tiap kombinasi mengikuti besar relatif method_overlap.parquet ASLI.
SCORE_FLAG_COMBOS = {
    0: [((False, False, False, False), 1.0)],
    1: [((True, False, False, False), 0.90), ((False, True, False, False), 0.10)],
    2: [((True, True, False, False), 0.55), ((False, False, True, False), 0.30), ((False, False, False, True), 0.15)],
    3: [((True, False, True, False), 0.5), ((True, False, False, True), 0.2), ((False, True, True, False), 0.3)],
    4: [((False, False, True, True), 0.85), ((True, True, True, False), 0.15)],
    5: [((True, False, True, True), 0.6), ((False, True, True, True), 0.4)],
    6: [((True, True, True, True), 1.0)],
}


def sample_flags_for_score(score: int, n: int) -> np.ndarray:
    combos, weights = zip(*SCORE_FLAG_COMBOS[score])
    weights = np.array(weights) / np.sum(weights)
    idx = rng.choice(len(combos), size=n, p=weights)
    arr = np.array(combos)[idx]  # (n, 4) bool
    return arr


# ---------------------------------------------------------------------------
# 4) Kategori anomali & investigasi - MENIRU PERSIS logika phase_4.py asli
#    (lihat NOTES.md) dari kombinasi flag, bukan dikarang independen.
# ---------------------------------------------------------------------------

def classify_anomaly(flag_iqr, flag_z, flag_iso, flag_hdb, flag_balance):
    n_flags = flag_iqr.astype(int) + flag_z.astype(int) + flag_iso.astype(int) + flag_hdb.astype(int)
    anomaly_type = np.full(len(flag_iqr), "Tidak Ada Anomali Statistik", dtype=object)
    anomaly_type[flag_balance & (n_flags == 0)] = "Ketidaksesuaian Saldo"
    anomaly_type[(flag_iqr | flag_z) & (n_flags == 1) & (~flag_balance)] = "Nominal Transaksi Ekstrem"
    anomaly_type[flag_iso & flag_hdb & (n_flags == 2)] = "Perilaku & Struktur Klaster Menyimpang"
    anomaly_type[flag_hdb & (n_flags == 1)] = "Klaster Menyimpang (Outlier)"
    anomaly_type[n_flags >= 3] = "Banyak Indikator Sekaligus"
    return anomaly_type


def classify_investigation(risk_score, flag_hdb):
    high_risk = (risk_score >= 3) | flag_hdb
    cat = np.full(len(risk_score), "Normal / Perlu Perhatian Rendah", dtype=object)
    cat[(risk_score == 1) | (risk_score == 2)] = "Kemungkinan Masalah Kualitas Data"
    cat[high_risk & (risk_score < 5)] = "Berpotensi Perlu Dipantau"
    cat[high_risk & (risk_score >= 5)] = "Berpotensi Fraud"
    return cat


def main():
    print(f"Generating {N_ROWS:,} synthetic rows (seed={RNG_SEED}) ...")
    chunks = []
    tx_offset = 0
    for seg in SEGMENTS:
        n = seg["n"]
        seg_id = seg["id"]

        # --- tipe transaksi sesuai profil segmen ---
        types, probs = zip(*seg["dominant_types"].items())
        probs = np.array(probs) / np.sum(probs)
        tx_type = rng.choice(types, size=n, p=probs)

        # --- risk score sesuai kalibrasi segmen ---
        score = rng.choice(np.arange(7), size=n, p=SCORE_DIST[seg_id])

        # --- flags turunan dari score ---
        flags = np.zeros((n, 4), dtype=bool)
        for s in range(7):
            mask = score == s
            cnt = mask.sum()
            if cnt:
                flags[mask] = sample_flags_for_score(s, cnt)
        flag_iqr, flag_z, flag_iso, flag_hdb = flags[:, 0], flags[:, 1], flags[:, 2], flags[:, 3]

        # --- balance mismatch flag (independen, dipakai utk anomaly_type Balance Mismatch) ---
        base_balance_rate = 0.226 if seg_id == 1 else (0.05 if seg_id == 0 else 0.10)
        flag_balance = rng.random(n) < base_balance_rate
        flag_balance = flag_balance & (score <= 1)  # jangan tabrakan dgn kombinasi flag tinggi

        # --- fraud, kondisional pada risk_score (mereproduksi temuan Sedang>Kritis) ---
        p_fraud = np.vectorize(FRAUD_RATE_BY_SCORE.get)(score).astype(float)
        is_fraud = rng.random(n) < p_fraud
        # segmen 0 secara historis TIDAK PERNAH berlabel fraud (lihat NOTES.md)
        if seg_id == 0:
            is_fraud[:] = False

        # --- nominal transaksi (dalam satuan mata uang dataset, skala mendekati PaySim asli) ---
        if seg_id == 0:
            amount = rng.lognormal(mean=15.5, sigma=0.9, size=n)          # transfer sangat besar
            old_orig = rng.lognormal(mean=13.5, sigma=1.3, size=n)
        elif seg_id in (2, 3):
            amount = rng.lognormal(mean=10.5, sigma=1.4, size=n)
            old_orig = rng.lognormal(mean=15.0, sigma=1.0, size=n)        # saldo awal sangat tinggi
        else:
            amount = rng.lognormal(mean=9.6, sigma=1.6, size=n)
            old_orig = rng.lognormal(mean=9.0, sigma=1.8, size=n)
        # transaksi berisiko tinggi cenderung py lebih ekstrem nominalnya
        boost = 1 + (score / 6.0) * rng.uniform(0.5, 3.0, size=n)
        amount = amount * boost
        old_dest = rng.lognormal(mean=10.0, sigma=2.0, size=n)

        orig_error = (rng.normal(0, 1, size=n) * (500 + 4000 * (score / 6.0))) * rng.choice([1, -1], size=n)
        dest_error = (rng.normal(0, 1, size=n) * (500 + 4000 * (score / 6.0))) * rng.choice([1, -1], size=n)
        orig_drained = (rng.random(n) < (0.15 + 0.6 * (score >= 5))) & (tx_type != "CASH_IN")
        is_dest_merchant = rng.random(n) < (0.35 if seg_id == 1 else 0.05)

        step = rng.integers(1, 744, size=n)
        wilayah = sample_wilayah(seg_id, n)

        df = pd.DataFrame({
            "transaction_id": [f"TX{v:08d}" for v in range(tx_offset, tx_offset + n)],
            "step": step.astype(np.int16),
            "transaction_type": tx_type,
            "amount": amount.astype(np.float64).round(2),
            "oldbalanceOrg": old_orig.astype(np.float64).round(2),
            "oldbalanceDest": old_dest.astype(np.float64).round(2),
            "origError": orig_error.astype(np.float64).round(2),
            "destError": dest_error.astype(np.float64).round(2),
            "origDrainedToZero": orig_drained,
            "isDestMerchant": is_dest_merchant,
            "cluster_kmeans": np.int8(seg_id),
            "flag_IQR": flag_iqr,
            "flag_ZScore": flag_z,
            "flag_IsoForest": flag_iso,
            "flag_HDBSCAN": flag_hdb,
            "flag_BalanceMismatch": flag_balance,
            "risk_score": score.astype(np.int8),
            "isFraud": is_fraud,
            "wilayah": wilayah,
        })
        chunks.append(df)
        tx_offset += n
        print(f"  segmen {seg_id}: {n:,} baris selesai")

    full = pd.concat(chunks, ignore_index=True)
    del chunks

    # shuffle supaya urutan baris tidak berdasar-segmen (lebih realistis)
    full = full.sample(frac=1.0, random_state=RNG_SEED).reset_index(drop=True)

    full["risk_level"] = full["risk_score"].map(RISK_LEVEL_ID)
    full["anomaly_type"] = classify_anomaly(
        full["flag_IQR"].values, full["flag_ZScore"].values,
        full["flag_IsoForest"].values, full["flag_HDBSCAN"].values,
        full["flag_BalanceMismatch"].values,
    )
    full["investigation_category"] = classify_investigation(full["risk_score"].values, full["flag_HDBSCAN"].values)
    full["high_risk"] = (full["risk_score"] >= 3) | full["flag_HDBSCAN"]

    print("Menyusun alasan anomali (vectorized, lookup 32 kombinasi) ...")
    FLAG_LABELS = [
        "Nominal tinggi tak wajar (IQR)",
        "Nominal ekstrem (Z-Score)",
        "Kombinasi perilaku tak wajar (Isolation Forest)",
        "Menyimpang dari struktur klaster (BIRCH+HDBSCAN)",
        "Ketidaksesuaian saldo asal/tujuan",
    ]
    # bit-pack 5 flag jadi kode 0-31, siapkan lookup string utk semua 32 kombinasi sekali saja
    code = (
        full["flag_IQR"].values.astype(np.int8) * 1
        + full["flag_ZScore"].values.astype(np.int8) * 2
        + full["flag_IsoForest"].values.astype(np.int8) * 4
        + full["flag_HDBSCAN"].values.astype(np.int8) * 8
        + full["flag_BalanceMismatch"].values.astype(np.int8) * 16
    )
    lookup = np.empty(32, dtype=object)
    for c in range(32):
        bits = [(c >> b) & 1 for b in range(5)]
        parts = [label for bit, label in zip(bits, FLAG_LABELS) if bit]
        lookup[c] = "; ".join(parts) if parts else "Tidak ada indikator yang terpicu"
    full["anomaly_reason"] = lookup[code]

    out_path = OUT_DIR / "synthetic_transactions.parquet"
    full.to_parquet(out_path, index=False)
    print(f"Tersimpan: {out_path}  shape={full.shape}")

    sample_path = OUT_DIR / "sample_for_rule_mining.parquet"
    full.sample(n=min(150_000, len(full)), random_state=7).to_parquet(sample_path, index=False)
    print(f"Tersimpan (sampel utk rule mining): {sample_path}")

    # ---- ringkasan cepat utk verifikasi terhadap NOTES.md ----
    print("\n--- verifikasi cepat ---")
    print("total baris:", len(full))
    print("fraud rate keseluruhan:", full["isFraud"].mean())
    print(full.groupby("cluster_kmeans").agg(
        n=("isFraud", "size"), fraud_rate=("isFraud", "mean"), avg_risk=("risk_score", "mean"),
        high_risk_rate=("high_risk", "mean"),
    ))
    print(full["risk_level"].value_counts(normalize=True))
    print(full.groupby("risk_score")["isFraud"].mean())


if __name__ == "__main__":
    main()
