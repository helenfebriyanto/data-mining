from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

try:
    import duckdb  # type: ignore
except Exception:  # pragma: no cover
    duckdb = None

from fallback_data import rules as fallback_rules
from business_labels import add_rule_business_columns, CLUSTER_LABELS

RISK_ORDER = ["Normal", "Low", "Medium", "High", "Critical"]
TYPE_COLS = ["type_CASH_IN", "type_CASH_OUT", "type_DEBIT", "type_PAYMENT", "type_TRANSFER"]


def log(message: str) -> None:
    print(f"[dashboard-cache] {message}")


def write_df(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    display_path = path
    try:
        df.to_parquet(path, index=False)
    except ImportError:
        # Keep the dashboard usable in environments where pyarrow/fastparquet
        # has not been installed yet. The app can read either parquet or CSV.
        display_path = path.with_suffix(".csv")
        df.to_csv(display_path, index=False)
    except Exception:
        raise
    root = display_path.parent.parent if display_path.parent.name == "cache" else display_path.parent
    log(f"wrote {display_path.relative_to(root)} ({len(df):,} rows)")


def read_csv_if_exists(path: Path) -> pd.DataFrame | None:
    if path.exists():
        return pd.read_csv(path)
    return None


def read_parquet_if_exists(path: Path, columns: list[str] | None = None) -> pd.DataFrame | None:
    if path.exists():
        return pd.read_parquet(path, columns=columns)
    return None


def normalize_percentage(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "percentage" not in df.columns:
        return df
    df = df.copy()
    df["percentage"] = pd.to_numeric(df["percentage"], errors="coerce")
    if df["percentage"].max(skipna=True) <= 1.0:
        df["percentage"] = df["percentage"] * 100
    return df


def copy_phase4_summaries(project_root: Path, cache_dir: Path) -> None:
    phase4 = project_root / "datasets" / "phase_4"
    mapping = {
        "risk_summary.csv": "risk_summary.parquet",
        "anomaly_type_summary.csv": "anomaly_type_summary.parquet",
        "investigation_summary.csv": "investigation_summary.parquet",
        "fraud_by_score.csv": "fraud_by_score.parquet",
        "method_overlap.csv": "method_overlap.parquet",
        "fraud_validation_metrics.csv": "fraud_validation_metrics.parquet",
        "cluster_kmeans_risk_summary.csv": "cluster_kmeans_risk_summary_raw.parquet",
        "high_risk_type_breakdown.csv": "high_risk_type_breakdown.parquet",
    }
    for src_name, dst_name in mapping.items():
        src = phase4 / src_name
        if not src.exists():
            log(f"missing optional Phase 4 summary: {src}")
            continue
        df = pd.read_csv(src)
        df = normalize_percentage(df)
        write_df(df, cache_dir / dst_name)


def build_cluster_summary(project_root: Path, cache_dir: Path) -> pd.DataFrame:
    phase2_parquet = project_root / "datasets" / "phase_2" / "paysim-dataset-phase2.parquet"
    phase4_cluster = cache_dir / "cluster_kmeans_risk_summary_raw.parquet"

    if phase4_cluster.exists():
        cluster = pd.read_parquet(phase4_cluster)
    elif phase2_parquet.exists():
        if duckdb is not None:
            query = f"""
                SELECT
                    cluster_kmeans,
                    COUNT(*) AS transactions,
                    SUM(isFraud) AS fraud_count,
                    AVG(isFraud) AS fraud_rate,
                    AVG(amount) AS avg_amount,
                    AVG(oldbalanceOrg) AS avg_oldbalanceOrg,
                    AVG(oldbalanceDest) AS avg_oldbalanceDest,
                    AVG(origError) AS avg_origError,
                    AVG(destError) AS avg_destError,
                    AVG(isDestMerchant) AS dest_merchant_rate,
                    AVG(origDrainedToZero) AS orig_drained_rate,
                    AVG(type_CASH_IN) AS type_cash_in_rate,
                    AVG(type_CASH_OUT) AS type_cash_out_rate,
                    AVG(type_DEBIT) AS type_debit_rate,
                    AVG(type_PAYMENT) AS type_payment_rate,
                    AVG(type_TRANSFER) AS type_transfer_rate
                FROM read_parquet('{phase2_parquet.as_posix()}')
                GROUP BY cluster_kmeans
                ORDER BY cluster_kmeans
            """
            cluster = duckdb.sql(query).df()
        else:
            cols = [
                "cluster_kmeans", "isFraud", "amount", "oldbalanceOrg", "oldbalanceDest", "origError", "destError",
                "isDestMerchant", "origDrainedToZero", *TYPE_COLS,
            ]
            df = pd.read_parquet(phase2_parquet, columns=[c for c in cols if c])
            agg = {
                "isFraud": ["size", "sum", "mean"],
                "amount": "mean", "oldbalanceOrg": "mean", "oldbalanceDest": "mean", "origError": "mean", "destError": "mean",
                "isDestMerchant": "mean", "origDrainedToZero": "mean",
            }
            for col in TYPE_COLS:
                if col in df.columns:
                    agg[col] = "mean"
            cluster = df.groupby("cluster_kmeans").agg(agg)
            cluster.columns = ["_".join(x).strip("_") for x in cluster.columns.to_flat_index()]
            cluster = cluster.reset_index().rename(columns={"isFraud_size": "transactions", "isFraud_sum": "fraud_count", "isFraud_mean": "fraud_rate"})
    else:
        log("no Phase 2 parquet or Phase 4 cluster summary found; using fallback segment summary")
        from fallback_data import cluster_summary
        cluster = cluster_summary()
        write_df(cluster, cache_dir / "cluster_summary.parquet")
        return cluster

    cluster = cluster.copy()
    cluster["cluster_kmeans"] = cluster["cluster_kmeans"].astype(int)
    total = cluster["transactions"].sum()
    cluster["population_share"] = cluster["transactions"] / total

    # Attach business names/profiles. These labels come from the Phase 2 profile and Phase 4 risk summaries.
    segment_meta = {
        0: {
            "segment_name": "Exceptional High-Value Transfer Segment",
            "business_profile": "Very small segment dominated by unusual high-value transfer behavior and balance mismatches. Not labelled as fraud, but operationally important.",
            "business_value": "Use as an exception-monitoring queue, not a mass customer segment.",
            "main_behavior": "Large transfer size and high destination balance mismatch",
        },
        1: {
            "segment_name": "Mainstream Everyday Banking Segment",
            "business_profile": "The core transaction population with mixed payment, cash-out, cash-in and transfer activity. Fraud appears because this group is large, but the rate is close to baseline.",
            "business_value": "Use as the baseline population for monitoring and policy comparison.",
            "main_behavior": "Ordinary mixed transaction behavior",
        },
        2: {
            "segment_name": "High-Balance Cash-In Segment",
            "business_profile": "Cash-in dominated group with very high origin balances. Better interpreted as a liquidity behavior segment than as a fraud segment.",
            "business_value": "Useful for monitoring high-balance funding behavior and balance-related rules.",
            "main_behavior": "Cash-in transactions with very high sender balances",
        },
        3: {
            "segment_name": "Very High-Balance Cash-In Segment",
            "business_profile": "Smaller cash-in group with very high starting balances and low merchant involvement.",
            "business_value": "Useful for separating very high-balance cash-in behavior from ordinary transactions.",
            "main_behavior": "Cash-in transactions with very high balances",
        },
    }
    for col in ["segment_name", "business_profile", "business_value", "main_behavior"]:
        cluster[col] = cluster["cluster_kmeans"].map(lambda x: segment_meta.get(int(x), {}).get(col, CLUSTER_LABELS.get(int(x), f"Segment {x}")))

    # Ensure columns expected by app exist.
    for col in ["avg_risk_score", "high_risk_count", "critical_count", "high_risk_rate"]:
        if col not in cluster.columns:
            cluster[col] = np.nan

    write_df(cluster, cache_dir / "cluster_summary.parquet")
    return cluster


def build_rules(project_root: Path, cache_dir: Path) -> None:
    phase3 = project_root / "datasets" / "phase_3"
    candidates = [
        phase3 / "top_10_final_rules.csv",
        phase3 / "fraud_focused_rules.csv",
        phase3 / "report_worthy_rules.csv",
    ]
    rules = None
    for path in candidates:
        if path.exists():
            rules = pd.read_csv(path).head(10)
            log(f"using rules from {path}")
            break
    if rules is None:
        log("no Phase 3 rules CSV found; using fallback top rules from notebook output")
        rules = fallback_rules()
    rules = add_rule_business_columns(rules)
    write_df(rules, cache_dir / "top_rules_business.parquet")


def derive_transaction_type(df: pd.DataFrame) -> pd.Series:
    if "transaction_type" in df.columns:
        return df["transaction_type"].astype(str)
    available = [col for col in TYPE_COLS if col in df.columns]
    if not available:
        return pd.Series(["Unknown"] * len(df), index=df.index)
    idx = df[available].astype(float).values.argmax(axis=1)
    names = [col.replace("type_", "") for col in available]
    return pd.Series([names[i] for i in idx], index=df.index)


def build_top_suspicious(project_root: Path, cache_dir: Path, max_rows: int) -> None:
    src = project_root / "datasets" / "phase_4" / "paysim-suspicious-transactions.parquet"
    if not src.exists():
        log(f"no suspicious transaction parquet found at {src}; creating empty table")
        empty = pd.DataFrame(columns=["step", "transaction_type", "amount", "risk_score", "risk_level", "investigation_category", "anomaly_type", "anomaly_reason", "cluster_kmeans", "isFraud"])
        write_df(empty, cache_dir / "top_suspicious_light.parquet")
        return

    all_cols = pd.read_parquet(src).columns.tolist()
    wanted = [
        "step", "amount", "isFraud", "risk_score", "risk_level", "anomaly_type", "investigation_category", "anomaly_reason", "cluster_kmeans",
        "flag_IQR", "flag_ZScore", "flag_IsoForest", "flag_HDBSCAN", "flag_BalanceMismatch", "high_risk", "critical_risk", *TYPE_COLS,
    ]
    cols = [c for c in wanted if c in all_cols]
    df = pd.read_parquet(src, columns=cols)
    df["transaction_type"] = derive_transaction_type(df)
    keep = ["step", "transaction_type", "amount", "risk_score", "risk_level", "investigation_category", "anomaly_type", "anomaly_reason", "cluster_kmeans", "isFraud"]
    keep = [c for c in keep if c in df.columns]
    df = df[keep].head(max_rows).copy()
    if "cluster_kmeans" in df.columns:
        df["cluster_kmeans"] = df["cluster_kmeans"].map(lambda x: CLUSTER_LABELS.get(int(x), f"Segment {x}") if pd.notna(x) else "Unknown")
    write_df(df, cache_dir / "top_suspicious_light.parquet")


def build_missing_summary_from_phase2(project_root: Path, cache_dir: Path) -> None:
    # If Phase 4 summaries are missing, build minimal high-level summaries from fallback.
    # Full anomaly summaries require Phase 4 because Phase 2 does not contain risk columns.
    from fallback_data import risk_summary, anomaly_type_summary, investigation_summary, fraud_by_score, method_overlap, fraud_validation_metrics
    fallback_map = {
        "risk_summary.parquet": risk_summary,
        "anomaly_type_summary.parquet": anomaly_type_summary,
        "investigation_summary.parquet": investigation_summary,
        "fraud_by_score.parquet": fraud_by_score,
        "method_overlap.parquet": method_overlap,
        "fraud_validation_metrics.parquet": fraud_validation_metrics,
    }
    for name, func in fallback_map.items():
        path = cache_dir / name
        if not path.exists():
            log(f"{name} missing; using fallback notebook summary")
            write_df(func(), path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build small parquet cache files for the Phase 5 Dash dashboard.")
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parent.parent), help="Project root containing datasets/phase_*/ outputs.")
    parser.add_argument("--cache-dir", default=str(Path(__file__).resolve().parent / "cache"), help="Output cache directory.")
    parser.add_argument("--max-queue-rows", type=int, default=20_000, help="Maximum suspicious transaction rows loaded into dashboard cache.")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    cache_dir = Path(args.cache_dir).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)

    log(f"project root: {project_root}")
    log(f"cache dir: {cache_dir}")

    copy_phase4_summaries(project_root, cache_dir)
    build_cluster_summary(project_root, cache_dir)
    build_rules(project_root, cache_dir)
    build_top_suspicious(project_root, cache_dir, max_rows=args.max_queue_rows)
    build_missing_summary_from_phase2(project_root, cache_dir)

    manifest = {
        "project_root": str(project_root),
        "cache_dir": str(cache_dir),
        "files": sorted([p.name for p in cache_dir.glob("*.parquet")]),
    }
    (cache_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log("cache build complete")


if __name__ == "__main__":
    main()
