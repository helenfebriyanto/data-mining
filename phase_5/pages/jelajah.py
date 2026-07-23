"""
pages/jelajah.py - Jelajah Data
Halaman pamer utama utk kebutuhan "searching dan filtering interaktif" dan
target "<100ms walau 6,3 juta baris". Latensi query yang SESUNGGUHNYA diukur
tiap kali filter berubah dan ditampilkan langsung ke pengguna (bukan klaim di
atas kertas) - lihat badge performa di bawah filter bar.
"""
from __future__ import annotations

import time

import dash
from dash import html, dcc, Input, Output, State, callback, dash_table

import config as cfg
from app import BACKEND
from data_backend.base import Filters
from components.filter_bar import make_filter_bar, read_filters, filter_summary_text
from components.cards import kpi_row, section_header, info_banner, empty_state

dash.register_page(__name__, path="/jelajah", name="Jelajah Data", title="Jelajah Data")

PAGE = "jelajah"
PAGE_SIZE = 25

layout = html.Div([
    html.Div([
        html.Div("DATA EXPLORER", className="page-hero-eyebrow"),
        html.H1("Jelajah Data Transaksi"),
        html.P(
            "Cari dan saring transaksi individual dari seluruh 6,3 juta baris data - bukan hanya sampel. "
            "Ketik ID transaksi (mis. 'TX00010000'), kata kunci metode deteksi (mis. 'hdbscan', 'saldo'), "
            "atau kombinasikan dengan filter di samping."
        ),
    ], className="page-hero"),

    make_filter_bar(PAGE, wilayah=True, segmen=True, jenis=True, risk_level=True,
                    anomaly_type=True, investigation_category=True, search=True,
                    search_placeholder="Cari ID transaksi atau kata kunci..."),

    html.Div(id=f"{PAGE}-perf-badge"),
    html.Div(id=f"{PAGE}-kpi-container"),

    section_header("Hasil Pencarian", "Klik header kolom untuk mengurutkan. Gunakan tombol navigasi di bawah tabel untuk berpindah halaman."),
    html.Div(id=f"{PAGE}-table-wrap"),

    html.Div([
        html.Button("← Sebelumnya", id=f"{PAGE}-prev", n_clicks=0, className="btn-reset"),
        html.Span(id=f"{PAGE}-page-indicator", className="page-indicator"),
        html.Button("Berikutnya →", id=f"{PAGE}-next", n_clicks=0, className="btn-reset"),
    ], className="pagination-row"),

    dcc.Store(id=f"{PAGE}-page-num", data=1),
], className="page-fade-in")


@callback(
    Output(f"{PAGE}-page-num", "data"),
    Input(f"{PAGE}-prev", "n_clicks"),
    Input(f"{PAGE}-next", "n_clicks"),
    Input(f"{PAGE}-filter-wilayah", "value"),
    Input(f"{PAGE}-filter-segmen", "value"),
    Input(f"{PAGE}-filter-jenis", "value"),
    Input(f"{PAGE}-filter-risk", "value"),
    Input(f"{PAGE}-filter-anomaly", "value"),
    Input(f"{PAGE}-filter-investigation", "value"),
    Input(f"{PAGE}-filter-search", "value"),
    State(f"{PAGE}-page-num", "data"),
    prevent_initial_call=True,
)
def _change_page(prev_clicks, next_clicks, wilayah, segmen, jenis, risk, anomaly, investigation, search, current_page):
    triggered = dash.ctx.triggered_id
    if triggered == f"{PAGE}-prev":
        return max(1, (current_page or 1) - 1)
    if triggered == f"{PAGE}-next":
        return (current_page or 1) + 1
    return 1  # filter apa pun berubah -> kembali ke halaman 1


@callback(
    Output(f"{PAGE}-perf-badge", "children"),
    Output(f"{PAGE}-kpi-container", "children"),
    Output(f"{PAGE}-table-wrap", "children"),
    Output(f"{PAGE}-page-indicator", "children"),
    Output(f"{PAGE}-filter-summary", "children"),
    Input(f"{PAGE}-filter-wilayah", "value"),
    Input(f"{PAGE}-filter-segmen", "value"),
    Input(f"{PAGE}-filter-jenis", "value"),
    Input(f"{PAGE}-filter-risk", "value"),
    Input(f"{PAGE}-filter-anomaly", "value"),
    Input(f"{PAGE}-filter-investigation", "value"),
    Input(f"{PAGE}-filter-search", "value"),
    Input(f"{PAGE}-page-num", "data"),
)
def _update(wilayah, segmen, jenis, risk, anomaly, investigation, search, page_num):
    f = read_filters(PAGE, wilayah=wilayah, segmen=segmen, jenis=jenis, risk=risk,
                      anomaly=anomaly, investigation=investigation, search=search)
    page_num = page_num or 1

    t0 = time.perf_counter()
    rows, total_match = BACKEND.search_transactions(f, sort_col="risk_score", sort_dir="desc",
                                                     page=page_num, page_size=PAGE_SIZE)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    total_all = BACKEND.count(Filters())

    tone = "success" if elapsed_ms < 100 else "warning"
    perf_badge = info_banner(
        f"⚡ Query ini selesai dalam {elapsed_ms:.1f} ms (backend: {BACKEND.name.upper()}) — "
        + ("memenuhi target <100ms." if elapsed_ms < 100 else
           "di atas target <100ms untuk kombinasi filter ini (pencarian teks bebas lebih berat di mode DuckDB; "
           "nyalakan Elasticsearch untuk performa konsisten <100ms pada pencarian bebas, lihat README)."),
        icon="⚡", tone=("info" if tone == "success" else "warning"),
    )

    kpis = kpi_row([
        dict(label="Cocok Filter Saat Ini", value=cfg.format_int(total_match) if total_match < 50001 else "50.000+",
             icon="🔎", tone="brand"),
        dict(label="Total Seluruh Data", value=cfg.format_int(total_all), icon="🗄️"),
        dict(label="Halaman", value=str(page_num), icon="📄", sublabel=f"{PAGE_SIZE} baris/halaman"),
    ])

    table = _build_table(rows) if rows else empty_state("Tidak ada transaksi yang cocok dengan pencarian/filter ini.")
    max_page = max(1, -(-min(total_match, 50000) // PAGE_SIZE))
    indicator = f"Halaman {page_num} dari ~{max_page}"
    summary = filter_summary_text(f, total_match, total_all)

    return perf_badge, kpis, table, indicator, summary


def _build_table(rows):
    data = [{
        "ID Transaksi": r["transaction_id"],
        "Jenis": cfg.humanize_transaction_type(r["transaction_type"]),
        "Waktu Simulasi": cfg.day_from_step(r["step"]),
        "Wilayah": r["wilayah"],
        "Segmen": int(r["cluster_kmeans"]),
        "Skor Risiko": r["risk_score"],
        "Level": r["risk_level"],
        "Kategori Investigasi": r["investigation_category"],
        "Fraud?": "Ya" if r["isFraud"] else "Tidak",
    } for r in rows]
    return html.Div(dash_table.DataTable(
        data=data,
        columns=[{"name": c, "id": c} for c in data[0].keys()],
        page_action="none",
        sort_action="native",
        style_table={"overflowX": "auto"},
        style_cell={"fontFamily": "Inter, sans-serif", "fontSize": "12.5px", "padding": "9px 11px",
                    "textAlign": "left", "whiteSpace": "normal", "height": "auto"},
        style_header={"backgroundColor": "#122A52", "color": "white", "fontWeight": "600", "textTransform": "uppercase", "fontSize": "10.5px"},
        style_data_conditional=[
            {"if": {"filter_query": '{Level} = "Kritis"'}, "backgroundColor": "#FBEAE8"},
            {"if": {"filter_query": '{Fraud?} = "Ya"'}, "borderLeft": "3px solid #C1483F"},
        ],
    ), className="fance-table")
