"""
pages/anomali.py - Aktivitas Tidak Wajar (Deteksi Anomali)
Menjawab catatan dosen:
- "justifikasi kenapa pake anomali" -> section Justifikasi (config.ANOMALY_JUSTIFICATION), didukung
  angka nyata dari kajian tumpang-tindih metode.
- "fitur apa yang mrmbuat fitur flag" -> 5 kartu metode (anomaly_method_card) sebut fitur input persis.
- "Tampilkan tipe outlier (general, contextual, dll)" (relevan lintas kelompok) -> anomaly_type breakdown.
- "setiap page at least ada slicer nya" -> filter lengkap: wilayah, jenis, segmen, level risiko, jenis
  anomali, kategori investigasi, + pencarian.
- Konsistensi hover -> semua grafik lewat components/charts.py (satu template).
"""
from __future__ import annotations

import dash
from dash import html, dcc, Input, Output, callback, dash_table

import config as cfg
from theme import COLORS
from app import BACKEND
from data_backend.base import Filters
from components.filter_bar import make_filter_bar, read_filters, filter_summary_text
from components.cards import kpi_row, section_header, anomaly_method_card, info_banner, empty_state
import components.charts as ch

dash.register_page(__name__, path="/anomali", name="Aktivitas Tidak Wajar", title="Aktivitas Tidak Wajar")

PAGE = "anomali"

layout = html.Div([
    html.Div([
        html.Div("ANOMALY DETECTION", className="page-hero-eyebrow"),
        html.H1("Aktivitas Tidak Wajar (Deteksi Anomali)"),
        html.P(
            "Lima metode deteksi independen digabung menjadi satu skor risiko 0-6, lalu divalidasi "
            "terhadap label fraud historis. Skor tinggi bukan berarti 'pasti fraud' — ini adalah "
            "sinyal untuk memprioritaskan mana yang perlu ditinjau manusia lebih dulu."
        ),
    ], className="page-hero"),

    make_filter_bar(PAGE, wilayah=True, segmen=True, jenis=True, risk_level=True,
                    anomaly_type=True, investigation_category=True, search=True,
                    search_placeholder="Cari ID transaksi atau kata kunci (mis. 'hdbscan', 'saldo')"),

    html.Div(id=f"{PAGE}-kpi-container"),

    section_header("Mengapa Memakai 5 Metode Sekaligus?", "Justifikasi pendekatan multi-metode, bukan satu model tunggal."),
    info_banner(cfg.ANOMALY_JUSTIFICATION, icon="🧭", tone="info"),

    section_header("Apa Saja yang Membentuk Setiap Penanda (Flag)?", "Fitur input & bobot kontribusi tiap metode ke skor risiko akhir."),
    html.Div([anomaly_method_card(m) for m in cfg.ANOMALY_METHODS], className="method-grid"),

    section_header("Tumpang Tindih Antar Metode", "Sel gelap = kedua metode sering menandai transaksi yang SAMA. HDBSCAN paling banyak berdiri sendiri — buktinya di bawah."),
    html.Div([dcc.Graph(id=f"{PAGE}-overlap-heatmap", config={"displayModeBar": False})], className="chart-card"),

    section_header("Temuan Utama: Skor 'Sedang' vs 'Kritis'", "Distribusi jumlah transaksi (batang, skala log) & tingkat fraud (garis) per skor risiko."),
    html.Div([dcc.Graph(id=f"{PAGE}-score-chart", config={"displayModeBar": False})], className="chart-card"),
    html.Div(id=f"{PAGE}-score-callout"),

    html.Div([
        html.Div([
            html.Div("Distribusi Level Risiko", className="chart-card-title"),
            dcc.Graph(id=f"{PAGE}-risk-bar", config={"displayModeBar": False}),
        ], className="chart-card"),
        html.Div([
            html.Div("Jenis Anomali", className="chart-card-title"),
            html.Div("General/univariat, structural/klaster, hingga kombinasi banyak indikator.", className="chart-card-note"),
            dcc.Graph(id=f"{PAGE}-type-bar", config={"displayModeBar": False}),
        ], className="chart-card"),
    ], className="grid-2-equal"),

    html.Div([
        html.Div("Kategori Investigasi yang Disarankan", className="chart-card-title"),
        dcc.Graph(id=f"{PAGE}-investigation-bar", config={"displayModeBar": False}),
    ], className="chart-card"),

    section_header("Validasi Terhadap Label Fraud Historis", "Skor risiko divalidasi silang - bukan angka yang berdiri sendiri."),
    html.Div(id=f"{PAGE}-validation-kpi"),

    section_header("Jelajahi Transaksi Individual", "Cari & filter transaksi spesifik sesuai kombinasi filter di atas (mendukung pencarian ID atau kata kunci alasan anomali)."),
    html.Div(id=f"{PAGE}-tx-table-wrap"),
], className="page-fade-in")


@callback(
    Output(f"{PAGE}-kpi-container", "children"),
    Output(f"{PAGE}-overlap-heatmap", "figure"),
    Output(f"{PAGE}-score-chart", "figure"),
    Output(f"{PAGE}-score-callout", "children"),
    Output(f"{PAGE}-risk-bar", "figure"),
    Output(f"{PAGE}-type-bar", "figure"),
    Output(f"{PAGE}-investigation-bar", "figure"),
    Output(f"{PAGE}-validation-kpi", "children"),
    Output(f"{PAGE}-tx-table-wrap", "children"),
    Output(f"{PAGE}-filter-summary", "children"),
    Input(f"{PAGE}-filter-wilayah", "value"),
    Input(f"{PAGE}-filter-segmen", "value"),
    Input(f"{PAGE}-filter-jenis", "value"),
    Input(f"{PAGE}-filter-risk", "value"),
    Input(f"{PAGE}-filter-anomaly", "value"),
    Input(f"{PAGE}-filter-investigation", "value"),
    Input(f"{PAGE}-filter-search", "value"),
)
def _update(wilayah, segmen, jenis, risk, anomaly, investigation, search):
    f = read_filters(PAGE, wilayah=wilayah, segmen=segmen, jenis=jenis, risk=risk,
                      anomaly=anomaly, investigation=investigation, search=search)
    kpi = BACKEND.get_kpi(f)
    overlap = BACKEND.get_method_overlap(f)
    by_score = BACKEND.get_fraud_by_score(f)
    risk_rows = BACKEND.get_risk_summary(f)
    type_rows = BACKEND.get_anomaly_type_summary(f)
    inv_rows = BACKEND.get_investigation_summary(f)
    total_all = BACKEND.count(Filters())

    kpis = kpi_row([
        dict(label="Total Transaksi (filter aktif)", value=cfg.format_int(kpi["total_transaksi"]), icon="📄", tone="brand"),
        dict(label="Antrean High-Risk", value=cfg.format_int(kpi["total_high_risk"]), icon="🚨", tone="warning",
             sublabel=cfg.format_pct(kpi["high_risk_rate"], 2) + " dari filter aktif"),
        dict(label="Kritis", value=cfg.format_int(kpi["total_kritis"]), icon="🔴", tone="danger"),
        dict(label="Rata-rata Skor Risiko", value=f"{kpi['avg_risk_score']:.2f}".replace(".", ",") + " / 6", icon="📊"),
    ])

    fig_overlap = ch.method_overlap_heatmap(overlap)
    fig_score = ch.fraud_by_score_chart(by_score)

    score2 = next((r for r in by_score if r["risk_score"] == 2), None)
    score6 = next((r for r in by_score if r["risk_score"] == 6), None)
    if score2 and score6 and score2["transactions"] and score6["transactions"]:
        callout = info_banner(
            f"Perhatikan: transaksi berskor 2 ('Sedang') punya tingkat fraud {cfg.format_pct(score2['fraud_rate'], 2)} — "
            f"lebih tinggi dibanding skor 6 ('Kritis') yang 'hanya' {cfg.format_pct(score6['fraud_rate'], 2)}. "
            "Ini terjadi karena kombinasi flag tertentu (mis. HDBSCAN sendirian) otomatis masuk kategori "
            "high-risk meski skor totalnya sedang. Jangan urutkan prioritas investigasi murni berdasar skor tertinggi.",
            icon="⚡", tone="warning",
        )
    else:
        callout = None

    fig_risk = ch.risk_level_bar(risk_rows)
    fig_type = ch.category_bar(type_rows, "anomaly_type")
    fig_inv = ch.category_bar(inv_rows, "investigation_category", color=COLORS["info"])

    val_kpis = kpi_row([
        dict(label="Fraud Enrichment", value=(cfg.format_multiplier(kpi["fraud_enrichment"]) if kpi["fraud_enrichment"] else "—"),
             icon="🎯", tone="success", sublabel="lebih pekat dibanding baseline populasi"),
        dict(label="Tingkat Fraud di Antrean High-Risk", value=(cfg.format_pct(kpi["high_risk_fraud_rate"], 2) if kpi["high_risk_fraud_rate"] else "—"),
             icon="🔬", tone="danger"),
        dict(label="Tingkat Fraud Keseluruhan (filter ini)", value=cfg.format_pct(kpi["fraud_rate"], 3), icon="📉"),
    ])

    rows, total_match = BACKEND.search_transactions(f, sort_col="risk_score", sort_dir="desc", page=1, page_size=25)
    table = _build_table(rows) if rows else empty_state("Tidak ada transaksi yang cocok dengan kombinasi filter ini.")
    summary = filter_summary_text(f, total_match, total_all)

    return kpis, fig_overlap, fig_score, callout, fig_risk, fig_type, fig_inv, val_kpis, table, summary


def _build_table(rows):
    data = [{
        "ID Transaksi": r["transaction_id"],
        "Jenis": cfg.humanize_transaction_type(r["transaction_type"]),
        "Wilayah": r["wilayah"],
        "Segmen": int(r["cluster_kmeans"]),
        "Skor Risiko": r["risk_score"],
        "Level": r["risk_level"],
        "Jenis Anomali": r["anomaly_type"],
        "Alasan": r["anomaly_reason"],
        "Fraud?": "Ya" if r["isFraud"] else "Tidak",
    } for r in rows]
    return html.Div(dash_table.DataTable(
        data=data,
        columns=[{"name": c, "id": c} for c in data[0].keys()],
        page_size=25, sort_action="native",
        style_table={"overflowX": "auto"},
        style_cell={"fontFamily": "Inter, sans-serif", "fontSize": "12.5px", "padding": "9px 11px",
                    "textAlign": "left", "whiteSpace": "normal", "height": "auto", "maxWidth": "260px"},
        style_header={"backgroundColor": "#122A52", "color": "white", "fontWeight": "600", "textTransform": "uppercase", "fontSize": "10.5px"},
        style_data_conditional=[
            {"if": {"filter_query": '{Level} = "Kritis"'}, "backgroundColor": "#FBEAE8"},
            {"if": {"filter_query": '{Fraud?} = "Ya"'}, "borderLeft": "3px solid #C1483F"},
        ],
    ), className="fance-table")
