"""
pipeline/es_indexer.py
========================
Definisi mapping index Elasticsearch & fungsi bulk-index. Dipanggil oleh
pipeline/flow.py. Dipisah supaya mapping mudah ditinjau/diaudit sendiri.
"""
from __future__ import annotations

from typing import Iterable

import pandas as pd

TRANSAKSI_MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {"analyzer": {"default": {"type": "standard"}}},
    },
    "mappings": {
        "properties": {
            "transaction_id": {"type": "keyword"},
            "step": {"type": "integer"},
            "transaction_type": {"type": "keyword"},
            "amount": {"type": "double"},
            "oldbalanceOrg": {"type": "double"},
            "oldbalanceDest": {"type": "double"},
            "origError": {"type": "double"},
            "destError": {"type": "double"},
            "origDrainedToZero": {"type": "boolean"},
            "isDestMerchant": {"type": "boolean"},
            "cluster_kmeans": {"type": "integer"},
            "flag_IQR": {"type": "boolean"},
            "flag_ZScore": {"type": "boolean"},
            "flag_IsoForest": {"type": "boolean"},
            "flag_HDBSCAN": {"type": "boolean"},
            "flag_BalanceMismatch": {"type": "boolean"},
            "risk_score": {"type": "byte"},
            "risk_level": {"type": "keyword"},
            "anomaly_type": {"type": "keyword"},
            "investigation_category": {"type": "keyword"},
            "anomaly_reason": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 512}},
            },
            "isFraud": {"type": "boolean"},
            "wilayah": {"type": "keyword"},
            "high_risk": {"type": "boolean"},
        }
    },
}

POLA_MAPPING = {
    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
    "mappings": {
        "properties": {
            "rule_id": {"type": "keyword"},
            "antecedents_str": {"type": "keyword"},
            "consequents_str": {"type": "keyword"},
            "support": {"type": "double"},
            "confidence": {"type": "double"},
            "lift": {"type": "double"},
            "when_text": {"type": "text"},
            "then_text": {"type": "text"},
            "coverage_fmt": {"type": "keyword"},
            "confidence_fmt": {"type": "keyword"},
            "lift_fmt": {"type": "keyword"},
            "takeaway": {"type": "text"},
            "recommendation": {"type": "text"},
            "rule_group": {"type": "keyword"},
            "is_top10": {"type": "boolean"},
            "penting": {"type": "keyword"},
        }
    },
}


def recreate_index(client, name: str, mapping: dict):
    if client.indices.exists(index=name):
        client.indices.delete(index=name)
    client.indices.create(index=name, body=mapping)


def _iter_docs(df: pd.DataFrame, index_name: str, id_col: str) -> Iterable[dict]:
    records = df.to_dict(orient="records")
    for rec in records:
        yield {"_index": index_name, "_id": rec[id_col], "_source": rec}


def bulk_index_dataframe(client, df: pd.DataFrame, index_name: str, id_col: str,
                          chunk_size: int = 5000, logger=None) -> int:
    from elasticsearch.helpers import bulk, BulkIndexError

    total = 0
    n = len(df)
    for start in range(0, n, chunk_size):
        chunk = df.iloc[start:start + chunk_size]
        try:
            ok, _ = bulk(client, _iter_docs(chunk, index_name, id_col), chunk_size=chunk_size, request_timeout=120)
            total += ok
        except BulkIndexError as e:  # pragma: no cover - defensif, tetap lanjut
            if logger:
                logger.warning(f"Sebagian dokumen gagal diindex ({len(e.errors)} error) - lanjut ke batch berikutnya")
        if logger and (start // chunk_size) % 20 == 0:
            logger.info(f"  indexing {index_name}: {min(start + chunk_size, n):,}/{n:,}")
    return total
