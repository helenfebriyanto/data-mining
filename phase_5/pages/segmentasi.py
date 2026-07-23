"""
pages/segmentasi.py - Segmentasi Nasabah
Menjawab catatan dosen:
- "Customer segments ada yang ga keliatan di grafiknya" -> population_share_bar pakai skala log + label selalu tampil
- "di segment tambahin grafik biar interaktif ga teks doang" -> radar + landscape + risk bar, semua ikut ter-highlight saat kartu diklik
- "main behavior besarin lgi" -> behavior-callout (font besar, kotak menonjol)
- "karakteristik segmen" -> radar chart + rincian pada kartu
"""
from __future__ import annotations

import dash
from dash import html, dcc, Input, Output, State, callback, ALL, ctx

import config as cfg
from app import BACKEND
from components.filter_bar import make_filter_bar, read_filters
from components.cards import kpi_row, section_header, segment_card, info_banner
import components.charts as ch

dash.register_page(__name__, path="/segmentasi", name="Segmentasi Nasabah", title="Segmentasi Nasabah")

PAGE = "segmentasi"

layout = html.Div([
    html.Div([
        html.Div("CUSTOMER SEGMENTATION", className="page-hero-eyebrow"),
        html.H1("Segmentasi Nasabah & Transaksi"),
        html.P(
            "Hasil KMeans clustering membagi 6,3 juta transaksi menjadi 4 segmen dengan karakteristik berbeda. "
            "Klik salah satu kartu segmen untuk menyorotnya di seluruh grafik pada halaman ini."
        ),
    ], className="page-hero"),

    make_filter_bar(PAGE, wilayah=True, segmen=False, jenis=True),

    html.Div(id=f"{PAGE}-kpi-container"),

    section_header("Kartu Segmen", "Klik kartu untuk menyorot segmen tsb. di semua grafik di bawah."),
    html.Div(id=f"{PAGE}-segment-cards", className="segment-grid"),

    section_header("Semua Segmen Kelihatan — Skala Log", "Segmen 0 hanya 0,03% dari populasi; pada skala biasa batangnya nyaris tak terlihat."),
    html.Div([
        dcc.Graph(id=f"{PAGE}-population-bar", config={"displayModeBar": False}),
    ], className="chart-card"),

    section_header("Karakteristik Antar Segmen", "Perbandingan multi-metrik (dinormalisasi) supaya pola tiap segmen mudah dibaca sekilas."),
    html.Div([
        html.Div([
            html.Div("Radar karakteristik segmen", className="chart-card-title"),
            dcc.Graph(id=f"{PAGE}-radar", config={"displayModeBar": False}),
        ], className="chart-card"),
        html.Div([
            html.Div("Tingkat high-risk per segmen", className="chart-card-title"),
            dcc.Graph(id=f"{PAGE}-risk-bar", config={"displayModeBar": False}),
        ], className="chart-card"),
    ], className="grid-2-equal"),

    section_header("Peta Populasi vs. Risiko"),
    html.Div([dcc.Graph(id=f"{PAGE}-landscape", config={"displayModeBar": False})], className="chart-card"),

    section_header("Sebaran Wilayah Segmen Terpilih"),
    html.Div(id=f"{PAGE}-wilayah-note", className="chart-card-note"),
    html.Div([dcc.Graph(id=f"{PAGE}-wilayah-bar", config={"displayModeBar": False})], className="chart-card"),

    dcc.Store(id=f"{PAGE}-selected-segment", data=None),
], className="page-fade-in")


@callback(
    Output(f"{PAGE}-kpi-container", "children"),
    Output(f"{PAGE}-segment-cards", "children"),
    Output(f"{PAGE}-population-bar", "figure"),
    Output(f"{PAGE}-radar", "figure"),
    Output(f"{PAGE}-risk-bar", "figure"),
    Output(f"{PAGE}-landscape", "figure"),
    Output(f"{PAGE}-wilayah-bar", "figure"),
    Output(f"{PAGE}-wilayah-note", "children"),
    Input(f"{PAGE}-filter-wilayah", "value"),
    Input(f"{PAGE}-filter-jenis", "value"),
    Input(f"{PAGE}-selected-segment", "data"),
)
def _update(wilayah, jenis, selected):
    f = read_filters(PAGE, wilayah=wilayah, jenis=jenis)
    seg_rows = BACKEND.get_segment_summary(f)
    kpi = BACKEND.get_kpi(f)

    kpis = kpi_row([
        dict(label="Jumlah Segmen", value=str(len(seg_rows)), icon="🧩", tone="brand"),
        dict(label="Segmen Terkecil", value=f"{min(r['population_share'] for r in seg_rows)*100:.3f}%".replace(".", ",") if seg_rows else "—",
             icon="🔬", tone="warning", sublabel="tetap terlihat berkat skala log"),
        dict(label="Total Transaksi", value=cfg.format_int(kpi["total_transaksi"]), icon="📄"),
        dict(label="Segmen Ter-pilih", value=(cfg.SEGMENT_NAMES.get(selected, "Belum dipilih") if selected is not None else "Semua segmen"),
             icon="🎯", tone="success"),
    ])

    cards = [segment_card(row, selected=(selected is not None and int(row["cluster_kmeans"]) == int(selected)))
             for row in seg_rows] if seg_rows else [html.Div("Tidak ada data untuk filter ini.")]

    fig_pop = ch.population_share_bar(seg_rows, selected_segment=selected)
    fig_radar = ch.segment_radar(seg_rows, selected_segment=selected)
    fig_risk = ch.segment_risk_bar(seg_rows, selected_segment=selected)
    fig_landscape = ch.segment_landscape(seg_rows, selected_segment=selected)

    wilayah_filters = read_filters(PAGE, wilayah=wilayah, jenis=jenis, segmen=[selected] if selected is not None else [])
    wil_rows = BACKEND.get_wilayah_breakdown(wilayah_filters)
    fig_wilayah = ch.wilayah_bar(wil_rows)
    note = (f"Menampilkan sebaran wilayah untuk Segmen {selected} — {cfg.SEGMENT_NAMES.get(selected,'')}."
            if selected is not None else "Menampilkan sebaran wilayah untuk semua segmen (klik kartu di atas untuk fokus ke satu segmen).")

    return kpis, cards, fig_pop, fig_radar, fig_risk, fig_landscape, fig_wilayah, note


@callback(
    Output(f"{PAGE}-selected-segment", "data"),
    Input({"type": "segment-card", "index": ALL}, "n_clicks"),
    State(f"{PAGE}-selected-segment", "data"),
    prevent_initial_call=True,
)
def _toggle_segment(n_clicks_list, current):
    triggered = ctx.triggered_id
    if not triggered or not any(n_clicks_list):
        return current
    clicked_index = triggered["index"]
    return None if current == clicked_index else clicked_index
