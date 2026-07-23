"""
components/filter_bar.py
==========================
Filter bar (slicer) yang konsisten di semua halaman - menjawab catatan dosen
"setiap page at least ada slicernya". Wilayah SELALU ada (dimensi spasial
ilustratif - lihat config.WILAYAH_DISCLOSURE) karena dataset tidak punya
atribut temporal untuk difilter.
"""
from __future__ import annotations

from dash import dcc, html

import config as cfg
from data_backend.base import Filters

SEGMENT_OPTIONS = [{"label": f"Segmen {i} — {cfg.SEGMENT_NAMES[i]}", "value": i} for i in range(4)]
JENIS_OPTIONS = [{"label": v, "value": k} for k, v in cfg.TRANSACTION_TYPE_LABELS.items()]
RISK_OPTIONS = [{"label": r, "value": r} for r in cfg.RISK_LEVELS]
WILAYAH_OPTIONS = [{"label": w, "value": w} for w in cfg.WILAYAH_LIST]
ANOMALY_TYPE_OPTIONS = [{"label": a, "value": a} for a in cfg.ANOMALY_TYPE_LABELS]
INVESTIGATION_OPTIONS = [{"label": a, "value": a} for a in cfg.INVESTIGATION_CATEGORY_LABELS]


def _dd(id_, options, placeholder, multi=True):
    return dcc.Dropdown(
        id=id_, options=options, multi=multi, placeholder=placeholder,
        className="fance-dropdown", clearable=True, persistence=False,
    )


def make_filter_bar(page_id: str, *, wilayah=True, segmen=True, jenis=True,
                     risk_level=False, anomaly_type=False, investigation_category=False,
                     search=False, search_placeholder="Cari...") -> html.Div:
    controls = []
    if wilayah:
        controls.append(html.Div([
            html.Label("Wilayah", className="filter-label"),
            _dd(f"{page_id}-filter-wilayah", WILAYAH_OPTIONS, "Semua wilayah"),
        ], className="filter-control"))
    if segmen:
        controls.append(html.Div([
            html.Label("Segmen", className="filter-label"),
            _dd(f"{page_id}-filter-segmen", SEGMENT_OPTIONS, "Semua segmen"),
        ], className="filter-control"))
    if jenis:
        controls.append(html.Div([
            html.Label("Jenis transaksi", className="filter-label"),
            _dd(f"{page_id}-filter-jenis", JENIS_OPTIONS, "Semua jenis"),
        ], className="filter-control"))
    if risk_level:
        controls.append(html.Div([
            html.Label("Level risiko", className="filter-label"),
            _dd(f"{page_id}-filter-risk", RISK_OPTIONS, "Semua level"),
        ], className="filter-control"))
    if anomaly_type:
        controls.append(html.Div([
            html.Label("Jenis anomali", className="filter-label"),
            _dd(f"{page_id}-filter-anomaly", ANOMALY_TYPE_OPTIONS, "Semua jenis"),
        ], className="filter-control filter-control-wide"))
    if investigation_category:
        controls.append(html.Div([
            html.Label("Kategori investigasi", className="filter-label"),
            _dd(f"{page_id}-filter-investigation", INVESTIGATION_OPTIONS, "Semua kategori"),
        ], className="filter-control filter-control-wide"))
    if search:
        controls.append(html.Div([
            html.Label("Cari", className="filter-label"),
            dcc.Input(id=f"{page_id}-filter-search", type="text", placeholder=search_placeholder,
                      className="fance-input", debounce=True),
        ], className="filter-control"))

    controls.append(html.Div([
        html.Label("\u00A0", className="filter-label"),
        html.Button("Reset filter", id=f"{page_id}-filter-reset", className="btn-reset", n_clicks=0),
    ], className="filter-control filter-control-reset"))

    return html.Div([
        html.Div("🔎 Filter data di halaman ini", className="filter-bar-title"),
        html.Div(controls, className="filter-bar-controls"),
        html.Div(id=f"{page_id}-filter-summary", className="filter-summary"),
    ], className="filter-bar", id=f"{page_id}-filter-bar")


def read_filters(page_id: str, wilayah=None, segmen=None, jenis=None, risk=None,
                  anomaly=None, investigation=None, search=None) -> Filters:
    """Bangun objek Filters dari nilai-nilai State/Input callback Dash."""
    return Filters(
        wilayah=wilayah or [], segmen=segmen or [], jenis_transaksi=jenis or [],
        risk_level=risk or [], anomaly_type=anomaly or [], investigation_category=investigation or [],
        search=search or "",
    )


def filter_summary_text(f: Filters, total_after: int, total_all: int) -> str:
    if f.is_empty():
        return f"Menampilkan semua {cfg.format_int(total_all)} transaksi (tidak ada filter aktif)."
    pct = (total_after / total_all * 100) if total_all else 0
    return (f"Menampilkan {cfg.format_int(total_after)} dari {cfg.format_int(total_all)} transaksi "
            f"({pct:.2f}%) sesuai filter aktif.".replace(".", ",", 1))
