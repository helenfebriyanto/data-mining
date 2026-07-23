"""
pages/rekomendasi.py - Rekomendasi Bisnis
Setiap rekomendasi terikat ke temuan nyata (segmen/pola/jenis anomali tertentu).
Filter wilayah pada halaman ini bukan sekadar pajangan - dipakai untuk menghitung
ULANG relevansi tiap rekomendasi (mis. "di wilayah ini, segmen terkait masih X%
high-risk"), jadi genuinely interaktif, bukan teks statis (slicer wajib per halaman).
"""
from __future__ import annotations

import dash
from dash import html, dcc, Input, Output, callback

import config as cfg
from app import BACKEND
from data_backend.base import Filters
from components.filter_bar import make_filter_bar, read_filters
from components.cards import kpi_row, section_header, recommendation_card, empty_state

dash.register_page(__name__, path="/rekomendasi", name="Rekomendasi", title="Rekomendasi Bisnis")

PAGE = "rekomendasi"
PRIORITY_ALL = "Semua prioritas"
PRIORITY_CHOICES = [PRIORITY_ALL, "Tinggi", "Sedang", "Rendah"]

layout = html.Div([
    html.Div([
        html.Div("BUSINESS RECOMMENDATIONS", className="page-hero-eyebrow"),
        html.H1("Rekomendasi Tindak Lanjut"),
        html.P(
            "Rekomendasi konkret, masing-masing terikat ke temuan nyata dari segmentasi, pola asosiasi, "
            "atau deteksi anomali - bukan saran generik. Gunakan filter wilayah untuk melihat apakah "
            "temuan yang mendasari tiap rekomendasi masih relevan pada irisan data tertentu."
        ),
    ], className="page-hero"),

    make_filter_bar(PAGE, wilayah=True, segmen=False, jenis=False),

    html.Div([
        html.Span("Prioritas:", className="chip-row-label"),
        html.Div(id=f"{PAGE}-priority-chips", className="chip-row"),
    ], className="chip-row-wrap"),

    html.Div(id=f"{PAGE}-kpi-container"),

    section_header("Daftar Rekomendasi", "Diurutkan berdasarkan prioritas. Bagian 'Relevansi saat ini' dihitung ulang mengikuti filter wilayah di atas."),
    html.Div(id=f"{PAGE}-rec-cards", className="recommendation-grid"),

    dcc.Store(id=f"{PAGE}-active-priority", data=PRIORITY_ALL),
], className="page-fade-in")


@callback(
    Output(f"{PAGE}-active-priority", "data"),
    Output(f"{PAGE}-priority-chips", "children"),
    Input({"type": f"{PAGE}-chip", "index": dash.ALL}, "n_clicks"),
    prevent_initial_call=False,
)
def _toggle_priority(_n_clicks):
    triggered = dash.ctx.triggered_id
    active = triggered["index"] if triggered else PRIORITY_ALL
    chips = [
        html.Button(p, id={"type": f"{PAGE}-chip", "index": p}, n_clicks=0,
                    className="chip" + (" chip-active" if p == active else ""))
        for p in PRIORITY_CHOICES
    ]
    return active, chips


@callback(
    Output(f"{PAGE}-kpi-container", "children"),
    Output(f"{PAGE}-rec-cards", "children"),
    Input(f"{PAGE}-active-priority", "data"),
    Input(f"{PAGE}-filter-wilayah", "value"),
)
def _update(active_priority, wilayah):
    recs = cfg.RECOMMENDATIONS
    if active_priority and active_priority != PRIORITY_ALL:
        recs = [r for r in recs if r["priority"] == active_priority]

    order = {"Tinggi": 0, "Sedang": 1, "Rendah": 2}
    recs = sorted(recs, key=lambda r: order.get(r["priority"], 9))

    n_tinggi = sum(1 for r in cfg.RECOMMENDATIONS if r["priority"] == "Tinggi")
    kpis = kpi_row([
        dict(label="Total Rekomendasi", value=str(len(cfg.RECOMMENDATIONS)), icon="✅", tone="brand"),
        dict(label="Prioritas Tinggi", value=str(n_tinggi), icon="🔴", tone="danger"),
        dict(label="Ditampilkan Saat Ini", value=str(len(recs)), icon="📋"),
    ])

    f_wilayah = Filters(wilayah=wilayah or [])
    cards = [_recommendation_card_with_relevance(r, f_wilayah) for r in recs] if recs else [
        empty_state("Tidak ada rekomendasi pada prioritas ini.")
    ]
    return kpis, cards


def _recommendation_card_with_relevance(rec: dict, f_wilayah: Filters) -> html.Div:
    card = recommendation_card(rec)
    relevance_text = None
    if rec.get("related_segment") is not None:
        seg_filter = Filters(wilayah=f_wilayah.wilayah, segmen=[rec["related_segment"]])
        rows = BACKEND.get_segment_summary(seg_filter)
        if rows:
            r = rows[0]
            relevance_text = (
                f"📍 Pada irisan data saat ini: Segmen {rec['related_segment']} = "
                f"{cfg.format_int(r['transactions'])} transaksi, {cfg.format_pct(r['high_risk_rate'], 2)} high-risk, "
                f"rata-rata skor {r['avg_risk_score']:.2f}".replace(".", ",") + "."
            )
    elif rec.get("related_anomaly_type"):
        rows = BACKEND.get_anomaly_type_summary(f_wilayah)
        match = next((r for r in rows if r["anomaly_type"] == rec["related_anomaly_type"]), None)
        if match:
            relevance_text = (
                f"📍 Pada irisan data saat ini: '{rec['related_anomaly_type']}' = "
                f"{cfg.format_int(match['transactions'])} transaksi ({match['percentage']:.2f}".replace(".", ",") + "% dari filter aktif)."
            )
    elif rec.get("related_rule_group"):
        n = len(BACKEND.get_rules(rule_group=rec["related_rule_group"]))
        relevance_text = f"📍 {n} pola termasuk kelompok '{rec['related_rule_group']}' tersedia di halaman Pola & Asosiasi."

    if relevance_text:
        card.children.append(html.Div(relevance_text, className="rec-relevance-live"))
    return card
