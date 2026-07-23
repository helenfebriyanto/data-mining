"""
data_backend/base.py
=====================
Kontrak bersama untuk sumber data dashboard. Dashboard TIDAK PERNAH memanggil
DuckDB atau Elasticsearch secara langsung - selalu lewat antarmuka ini, supaya
kedua backend bisa saling menggantikan tanpa mengubah kode halaman/callback.

Kenapa dua backend?
- ElasticsearchBackend  : jalur "produksi" sesuai permintaan - dipakai kalau
  kelompok menjalankan Elasticsearch (lihat docker-compose.yml).
- DuckDBBackend         : jalan otomatis tanpa instalasi tambahan apa pun,
  tetap memenuhi target <100ms pada 6,3 juta baris (lihat BENCHMARK.md),
  dan dipakai sebagai fallback kalau Elasticsearch sedang tidak menyala -
  dashboard tidak pernah "mati" gara-gara satu servis down.

Setiap method menerima `filters: dict` dengan kunci opsional berikut (semua
opsional, nilai kosong/None berarti "semua data"):
    wilayah: list[str]
    jenis_transaksi: list[str]
    segmen: list[int]
    risk_level: list[str]
    investigation_category: list[str]
    anomaly_type: list[str]
    search: str                  (dicari pada transaction_id & anomaly_reason)
    amount_min / amount_max: float
    risk_score_min / risk_score_max: int
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Filters:
    wilayah: list = field(default_factory=list)
    jenis_transaksi: list = field(default_factory=list)
    segmen: list = field(default_factory=list)
    risk_level: list = field(default_factory=list)
    investigation_category: list = field(default_factory=list)
    anomaly_type: list = field(default_factory=list)
    search: str = ""
    amount_min: Optional[float] = None
    amount_max: Optional[float] = None
    risk_score_min: Optional[int] = None
    risk_score_max: Optional[int] = None

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "Filters":
        if not d:
            return cls()
        known = {f: d.get(f) for f in cls.__dataclass_fields__ if d.get(f) not in (None, [], "")}
        return cls(**known)

    def is_empty(self) -> bool:
        return self == Filters()


class DataBackend(ABC):
    """Kontrak yang wajib dipenuhi setiap backend data."""

    name: str = "backend"

    @abstractmethod
    def ping(self) -> bool:
        """True kalau backend siap dipakai (mis. koneksi ES berhasil)."""

    @abstractmethod
    def get_kpi(self, filters: Filters) -> dict[str, Any]:
        """Total transaksi, fraud, high-risk, fraud_rate, enrichment untuk filter aktif."""

    @abstractmethod
    def get_segment_summary(self, filters: Filters) -> list[dict]:
        """Statistik per segmen (dihitung ulang sesuai filter aktif)."""

    @abstractmethod
    def get_risk_summary(self, filters: Filters) -> list[dict]:
        ...

    @abstractmethod
    def get_anomaly_type_summary(self, filters: Filters) -> list[dict]:
        ...

    @abstractmethod
    def get_investigation_summary(self, filters: Filters) -> list[dict]:
        ...

    @abstractmethod
    def get_fraud_by_score(self, filters: Filters) -> list[dict]:
        ...

    @abstractmethod
    def get_method_overlap(self, filters: Filters) -> list[dict]:
        ...

    @abstractmethod
    def get_wilayah_breakdown(self, filters: Filters) -> list[dict]:
        ...

    @abstractmethod
    def get_transaction_type_breakdown(self, filters: Filters) -> list[dict]:
        ...

    @abstractmethod
    def search_transactions(
        self, filters: Filters, sort_col: str = "risk_score", sort_dir: str = "desc",
        page: int = 1, page_size: int = 25,
    ) -> tuple[list[dict], int]:
        """Kembalikan (baris_halaman_ini, total_baris_cocok_filter)."""

    @abstractmethod
    def get_rules(self, rule_group: Optional[str] = None, min_lift: float = 0.0,
                  search: str = "", limit: Optional[int] = None) -> list[dict]:
        ...

    @abstractmethod
    def count(self, filters: Filters) -> int:
        ...
