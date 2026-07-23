"""
tools/build_rules_and_db.py  (skrip pengembangan/uji, BUKAN bagian pipeline resmi)
====================================================================================
1. Menjalankan ULANG apriori (mlxtend) memakai metodologi & parameter yang PERSIS
   sama dengan Phase 3 asli (lihat NOTES.md) di atas sampel data sintetis, supaya
   ada pool pola yang lebih besar dari 10 untuk menguji fitur "10 pola utama +
   selebihnya tetap bisa diakses & dicari".
2. 10 pola TERATAS tetap memakai angka ASLI dari top_rules_business.parquet
   (tidak diganti data sintetis) - dikunci sebagai is_top10=True.
3. Menulis semuanya ke satu berkas fance_dashboard.duckdb yang dipakai app.py.

Pipeline resmi (pipeline/flow.py) melakukan hal yang serupa terhadap data ASLI
kelompok saat dijalankan di komputer mereka sendiri.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import duckdb
import numpy as np
import pandas as pd
from mlxtend.frequent_patterns import apriori, association_rules

import config as cfg

BUILD_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BUILD_DIR / "data"
SYN_PATH = DATA_DIR / "raw_synthetic" / "synthetic_transactions.parquet"
DUCKDB_PATH = DATA_DIR / "fance_dashboard.duckdb"

MIN_SUPPORT = 0.005
MIN_CONFIDENCE = 0.50
MIN_LIFT = 1.20
MAX_LEN = 3
FRAUD_MIN_SUPPORT = 0.0008

# 10 pola ASLI (dari top_rules_business.parquet, lihat NOTES.md) - dikunci apa adanya
REAL_TOP10 = [
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
]


def build_basket(df: pd.DataFrame) -> pd.DataFrame:
    """Persis meniru build_basket() Phase 3 asli (lihat NOTES.md)."""
    basket = pd.DataFrame(index=df.index)
    for t in ["CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"]:
        basket[f"type_{t}"] = df["transaction_type"] == t
    basket["isFraud_yes"] = df["isFraud"].astype(bool)
    basket["isFraud_no"] = ~df["isFraud"].astype(bool)
    basket["dest_merchant_yes"] = df["isDestMerchant"].astype(bool)
    basket["dest_merchant_no"] = ~df["isDestMerchant"].astype(bool)
    basket["orig_drained_yes"] = df["origDrainedToZero"].astype(bool)
    basket["orig_drained_no"] = ~df["origDrainedToZero"].astype(bool)
    for c in range(4):
        basket[f"cluster_kmeans_{c}"] = df["cluster_kmeans"] == c
    basket["hdbscan_outlier"] = df["flag_HDBSCAN"].astype(bool)
    basket["hdbscan_normal"] = ~df["flag_HDBSCAN"].astype(bool)
    for col in ["amount", "oldbalanceOrg", "oldbalanceDest", "origError", "destError"]:
        try:
            bins = pd.qcut(df[col], q=5, labels=["very_low", "low", "medium", "high", "very_high"], duplicates="drop")
        except ValueError:
            bins = pd.qcut(df[col].rank(method="first"), q=5, labels=["very_low", "low", "medium", "high", "very_high"])
        for lvl in ["very_low", "low", "medium", "high", "very_high"]:
            basket[f"{col}_{lvl}"] = (bins == lvl).fillna(False)
    return basket


def mine_rules(df_sample: pd.DataFrame) -> pd.DataFrame:
    basket = build_basket(df_sample)
    print(f"  basket shape: {basket.shape}")

    freq = apriori(basket, min_support=MIN_SUPPORT, use_colnames=True, max_len=MAX_LEN, low_memory=True)
    rules = association_rules(freq, metric="confidence", min_threshold=MIN_CONFIDENCE)
    rules = rules[rules["lift"] >= MIN_LIFT].copy()
    print(f"  aturan umum (support>={MIN_SUPPORT}): {len(rules)}")

    fraud_mask = basket["isFraud_yes"]
    if fraud_mask.sum() >= 5:
        freq_fraud = apriori(basket, min_support=FRAUD_MIN_SUPPORT, use_colnames=True, max_len=MAX_LEN, low_memory=True)
        rules_fraud = association_rules(freq_fraud, metric="lift", min_threshold=MIN_LIFT)
        rules_fraud = rules_fraud[
            rules_fraud["consequents"].apply(lambda s: "isFraud_yes" in set(s))
        ].copy()
        print(f"  aturan fraud (support>={FRAUD_MIN_SUPPORT}): {len(rules_fraud)}")
        rules = pd.concat([rules, rules_fraud], ignore_index=True)

    rules["antecedents_str"] = rules["antecedents"].apply(lambda s: ", ".join(sorted(s)))
    rules["consequents_str"] = rules["consequents"].apply(lambda s: ", ".join(sorted(s)))
    rules = rules.drop_duplicates(subset=["antecedents_str", "consequents_str"])
    rules = rules.sort_values("lift", ascending=False).reset_index(drop=True)
    return rules[["antecedents_str", "consequents_str", "support", "confidence", "lift"]]


def rule_group_of(antecedents: str, consequents: str) -> str:
    both = f"{antecedents} {consequents}"
    if "isFraud_yes" in consequents:
        return cfg.RULE_GROUP_FRAUD
    if "cluster_kmeans" in both:
        return cfg.RULE_GROUP_SEGMENT
    if "hdbscan_outlier" in both:
        return cfg.RULE_GROUP_OUTLIER
    return cfg.RULE_GROUP_GENERAL


def business_takeaway_and_recommendation(row) -> tuple[str, str]:
    """(takeaway singkat, rekomendasi tindakan lebih detail) - utk pertanyaan dosen
    'pattern recommendation tambahin yang detail'."""
    ante, cons = row["antecedents_str"], row["consequents_str"]
    both = f"{ante} {cons}"
    lift = row["lift"]
    conf = row["confidence"]
    if "isFraud_yes" in cons:
        takeaway = (
            "Pola langka, tapi begitu muncul sangat terkonsentrasi ke fraud terkonfirmasi."
            if conf >= 0.5 else
            "Pola ini menaikkan konsentrasi fraud namun masih perlu konfirmasi sebelum ditindaklanjuti."
        )
        rekomendasi = (
            "Jadikan kombinasi ini sebagai ATURAN PEMBLOKIRAN/REVIEW OTOMATIS pada sistem "
            "monitoring transaksi real-time, bukan sekadar laporan pasif. Prioritaskan tim "
            "investigasi fraud untuk transaksi yang cocok pola ini sebelum dana keluar dari sistem."
        )
    elif "cluster_kmeans" in both:
        takeaway = "Pola ini menjelaskan perilaku yang secara alami melekat pada satu segmen nasabah/transaksi."
        rekomendasi = (
            "Pakai pola ini untuk menyusun kebijakan khusus per segmen (mis. limit transaksi atau "
            "ambang verifikasi berbeda), bukan kebijakan seragam untuk semua nasabah."
        )
    elif "hdbscan_outlier" in both:
        takeaway = "Pola ini mengarah ke transaksi yang berada di luar struktur normal populasi."
        rekomendasi = (
            "Gunakan sebagai sinyal tambahan (bukan tunggal) untuk memicu peninjauan manual, "
            "terutama saat muncul bersamaan dengan indikator lain."
        )
    elif lift >= 10:
        takeaway = "Pola perilaku yang kuat, berguna untuk menjelaskan bagaimana atribut transaksi bergerak bersama."
        rekomendasi = "Manfaatkan sebagai fitur tambahan pada aturan bisnis atau model deteksi berikutnya."
    else:
        takeaway = "Pola bisnis umum yang membantu menjelaskan perilaku transaksi yang sering terjadi."
        rekomendasi = "Cocok sebagai konteks/latar belakang, bukan prioritas tindakan investigasi."
    return takeaway, rekomendasi


def main():
    print("1) Memuat sampel data sintetis untuk penambangan pola tambahan ...")
    df_full = pd.read_parquet(SYN_PATH)
    sample = df_full.sample(n=min(150_000, len(df_full)), random_state=7)
    print(f"   sampel: {len(sample):,} baris (dari total {len(df_full):,})")

    print("2) Menjalankan apriori (metodologi sama dgn Phase 3 asli) ...")
    mined = mine_rules(sample)
    print(f"   total pola hasil tambang: {len(mined)}")

    real10 = pd.DataFrame(REAL_TOP10)
    real10["is_real"] = True
    mined["is_real"] = False
    # buang hasil tambang yg kebetulan duplikat dgn 10 asli
    key_real = set(zip(real10["antecedents_str"], real10["consequents_str"]))
    mined = mined[~mined.apply(lambda r: (r["antecedents_str"], r["consequents_str"]) in key_real, axis=1)]

    all_rules = pd.concat([real10, mined], ignore_index=True)
    all_rules["rule_group"] = all_rules.apply(lambda r: rule_group_of(r["antecedents_str"], r["consequents_str"]), axis=1)
    all_rules["when_text"] = all_rules["antecedents_str"].apply(cfg.humanize_item_list)
    all_rules["then_text"] = all_rules["consequents_str"].apply(cfg.humanize_item_list)
    all_rules["coverage_fmt"] = all_rules["support"].apply(lambda x: cfg.format_pct(x, 3))
    all_rules["confidence_fmt"] = all_rules["confidence"].apply(lambda x: cfg.format_pct(x, 1))
    all_rules["lift_fmt"] = all_rules["lift"].apply(cfg.format_multiplier)
    takeaways = all_rules.apply(business_takeaway_and_recommendation, axis=1, result_type="expand")
    all_rules["takeaway"], all_rules["recommendation"] = takeaways[0], takeaways[1]

    # is_top10: 10 baris dgn lift tertinggi DI ANTARA yang is_real (menjaga urutan asli top_rules_business)
    all_rules = all_rules.sort_values(["is_real", "lift"], ascending=[False, False]).reset_index(drop=True)
    all_rules["is_top10"] = False
    all_rules.loc[all_rules["is_real"], "is_top10"] = True
    all_rules["rule_id"] = [f"POLA{i+1:04d}" for i in range(len(all_rules))]
    all_rules["penting"] = np.where(all_rules["is_top10"], "Insight utama", "Insight tambahan")

    print(f"   total pola akhir (asli+tambang): {len(all_rules)}  (top10 asli terkunci: {all_rules['is_top10'].sum()})")

    print("3) Menulis DuckDB ...")
    DUCKDB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DUCKDB_PATH.exists():
        DUCKDB_PATH.unlink()
    con = duckdb.connect(str(DUCKDB_PATH))

    con.execute("CREATE TABLE transaksi AS SELECT * FROM read_parquet(?)", [str(SYN_PATH)])
    con.execute("ALTER TABLE transaksi ALTER COLUMN cluster_kmeans SET DATA TYPE TINYINT")
    for col in ["wilayah", "transaction_type", "risk_level", "anomaly_type", "investigation_category"]:
        con.execute(f"CREATE INDEX idx_{col} ON transaksi ({col})")
    con.execute("CREATE INDEX idx_risk_score ON transaksi (risk_score)")
    con.execute("CREATE INDEX idx_amount ON transaksi (amount)")
    con.execute("CREATE INDEX idx_txid ON transaksi (transaction_id)")

    pola_cols = [
        "rule_id", "antecedents_str", "consequents_str", "support", "confidence", "lift",
        "when_text", "then_text", "coverage_fmt", "confidence_fmt", "lift_fmt",
        "takeaway", "recommendation", "rule_group", "is_top10", "penting",
    ]
    con.register("pola_df", all_rules[pola_cols])
    con.execute("CREATE TABLE pola AS SELECT * FROM pola_df")

    n_transaksi = con.execute("SELECT COUNT(*) FROM transaksi").fetchone()[0]
    n_pola = con.execute("SELECT COUNT(*) FROM pola").fetchone()[0]
    print(f"   transaksi: {n_transaksi:,} baris | pola: {n_pola} baris")

    print("4) Membangun cube pra-agregasi (kunci performa <100ms) ...")
    # Semua kolom yang bisa difilter dikelompokkan sekali di sini. risk_score/
    # risk_level/anomaly_type/investigation_category adalah fungsi deterministik
    # dari kombinasi flag, jadi cukup dibawa apa adanya (bukan dihitung ulang).
    con.execute("""
        CREATE TABLE cube AS
        SELECT
            wilayah, transaction_type, cluster_kmeans, isFraud,
            flag_IQR, flag_ZScore, flag_IsoForest, flag_HDBSCAN, flag_BalanceMismatch,
            risk_score, risk_level, anomaly_type, investigation_category,
            (risk_score >= 3 OR flag_HDBSCAN) AS high_risk,
            COUNT(*) AS n
        FROM transaksi
        GROUP BY 1,2,3,4,5,6,7,8,9,10,11,12,13,14
    """)
    n_cube = con.execute("SELECT COUNT(*) FROM cube").fetchone()[0]
    check = con.execute("SELECT SUM(n) FROM cube").fetchone()[0]
    print(f"   cube: {n_cube:,} baris ringkas (representasi {check:,} baris transaksi)")
    assert check == n_transaksi, "cube tidak konsisten dengan tabel transaksi!"
    for col in ["wilayah", "transaction_type", "cluster_kmeans", "risk_level"]:
        con.execute(f"CREATE INDEX idx_cube_{col} ON cube ({col})")

    con.close()
    print(f"Selesai -> {DUCKDB_PATH}")


if __name__ == "__main__":
    main()
