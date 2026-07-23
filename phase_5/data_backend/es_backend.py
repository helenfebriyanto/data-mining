"""
data_backend/es_backend.py
============================
Implementasi DataBackend memakai Elasticsearch. Ini jalur yang diminta di
brief awal ("pake elastic search kalo bisa"). Jalankan `docker-compose up -d`
(lihat docker-compose.yml di root project) lalu jalankan pipeline
(`python -m pipeline.flow`) untuk mengisi index-nya.

Kenapa Elasticsearch cocok di sini:
- Agregasi (terms/filter aggregation) atas jutaan baris tetap <100ms karena
  Elasticsearch menghitungnya dari struktur index (inverted index + doc
  values per-kolom), bukan memindai baris satu per satu.
- Pencarian bebas (full-text) pada anomaly_reason / transaction_id memakai
  inverted index -> ini keunggulan dibanding pemindaian LIKE/ILIKE biasa
  (lihat catatan performa di README/BENCHMARK.md - inilah tepatnya kasus
  yang paling lambat di mode fallback DuckDB, dan paling diuntungkan kalau
  Elasticsearch benar-benar dinyalakan).

Catatan lingkungan pengembangan: sandbox tempat proyek ini dibangun tidak
memiliki akses jaringan ke elastic.co / Docker Hub (lihat README bagian
"Batasan lingkungan pengembangan"), sehingga kelas ini tidak bisa diuji
langsung terhadap cluster asli di sana - tapi memakai elasticsearch-py resmi
dengan Query DSL standar, dan struktur query-nya dites lewat query yang
dihasilkan (lihat tools/test_es_backend.py).
"""
from __future__ import annotations

from typing import Any, Optional

from data_backend.base import DataBackend, Filters

try:
    from elasticsearch import Elasticsearch
    from elasticsearch.helpers import bulk as es_bulk
except ImportError:  # pragma: no cover
    Elasticsearch = None
    es_bulk = None

INDEX_TRANSAKSI = "fance_transaksi"
INDEX_POLA = "fance_pola_asosiasi"

CATEGORICAL_FIELD_MAP = {
    "wilayah": "wilayah",
    "jenis_transaksi": "transaction_type",
    "segmen": "cluster_kmeans",
    "risk_level": "risk_level",
    "investigation_category": "investigation_category",
    "anomaly_type": "anomaly_type",
}


def _build_es_query(filters: Filters, extra_must: Optional[list] = None) -> dict:
    must = list(extra_must or [])
    filter_clauses = []
    for key, field in CATEGORICAL_FIELD_MAP.items():
        values = getattr(filters, key)
        if values:
            filter_clauses.append({"terms": {field: list(values)}})
    if filters.amount_min is not None or filters.amount_max is not None:
        rng = {}
        if filters.amount_min is not None:
            rng["gte"] = filters.amount_min
        if filters.amount_max is not None:
            rng["lte"] = filters.amount_max
        filter_clauses.append({"range": {"amount": rng}})
    if filters.risk_score_min is not None or filters.risk_score_max is not None:
        rng = {}
        if filters.risk_score_min is not None:
            rng["gte"] = filters.risk_score_min
        if filters.risk_score_max is not None:
            rng["lte"] = filters.risk_score_max
        filter_clauses.append({"range": {"risk_score": rng}})
    if filters.search:
        must.append({
            "multi_match": {
                "query": filters.search,
                # transaction_id pakai sub-field .keyword utk exact/prefix,
                # anomaly_reason full-text dgn analisa bahasa standar
                "fields": ["transaction_id^3", "anomaly_reason"],
                "type": "best_fields",
            }
        })
    query: dict = {"bool": {}}
    if must:
        query["bool"]["must"] = must
    if filter_clauses:
        query["bool"]["filter"] = filter_clauses
    if not must and not filter_clauses:
        query = {"match_all": {}}
    return query


class ElasticsearchBackend(DataBackend):
    name = "elasticsearch"

    def __init__(self, url: str, timeout: float = 3.0):
        if Elasticsearch is None:
            raise RuntimeError("Package 'elasticsearch' belum terpasang (pip install elasticsearch).")
        self.client = Elasticsearch(url, request_timeout=timeout)

    def ping(self) -> bool:
        try:
            return bool(self.client.ping())
        except Exception:
            return False

    def _agg_search(self, filters: Filters, aggs: dict, size: int = 0) -> dict:
        body = {"query": _build_es_query(filters), "aggs": aggs, "size": size, "track_total_hits": True}
        return self.client.search(index=INDEX_TRANSAKSI, body=body).body

    # ------------------------------------------------------------------
    def get_kpi(self, filters: Filters) -> dict[str, Any]:
        aggs = {
            "fraud": {"filter": {"term": {"isFraud": True}}},
            "high_risk": {"filter": {"bool": {"should": [
                {"range": {"risk_score": {"gte": 3}}}, {"term": {"flag_HDBSCAN": True}},
            ]}}},
            "kritis": {"filter": {"term": {"risk_level": "Kritis"}}},
            "avg_risk": {"avg": {"field": "risk_score"}},
            "high_risk_fraud": {"filter": {"bool": {"must": [
                {"term": {"isFraud": True}},
                {"bool": {"should": [{"range": {"risk_score": {"gte": 3}}}, {"term": {"flag_HDBSCAN": True}}]}},
            ]}}},
        }
        res = self._agg_search(filters, aggs)
        total = res["hits"]["total"]["value"]
        fraud = res["aggregations"]["fraud"]["doc_count"]
        high_risk = res["aggregations"]["high_risk"]["doc_count"]
        baseline_fraud_rate = 0.0012883
        high_risk_fraud_rate = (res["aggregations"]["high_risk_fraud"]["doc_count"] / high_risk) if high_risk else None
        enrichment = (high_risk_fraud_rate / baseline_fraud_rate) if high_risk_fraud_rate else None
        return dict(
            total_transaksi=total, total_fraud=fraud, total_high_risk=high_risk,
            total_kritis=res["aggregations"]["kritis"]["doc_count"],
            fraud_rate=(fraud / total) if total else 0.0,
            high_risk_rate=(high_risk / total) if total else 0.0,
            avg_risk_score=res["aggregations"]["avg_risk"]["value"] or 0.0,
            high_risk_fraud_rate=high_risk_fraud_rate, fraud_enrichment=enrichment,
        )

    def get_segment_summary(self, filters: Filters) -> list[dict]:
        aggs = {
            "per_segmen": {
                "terms": {"field": "cluster_kmeans", "size": 10},
                "aggs": {
                    "fraud": {"filter": {"term": {"isFraud": True}}},
                    "high_risk": {"filter": {"bool": {"should": [
                        {"range": {"risk_score": {"gte": 3}}}, {"term": {"flag_HDBSCAN": True}},
                    ]}}},
                    "kritis": {"filter": {"term": {"risk_level": "Kritis"}}},
                    "avg_risk": {"avg": {"field": "risk_score"}},
                },
            }
        }
        res = self._agg_search(filters, aggs)
        buckets = res["aggregations"]["per_segmen"]["buckets"]
        total_all = sum(b["doc_count"] for b in buckets) or 1
        out = []
        for b in buckets:
            n = b["doc_count"]
            out.append(dict(
                cluster_kmeans=b["key"], transactions=n,
                fraud_count=b["fraud"]["doc_count"],
                avg_risk_score=b["avg_risk"]["value"] or 0.0,
                high_risk_count=b["high_risk"]["doc_count"],
                critical_count=b["kritis"]["doc_count"],
                population_share=n / total_all,
                fraud_rate=(b["fraud"]["doc_count"] / n) if n else 0.0,
                high_risk_rate=(b["high_risk"]["doc_count"] / n) if n else 0.0,
            ))
        return sorted(out, key=lambda r: r["cluster_kmeans"])

    def _simple_terms_summary(self, filters: Filters, field: str, key_name: str) -> list[dict]:
        aggs = {"by_field": {"terms": {"field": field, "size": 50}}}
        res = self._agg_search(filters, aggs)
        buckets = res["aggregations"]["by_field"]["buckets"]
        total = sum(b["doc_count"] for b in buckets) or 1
        return [
            {key_name: b["key"], "transactions": b["doc_count"], "percentage": 100.0 * b["doc_count"] / total}
            for b in buckets
        ]

    def get_risk_summary(self, filters: Filters) -> list[dict]:
        return self._simple_terms_summary(filters, "risk_level", "risk_level")

    def get_anomaly_type_summary(self, filters: Filters) -> list[dict]:
        return self._simple_terms_summary(filters, "anomaly_type", "anomaly_type")

    def get_investigation_summary(self, filters: Filters) -> list[dict]:
        return self._simple_terms_summary(filters, "investigation_category", "investigation_category")

    def get_fraud_by_score(self, filters: Filters) -> list[dict]:
        aggs = {"by_score": {"terms": {"field": "risk_score", "size": 10},
                              "aggs": {"fraud": {"filter": {"term": {"isFraud": True}}}}}}
        res = self._agg_search(filters, aggs)
        out = []
        for b in res["aggregations"]["by_score"]["buckets"]:
            n = b["doc_count"]
            out.append(dict(risk_score=b["key"], transactions=n, fraud_count=b["fraud"]["doc_count"],
                             fraud_rate=(b["fraud"]["doc_count"] / n) if n else 0.0))
        return sorted(out, key=lambda r: r["risk_score"])

    def get_method_overlap(self, filters: Filters) -> list[dict]:
        methods = ["flag_IQR", "flag_ZScore", "flag_IsoForest", "flag_HDBSCAN"]
        aggs = {}
        for m1 in methods:
            for m2 in methods:
                aggs[f"{m1}__{m2}"] = {"filter": {"bool": {"filter": [
                    {"term": {m1: True}}, {"term": {m2: True}}
                ]}}}
        res = self._agg_search(filters, aggs)
        matrix = []
        for m1 in methods:
            entry = {"method": m1}
            for m2 in methods:
                entry[m2] = res["aggregations"][f"{m1}__{m2}"]["doc_count"]
            matrix.append(entry)
        return matrix

    def get_wilayah_breakdown(self, filters: Filters) -> list[dict]:
        aggs = {
            "per_wilayah": {
                "terms": {"field": "wilayah", "size": 20},
                "aggs": {
                    "fraud": {"filter": {"term": {"isFraud": True}}},
                    "high_risk": {"filter": {"bool": {"should": [
                        {"range": {"risk_score": {"gte": 3}}}, {"term": {"flag_HDBSCAN": True}},
                    ]}}},
                    "avg_risk": {"avg": {"field": "risk_score"}},
                },
            }
        }
        res = self._agg_search(filters, aggs)
        buckets = res["aggregations"]["per_wilayah"]["buckets"]
        total = sum(b["doc_count"] for b in buckets) or 1
        out = []
        for b in buckets:
            n = b["doc_count"]
            out.append(dict(
                wilayah=b["key"], transactions=n, fraud_count=b["fraud"]["doc_count"],
                high_risk_count=b["high_risk"]["doc_count"], avg_risk_score=b["avg_risk"]["value"] or 0.0,
                share=n / total, fraud_rate=(b["fraud"]["doc_count"] / n) if n else 0.0,
                high_risk_rate=(b["high_risk"]["doc_count"] / n) if n else 0.0,
            ))
        return sorted(out, key=lambda r: -r["transactions"])

    def get_transaction_type_breakdown(self, filters: Filters) -> list[dict]:
        aggs = {"per_tipe": {"terms": {"field": "transaction_type", "size": 10},
                              "aggs": {"fraud": {"filter": {"term": {"isFraud": True}}}}}}
        res = self._agg_search(filters, aggs)
        buckets = res["aggregations"]["per_tipe"]["buckets"]
        total = sum(b["doc_count"] for b in buckets) or 1
        out = []
        for b in buckets:
            n = b["doc_count"]
            out.append(dict(transaction_type=b["key"], transactions=n, fraud_count=b["fraud"]["doc_count"],
                             share=n / total, fraud_rate=(b["fraud"]["doc_count"] / n) if n else 0.0))
        return sorted(out, key=lambda r: -r["transactions"])

    def search_transactions(
        self, filters: Filters, sort_col: str = "risk_score", sort_dir: str = "desc",
        page: int = 1, page_size: int = 25,
    ) -> tuple[list[dict], int]:
        sort_field_map = {
            "risk_score": "risk_score", "amount": "amount", "step": "step",
            "transaction_type": "transaction_type", "wilayah": "wilayah",
            "cluster_kmeans": "cluster_kmeans", "risk_level": "risk_level.keyword",
            "isFraud": "isFraud", "anomaly_type": "anomaly_type",
        }
        sort_field = sort_field_map.get(sort_col, "risk_score")
        body = {
            "query": _build_es_query(filters),
            "sort": [{sort_field: {"order": sort_dir}}],
            "from": max(0, (page - 1) * page_size),
            "size": page_size,
            "track_total_hits": True,
        }
        res = self.client.search(index=INDEX_TRANSAKSI, body=body).body
        rows = [h["_source"] for h in res["hits"]["hits"]]
        total = res["hits"]["total"]["value"]
        return rows, total

    def get_rules(self, rule_group: Optional[str] = None, min_lift: float = 0.0,
                  search: str = "", limit: Optional[int] = None) -> list[dict]:
        filt = []
        must = []
        if rule_group:
            filt.append({"term": {"rule_group": rule_group}})
        if min_lift:
            filt.append({"range": {"lift": {"gte": min_lift}}})
        if search:
            must.append({"multi_match": {"query": search, "fields": ["when_text", "then_text"]}})
        query = {"bool": {}}
        if must:
            query["bool"]["must"] = must
        if filt:
            query["bool"]["filter"] = filt
        if not must and not filt:
            query = {"match_all": {}}
        body = {
            "query": query,
            "sort": [{"is_top10": {"order": "desc"}}, {"lift": {"order": "desc"}}],
            "size": limit or 200,
        }
        res = self.client.search(index=INDEX_POLA, body=body).body
        return [h["_source"] for h in res["hits"]["hits"]]

    def count(self, filters: Filters) -> int:
        body = {"query": _build_es_query(filters), "track_total_hits": True}
        res = self.client.count(index=INDEX_TRANSAKSI, body={"query": body["query"]}).body
        return res["count"]
