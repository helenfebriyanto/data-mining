"""
pages/ringkasan.py - Ringkasan Eksekutif (halaman utama, path "/")
"""
from __future__ import annotations

import dash
from dash import html, dcc, Input, Output, callback

import config as cfg
from app import BACKEND
from data_backend.base import Filters
from components.filter_bar import make_filter_bar, read_filters, filter_summary_text
from components.cards import kpi_row, section_header, info_banner
import components.charts as ch

dash.register_page(__name__, path="/", name="Ringkasan Eksekutif", title="Ringkasan Eksekutif")

PAGE = "ringkasan"

layout = html.Div([
    html.Div([
        html.Div("EXECUTIVE SUMMARY", className="page-hero-eyebrow"),
        html.H1("Ringkasan Deteksi Fraud & Risiko Transaksi"),
        html.P(
            "Gambaran menyeluruh hasil analisis 6,3 juta transaksi perbankan: seberapa besar risiko fraud "
            "yang ditemukan, di segmen mana risiko itu terkonsentrasi, dan seberapa efektif model deteksi "
            "dibanding hanya mengandalkan label fraud historis."
        ),
    ], className="page-hero"),

    make_filter_bar(PAGE, wilayah=True, segmen=True, jenis=True),

    html.Div(id=f"{PAGE}-kpi-container"),
    html.Div(id=f"{PAGE}-insight-banner"),

    section_header("Risiko per Segmen Nasabah", "Segmen dengan tingkat high-risk tertinggi patut jadi prioritas pemantauan."),
    html.Div([
        html.Div([
            html.Div("Populasi vs. rata-rata skor risiko per segmen", className="chart-card-title"),
            html.Div("Ukuran lingkaran = jumlah transaksi. Detail lengkap ada di halaman Segmentasi Nasabah.", className="chart-card-note"),
            dcc.Graph(id=f"{PAGE}-segment-landscape", config={"displayModeBar": False}),
        ], className="chart-card"),
        html.Div([
            html.Div("Distribusi level risiko", className="chart-card-title"),
            html.Div("Skala log pada sumbu Y supaya kelompok kecil tetap terlihat.", className="chart-card-note"),
            dcc.Graph(id=f"{PAGE}-risk-bar", config={"displayModeBar": False}),
        ], className="chart-card"),
    ], className="grid-2"),

    section_header("Sebaran Wilayah", "Filter spasial: dataset PaySim tidak memiliki atribut geografis asli — lihat catatan di footer halaman."),
    html.Div([
        html.Div("Jumlah transaksi per wilayah", className="chart-card-title"),
        dcc.Graph(id=f"{PAGE}-wilayah-bar", config={"displayModeBar": False}),
    ], className="chart-card"),

    section_header("Ringkasan Setiap Bagian Analisis"),
    html.Div(id=f"{PAGE}-nav-summary", className="grid-2-equal"),
], className="page-fade-in")


@callback(
    Output(f"{PAGE}-kpi-container", "children"),
    Output(f"{PAGE}-insight-banner", "children"),
    Output(f"{PAGE}-segment-landscape", "figure"),
    Output(f"{PAGE}-risk-bar", "figure"),
    Output(f"{PAGE}-wilayah-bar", "figure"),
    Output(f"{PAGE}-nav-summary", "children"),
    Input(f"{PAGE}-filter-wilayah", "value"),
    Input(f"{PAGE}-filter-segmen", "value"),
    Input(f"{PAGE}-filter-jenis", "value"),
)
def _update(wilayah, segmen, jenis):
    f = read_filters(PAGE, wilayah=wilayah, segmen=segmen, jenis=jenis)
    kpi = BACKEND.get_kpi(f)
    seg_rows = BACKEND.get_segment_summary(f)
    risk_rows = BACKEND.get_risk_summary(f)
    wilayah_rows = BACKEND.get_wilayah_breakdown(f)

    kpis = kpi_row([
        dict(label="Total Transaksi", value=cfg.format_int(kpi["total_transaksi"]), icon="📄", tone="brand",
             sublabel="sesuai filter aktif"),
        dict(label="Fraud Terkonfirmasi", value=cfg.format_int(kpi["total_fraud"]), icon="🚩", tone="danger",
             sublabel=f"tingkat fraud {cfg.format_pct(kpi['fraud_rate'], 3)}"),
        dict(label="Antrean High-Risk", value=cfg.format_int(kpi["total_high_risk"]), icon="🔎", tone="warning",
             sublabel=f"{cfg.format_pct(kpi['high_risk_rate'], 2)} dari total transaksi"),
        dict(label="Rata-rata Skor Risiko", value=f"{kpi['avg_risk_score']:.2f}".replace(".", ",") + " / 6", icon="📈",
             tone="default", sublabel="skor gabungan 4 metode deteksi"),
        dict(label="Fraud Enrichment", value=(cfg.format_multiplier(kpi["fraud_enrichment"]) if kpi["fraud_enrichment"] else "—"),
             icon="🎯", tone="success", sublabel="lebih pekat fraud di antrean high-risk vs baseline"),
    ])

    if kpi["total_high_risk"] and kpi["fraud_enrichment"]:
        banner = info_banner(
            f"Dengan memfokuskan investigasi ke {cfg.format_int(kpi['total_high_risk'])} transaksi berstatus "
            f"high-risk (bukan menyisir seluruh {cfg.format_int(kpi['total_transaksi'])} transaksi), tim investigasi "
            f"berpotensi menemukan fraud dengan konsentrasi {cfg.format_multiplier(kpi['fraud_enrichment'])} lebih "
            f"tinggi dibanding baseline populasi. Ini melengkapi label fraud historis yang tidak akan pernah bisa "
            f"menangkap pola yang belum pernah dilabeli sebelumnya.",
            icon="💡", tone="info",
        )
    else:
        banner = info_banner("Tidak ada transaksi high-risk pada kombinasi filter ini.", icon="ℹ️", tone="info")

    fig_landscape = ch.segment_landscape(seg_rows) if seg_rows else ch.segment_landscape([])
    fig_risk = ch.risk_level_bar(risk_rows) if risk_rows else ch.risk_level_bar([])
    fig_wilayah = ch.wilayah_bar(wilayah_rows) if wilayah_rows else ch.wilayah_bar([])

    nav_cards = []
    nav_info = [
        ("/segmentasi", "🧩 Segmentasi Nasabah", f"{len(seg_rows)} segmen ditemukan, dari transaksi bernilai "
         "eksepsional (0,03% populasi, 79% high-risk) hingga populasi harian utama."),
        ("/pola", "🔗 Pola & Asosiasi", "10 pola utama (dari 135+ pola yang tersedia) menjelaskan kombinasi atribut "
         "yang paling sering muncul bersamaan, termasuk pola yang mengarah langsung ke fraud."),
        ("/anomali", "🚨 Aktivitas Tidak Wajar", "5 metode deteksi independen digabung jadi satu skor risiko 0-6, "
         "divalidasi terhadap label fraud historis."),
        ("/rekomendasi", "✅ Rekomendasi", "Tindakan konkret berbasis temuan segmentasi, pola, dan anomali."),
    ]
    for path, title, desc in nav_info:
        nav_cards.append(html.Div([
            dcc.Link(html.H4(title, className="rec-title"), href=path),
            html.P(desc, className="segment-text"),
            dcc.Link("Lihat detail →", href=path, className="chip"),
        ], className="chart-card"))

    return kpis, banner, fig_landscape, fig_risk, fig_wilayah, nav_cards
