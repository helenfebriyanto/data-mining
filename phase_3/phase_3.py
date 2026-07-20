import pandas as pd
import numpy as np
import os
import matplotlib.pyplot as plt
import networkx as nx
from mlxtend.frequent_patterns import apriori, association_rules
from prefect import flow, task, get_run_logger

def _format_log_value(value):
    if isinstance(value, pd.DataFrame):
        return "\n" + value.to_string()
    if isinstance(value, pd.Series):
        return "\n" + value.to_string()
    return str(value)


def log_prefect(value):
    try:
        logger = get_run_logger()
        logger.info(_format_log_value(value))
    except Exception:
        print(_format_log_value(value))


def display(value):
    log_prefect(value)


def discretize_numeric_series(series, col_name, q=5):
    labels_map = {
        1: ["all"],
        2: ["low", "high"],
        3: ["low", "medium", "high"],
        4: ["very_low", "low", "high", "very_high"],
        5: ["very_low", "low", "medium", "high", "very_high"],
    }

    s = pd.to_numeric(series, errors="coerce")

    if s.nunique(dropna=True) <= 1:
        return None

    try:
        codes, bins = pd.qcut(
            s,
            q=q,
            labels=False,
            retbins=True,
            duplicates="drop"
        )

        n_bins = len(bins) - 1

        if n_bins <= 0:
            return None

        labels = labels_map.get(n_bins, [f"bin_{i}" for i in range(n_bins)])
        mapped = codes.map(lambda x: f"{col_name}_{labels[int(x)]}" if pd.notna(x) else np.nan)

        categories = [f"{col_name}_{label}" for label in labels]
        return pd.Categorical(mapped, categories=categories)

    except Exception as e:
        log_prefect(f"Failed to discretize {col_name}: {e}")
        return None


def build_basket(df):
    basket_parts = []

    # Transaction type dari hasil one-hot Phase 1
    type_cols = [col for col in df.columns if col.startswith("type_")]
    if type_cols:
        basket_parts.append(df[type_cols].astype(bool))

    # Fraud label
    if "isFraud" in df.columns:
        fraud_items = pd.DataFrame(index=df.index)
        fraud_items["isFraud_yes"] = df["isFraud"].astype(int) == 1
        fraud_items["isFraud_no"] = df["isFraud"].astype(int) == 0
        basket_parts.append(fraud_items)

    # Destination merchant
    if "isDestMerchant" in df.columns:
        merchant_items = pd.DataFrame(index=df.index)
        merchant_items["dest_merchant_yes"] = df["isDestMerchant"].astype(int) == 1
        merchant_items["dest_merchant_no"] = df["isDestMerchant"].astype(int) == 0
        basket_parts.append(merchant_items)

    # Origin account drained to zero
    if "origDrainedToZero" in df.columns:
        drained_items = pd.DataFrame(index=df.index)
        drained_items["orig_drained_yes"] = df["origDrainedToZero"].astype(int) == 1
        drained_items["orig_drained_no"] = df["origDrainedToZero"].astype(int) == 0
        basket_parts.append(drained_items)

    # KMeans cluster dari Phase 2
    if "cluster_kmeans" in df.columns:
        cluster_items = pd.get_dummies(
            df["cluster_kmeans"].astype(str),
            prefix="cluster_kmeans"
        ).astype(bool)
        basket_parts.append(cluster_items)

    # HDBSCAN outlier dari Phase 2
    # Pakai cluster_birch_hdbscan (hasil BIRCH+HDBSCAN), BUKAN cluster_hdbscan (HDBSCAN
    # langsung + approximate_predict di Phase 2 bagian 5). Versi langsung menandai ~71%
    # baris sebagai outlier sehingga item "hdbscan_outlier" nyaris tidak informatif untuk
    # association rule mining. Nama item di basket tetap "hdbscan_outlier"/"hdbscan_normal"
    # supaya semua filter di bawah (generate_report_rules, select_top_10_rules, dst) tidak
    # perlu ikut diubah.
    if "is_birch_hdbscan_outlier" in df.columns:
        hdbscan_items = pd.DataFrame(index=df.index)
        hdbscan_items["hdbscan_outlier"] = df["is_birch_hdbscan_outlier"] == 1
        hdbscan_items["hdbscan_normal"] = df["is_birch_hdbscan_outlier"] == 0
        basket_parts.append(hdbscan_items)

    # Discretize numeric columns
    # balanceDiffOrig/balanceDiffDest sudah tidak ada sejak Phase 1 mengganti fitur ini
    # menjadi origError/destError - ganti referensinya di sini juga, kalau tidak loop di
    # bawah cuma akan skip kedua kolom itu (silent, tidak error, tapi origError/destError
    # jadi tidak pernah ikut dianalisis padahal ini fitur pembeda paling kuat di Phase 2).
    numeric_cols = [
        "amount",
        "oldbalanceOrg",
        "oldbalanceDest",
        "origError",
        "destError"
    ]

    for col in numeric_cols:
        if col in df.columns:
            cat = discretize_numeric_series(df[col], col_name=col, q=5)

            if cat is not None:
                dummies = pd.get_dummies(cat).astype(bool)
                basket_parts.append(dummies)
                log_prefect(f"Discretized {col}: {list(dummies.columns)}")
            else:
                log_prefect(f"Skipped {col}: not enough unique values")

    basket = pd.concat(basket_parts, axis=1)
    basket = basket.fillna(False).astype(bool)

    # Buang kolom yang semuanya False
    basket = basket.loc[:, basket.any(axis=0)]

    return basket


def filter_meaningful_rules(rules):
    if len(rules) == 0:
        return rules.copy()

    filtered = rules.copy()

    # Hindari consequent yang terlalu dominan dan kurang actionable
    trivial_consequents = [
        "isFraud_no",
        "hdbscan_normal",
        "orig_drained_no",
        "dest_merchant_no"
    ]

    for keyword in trivial_consequents:
        filtered = filtered[
            ~filtered["consequents_str"].str.contains(keyword, regex=False, na=False)
        ]

    # Prioritaskan consequent yang berguna untuk insight bisnis
    important_mask = (
        filtered["consequents_str"].str.contains("isFraud_yes", regex=False, na=False) |
        filtered["consequents_str"].str.contains("hdbscan_outlier", regex=False, na=False) |
        filtered["consequents_str"].str.contains("cluster_kmeans", regex=False, na=False) |
        filtered["consequents_str"].str.contains("very_high", regex=False, na=False) |
        filtered["consequents_str"].str.contains("very_low", regex=False, na=False) |
        filtered["consequents_str"].str.contains("orig_drained_yes", regex=False, na=False) |
        filtered["consequents_str"].str.contains("dest_merchant_yes", regex=False, na=False)
    )

    filtered = filtered[important_mask].copy()

    return filtered.sort_values(
        by=["lift", "confidence", "support"],
        ascending=[False, False, False]
    ).reset_index(drop=True)


def stringify_itemset(value):
    """
    Convert frozenset/set/list itemset menjadi string.
    Kalau value sudah string atau number, biarkan aman.
    """
    if isinstance(value, (frozenset, set, list, tuple)):
        return ", ".join(sorted(list(value)))
    return value


# LOAD DATASET
@task
def load_dataset(file_path):
    logger = get_run_logger()
    df = pd.read_parquet(file_path)
    display(df.head())
    logger.info(f"Loaded shape: {df.shape}")
    return df


# BUILD BASKET
@task
def build_basket_task(df):
    logger = get_run_logger()
    basket = build_basket(df)

    log_prefect(f"Basket shape: {basket.shape}")
    display(basket.head())
    logger.info(f"Basket shape: {basket.shape}")
    return basket


# ITEM FREQUENCY
@task
def item_frequency_analysis(basket):
    item_frequency = basket.mean().sort_values(ascending=False).to_frame("support")
    display(item_frequency)

    plt.figure(figsize=(10, 6))
    item_frequency.head(25)["support"].sort_values().plot(kind="barh")
    plt.title("Top 25 Item Frequency / Support")
    plt.xlabel("Support")
    plt.ylabel("Item")
    plt.tight_layout()
    plt.show()
    return item_frequency


# FREQUENT ITEMSETS
@task
def generate_frequent_itemsets(basket, MIN_SUPPORT, MAX_LEN):
    frequent_itemsets = apriori(
        basket,
        min_support=MIN_SUPPORT,
        use_colnames=True,
        max_len=MAX_LEN,
        low_memory=True
    )

    frequent_itemsets = frequent_itemsets.sort_values(
        by="support",
        ascending=False
    ).reset_index(drop=True)

    log_prefect(f"Frequent itemsets found: {len(frequent_itemsets)}")
    display(frequent_itemsets.head(20))
    return frequent_itemsets


# ASSOCIATION RULES
@task
def generate_association_rules(frequent_itemsets, MIN_CONFIDENCE, MIN_LIFT):
    if len(frequent_itemsets) == 0:
        raise ValueError("No frequent itemsets found. Coba turunkan MIN_SUPPORT.")

    rules = association_rules(
        frequent_itemsets,
        metric="lift",
        min_threshold=MIN_LIFT
    )

    rules = rules[
        (rules["confidence"] >= MIN_CONFIDENCE) &
        (rules["lift"] >= MIN_LIFT)
    ].copy()

    rules["antecedents_str"] = rules["antecedents"].apply(lambda x: ", ".join(sorted(list(x))))
    rules["consequents_str"] = rules["consequents"].apply(lambda x: ", ".join(sorted(list(x))))
    rules["antecedent_len"] = rules["antecedents"].apply(len)
    rules["consequent_len"] = rules["consequents"].apply(len)

    rules = rules.sort_values(
        by=["lift", "confidence", "support"],
        ascending=[False, False, False]
    ).reset_index(drop=True)

    log_prefect(f"Rules generated after filtering: {len(rules)}")
    display(rules[[
        "antecedents_str",
        "consequents_str",
        "support",
        "confidence",
        "lift",
        "leverage",
        "conviction"
    ]].head(20))
    return rules


# MEANINGFUL RULES
@task
def generate_meaningful_rules(rules):
    meaningful_rules = filter_meaningful_rules(rules)

    log_prefect(f"Meaningful rules: {len(meaningful_rules)}")
    display(meaningful_rules[[
        "antecedents_str",
        "consequents_str",
        "support",
        "confidence",
        "lift",
        "leverage",
        "conviction"
    ]].head(20))
    return meaningful_rules


# REPORT-WORTHY RULES
@task
def generate_report_rules(meaningful_rules):
    report_rules = meaningful_rules.copy()

    # Catatan: dua filter balanceDiffOrig/balanceDiffDest yang dulu ada di sini sengaja
    # dihapus. Kolom itu sudah diganti origError/destError sejak Phase 1, dan alasan
    # awal membuang balanceDiffOrig (nilainya nyaris selalu = -amount untuk transaksi
    # normal, jadi "mekanis"/tautologis dengan amount) tidak berlaku untuk origError/
    # destError - keduanya nyaris 0 untuk mayoritas transaksi dan cuma membesar pada
    # kelompok kecil yang justru fraud-rate-nya jauh di atas rata-rata (lihat Phase 2).
    # Kalau difilter di sini, rule paling informatif dari origError/destError malah
    # tidak akan pernah muncul di report_rules.

    # Buang consequent yang terlalu umum dan tidak menarik
    report_rules = report_rules[
        ~report_rules["consequents_str"].str.contains(
            "isFraud_no|hdbscan_normal|orig_drained_no|dest_merchant_no",
            regex=True,
            na=False
        )
    ].copy()

    # Filter rule yang cukup kuat
    report_rules = report_rules[
        (report_rules["confidence"] >= 0.30) &
        (report_rules["lift"] >= 1.20)
    ].copy()

    report_rules = report_rules.sort_values(
        by=["lift", "confidence", "support"],
        ascending=[False, False, False]
    ).reset_index(drop=True)

    log_prefect(f"Report-worthy rules: {len(report_rules)}")

    display(report_rules[[
        "antecedents_str",
        "consequents_str",
        "support",
        "confidence",
        "lift",
        "leverage",
        "conviction"
    ]].head(30))
    return report_rules


# IMPORTANT ITEM SUPPORT
@task
def show_important_item_support(basket):
    important_items = [
        "isFraud_yes",
        "isFraud_no",
        "hdbscan_outlier",
        "hdbscan_normal",
        "orig_drained_yes",
        "orig_drained_no",
        "dest_merchant_yes",
        "dest_merchant_no"
    ]

    for item in important_items:
        if item in basket.columns:
            log_prefect(f"{item}: {basket[item].mean():.6f} ({basket[item].mean() * 100:.4f}%)")


# FRAUD RULES
@task
def generate_fraud_rules(basket):
    fraud_itemsets = apriori(
        basket,
        min_support=0.0001,
        use_colnames=True,
        max_len=3,
        low_memory=True
    )

    fraud_rules = association_rules(
        fraud_itemsets,
        metric="lift",
        min_threshold=1.2
    )

    fraud_rules["antecedents_str"] = fraud_rules["antecedents"].apply(
        lambda x: ", ".join(sorted(list(x)))
    )

    fraud_rules["consequents_str"] = fraud_rules["consequents"].apply(
        lambda x: ", ".join(sorted(list(x)))
    )

    fraud_rules = fraud_rules[
        fraud_rules["consequents_str"].str.contains("isFraud_yes", regex=False, na=False)
    ].copy()

    # Buang antecedent yang terlalu mekanis kalau mau lebih bersih
    # (balanceDiffOrig/balanceDiffDest dihapus dari filter ini - lihat catatan di
    # generate_report_rules; kolomnya sudah diganti origError/destError)
    fraud_rules = fraud_rules[
        ~fraud_rules["antecedents_str"].str.contains(
            "isFraud_no",
            regex=True,
            na=False
        )
    ].copy()

    fraud_rules = fraud_rules.sort_values(
        by=["lift", "confidence", "support"],
        ascending=[False, False, False]
    ).reset_index(drop=True)

    log_prefect(f"Fraud rules: {len(fraud_rules)}")

    display(fraud_rules[[
        "antecedents_str",
        "consequents_str",
        "support",
        "confidence",
        "lift",
        "leverage",
        "conviction"
    ]].head(20))
    return fraud_rules


# SELECT TOP 10 RULES
@task
def select_top_10_rules(fraud_rules, report_rules):
    globals()["fraud_rules"] = fraud_rules
    selected_parts = []

    # 1. Fraud rules
    if "fraud_rules" in globals() and len(fraud_rules) > 0:
        selected_parts.append(fraud_rules.head(4))

    # 2. Outlier rules
    outlier_rules = report_rules[
        report_rules["consequents_str"].str.contains("hdbscan_outlier", regex=False, na=False)
    ].copy()

    if len(outlier_rules) > 0:
        selected_parts.append(outlier_rules.head(2))

    # 3. Cluster rules
    cluster_rules = report_rules[
        report_rules["consequents_str"].str.contains("cluster_kmeans", regex=False, na=False)
    ].copy()

    if len(cluster_rules) > 0:
        selected_parts.append(cluster_rules.head(2))

    # 4. General interesting rules
    general_rules = report_rules[
        ~report_rules["consequents_str"].str.contains(
            "isFraud_yes|hdbscan_outlier|cluster_kmeans",
            regex=True,
            na=False
        )
    ].copy()

    if len(general_rules) > 0:
        selected_parts.append(general_rules.head(5))

    # Gabungkan
    top_10_final = pd.concat(selected_parts, ignore_index=True)

    # Hindari duplikat
    top_10_final = top_10_final.drop_duplicates(
        subset=["antecedents_str", "consequents_str"]
    )

    # Kalau masih kurang dari 10, tambahkan dari report_rules
    if len(top_10_final) < 10:
        filler = report_rules[
            ~report_rules.set_index(["antecedents_str", "consequents_str"]).index.isin(
                top_10_final.set_index(["antecedents_str", "consequents_str"]).index
            )
        ].copy()

        top_10_final = pd.concat(
            [top_10_final, filler.head(10 - len(top_10_final))],
            ignore_index=True
        )

    top_10_final = top_10_final.head(10).copy()

    display(top_10_final[[
        "antecedents_str",
        "consequents_str",
        "support",
        "confidence",
        "lift",
        "leverage",
        "conviction"
    ]])
    return top_10_final


# PLOT TOP RULES
@task
def plot_top_rules(top_10_final):
    if len(top_10_final) > 0:
        plot_df = top_10_final.copy()
        plot_df["rule"] = plot_df["antecedents_str"] + " -> " + plot_df["consequents_str"]

        plt.figure(figsize=(10, 6))
        plot_df.set_index("rule")["lift"].sort_values().plot(kind="barh")
        plt.title("Top 10 Final Association Rules by Lift")
        plt.xlabel("Lift")
        plt.ylabel("Rule")
        plt.tight_layout()
        plt.show()
    else:
        log_prefect("No top rules available to plot.")


# CLEAN TOP 10 RULES
@task
def clean_top_10_rules(top_10_final, report_rules):
    top_10_final = top_10_final[
        ~top_10_final["antecedents_str"].str.contains(
            "isFraud_no|hdbscan_normal|orig_drained_no",
            regex=True,
            na=False
        )
    ].copy()

    # Kalau setelah dibuang jadi kurang dari 10, tambahkan filler dari report_rules
    if len(top_10_final) < 10:
        existing_pairs = set(
            zip(top_10_final["antecedents_str"], top_10_final["consequents_str"])
        )

        filler = report_rules[
            ~report_rules["antecedents_str"].str.contains(
                "isFraud_no|hdbscan_normal|orig_drained_no",
                regex=True,
                na=False
            )
        ].copy()

        filler = filler[
            ~filler.apply(
                lambda row: (row["antecedents_str"], row["consequents_str"]) in existing_pairs,
                axis=1
            )
        ]

        top_10_final = pd.concat(
            [top_10_final, filler.head(10 - len(top_10_final))],
            ignore_index=True
        )

    top_10_final = top_10_final.head(10).copy()

    display(top_10_final[[
        "antecedents_str",
        "consequents_str",
        "support",
        "confidence",
        "lift",
        "leverage",
        "conviction"
    ]])
    return top_10_final


# SAVE OUTPUTS
@task
def save_outputs(frequent_itemsets, rules, meaningful_rules, report_rules, top_10_final, fraud_rules, OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    globals()["fraud_rules"] = fraud_rules

    # Convert frozenset columns supaya readable di CSV
    frequent_itemsets_out = frequent_itemsets.copy()
    if "itemsets" in frequent_itemsets_out.columns:
        frequent_itemsets_out["itemsets"] = frequent_itemsets_out["itemsets"].apply(stringify_itemset)

    rules_out = rules.copy()
    meaningful_out = meaningful_rules.copy()
    report_out = report_rules.copy()
    top_10_final_out = top_10_final.copy()

    for df_out in [rules_out, meaningful_out, report_out, top_10_final_out]:
        for col in ["antecedents", "consequents"]:
            if col in df_out.columns:
                df_out[col] = df_out[col].apply(stringify_itemset)

    frequent_itemsets_path = os.path.join(OUTPUT_DIR, "frequent_itemsets.csv")
    association_rules_path = os.path.join(OUTPUT_DIR, "association_rules.csv")
    meaningful_rules_path = os.path.join(OUTPUT_DIR, "meaningful_rules.csv")
    report_rules_path = os.path.join(OUTPUT_DIR, "report_worthy_rules.csv")
    top_10_final_path = os.path.join(OUTPUT_DIR, "top_10_final_rules.csv")

    frequent_itemsets_out.to_csv(frequent_itemsets_path, index=False)
    rules_out.to_csv(association_rules_path, index=False)
    meaningful_out.to_csv(meaningful_rules_path, index=False)
    report_out.to_csv(report_rules_path, index=False)
    top_10_final_out.to_csv(top_10_final_path, index=False)

    if "fraud_rules" in globals():
        fraud_out = fraud_rules.copy()
        for col in ["antecedents", "consequents"]:
            if col in fraud_out.columns:
                fraud_out[col] = fraud_out[col].apply(stringify_itemset)

        fraud_rules_path = os.path.join(OUTPUT_DIR, "fraud_focused_rules.csv")
        fraud_out.to_csv(fraud_rules_path, index=False)
    else:
        fraud_rules_path = None

    log_prefect("Saved:")
    log_prefect(frequent_itemsets_path)
    log_prefect(association_rules_path)
    log_prefect(meaningful_rules_path)
    log_prefect(report_rules_path)
    log_prefect(top_10_final_path)
    if fraud_rules_path:
        log_prefect(fraud_rules_path)


# FLOW
@flow(name="Phase 3")
def association_rules_pipeline():

    file_path = "../datasets/phase_2/paysim-dataset-phase2.parquet"
    OUTPUT_DIR = "../datasets/phase_3"

    MIN_SUPPORT = 0.005
    MIN_CONFIDENCE = 0.50
    MIN_LIFT = 1.20
    MAX_LEN = 3

    df = load_dataset(file_path)
    basket = build_basket_task(df)
    item_frequency_analysis(basket)

    frequent_itemsets = generate_frequent_itemsets(basket, MIN_SUPPORT, MAX_LEN)
    rules = generate_association_rules(frequent_itemsets, MIN_CONFIDENCE, MIN_LIFT)
    meaningful_rules = generate_meaningful_rules(rules)
    report_rules = generate_report_rules(meaningful_rules)
    show_important_item_support(basket)

    payment_rules = report_rules[
        report_rules["antecedents_str"].str.contains("type_PAYMENT", na=False)
        | report_rules["consequents_str"].str.contains("type_PAYMENT", na=False)
    ].sort_values("lift", ascending=False)

    logger = get_run_logger()
    logger.info(f"Number of rules related to PAYMENT: {len(payment_rules)}")
    logger.info(f"Rules PAYMENT:\n{payment_rules[['antecedents_str','consequents_str','support','confidence','lift']].head(5)}")

    fraud_rules = generate_fraud_rules(basket)
    top_10_final = select_top_10_rules(fraud_rules, report_rules)
    plot_top_rules(top_10_final)
    top_10_final = clean_top_10_rules(top_10_final, report_rules)
    plot_top_rules(top_10_final)

    save_outputs(
        frequent_itemsets,
        rules,
        meaningful_rules,
        report_rules,
        top_10_final,
        fraud_rules,
        OUTPUT_DIR
    )


# RUN
if __name__ == "__main__":
    association_rules_pipeline()
