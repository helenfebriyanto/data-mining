"""
pages/pola.py - Pola & Aturan Asosiasi
Menjawab catatan dosen:
- "Association rules di translate jadi bahasa manusia (jika -> maka)" -> rule_card (JIKA/MAKA)
- "pattern recomendation tambain yang detail, di page pattern tambahin recomendation" -> field recommendation per pola
- "tampil 10 aja tapi yg lainnya tetap bisa di akses ... insight 10 aja" -> 10 pola utama (kartu besar)
  + tabel semua 135 pola (bisa dicari/difilter) dengan tag "Insight utama" / "Insight tambahan"
- "setiap page at least ada slicer nya" -> filter kelompok pola + pencarian + ambang lift
- "Text yang ditampilkan jangan sampai kepotong" -> rule-clause di CSS pakai white-space normal + word-wrap
"""
from __future__ import annotations

import dash
from dash import html, dcc, Input, Output, State, callback, dash_table

import config as cfg
from app import BACKEND
from components.filter_bar import make_filter_bar
from components.cards import kpi_row, section_header, rule_card, info_banner, empty_state
import components.charts as ch

dash.register_page(__name__, path="/pola", name="Pola & Asosiasi", title="Pola & Aturan Asosiasi")

PAGE = "pola"
GROUP_ALL = "Semua kelompok"
GROUP_CHOICES = [GROUP_ALL] + cfg.RULE_GROUP_ORDER

layout = html.Div([
    html.Div([
        html.Div("PATTERN MINING", className="page-hero-eyebrow"),
        html.H1("Pola & Aturan Asosiasi (Association Rules)"),
        html.P(
            "Kombinasi atribut transaksi yang paling sering muncul bersamaan, diterjemahkan ke kalimat "
            "JIKA → MAKA supaya mudah dibaca tanpa latar belakang statistik. 10 pola paling penting "
            "ditonjolkan sebagai kartu besar; seluruh 135 pola yang ditemukan tetap bisa diakses, dicari, "
            "dan difilter di bagian bawah halaman."
        ),
    ], className="page-hero"),

    make_filter_bar(PAGE, wilayah=False, segmen=False, jenis=False, search=True,
                     search_placeholder="Cari atribut pola, mis. 'fraud', 'saldo', 'segmen 2'..."),

    html.Div([
        html.Span("Kelompok pola:", className="chip-row-label"),
        html.Div(id=f"{PAGE}-group-chips", className="chip-row"),
    ], className="chip-row-wrap"),

    html.Div(id=f"{PAGE}-kpi-container"),

    section_header("10 Pola Utama", "Diseleksi dari 135 pola berdasarkan kekuatan bisnis (lift & confidence) - lihat detail metodologi di README."),
    html.Div(id=f"{PAGE}-top10-cards", className="rules-grid"),

    section_header("Kekuatan Pola Utama (Lift)", "Lift = seberapa kuat kombinasi ini dibanding kejadian kebetulan. Lift 10x berarti 10x lebih sering dari yang diharapkan acak."),
    html.Div([dcc.Graph(id=f"{PAGE}-lift-bar", config={"displayModeBar": False})], className="chart-card"),

    html.Div([
        html.Div([
            html.Div("Komposisi Kelompok Pola", className="chart-card-title"),
            dcc.Graph(id=f"{PAGE}-group-donut", config={"displayModeBar": False}),
        ], className="chart-card"),
        html.Div([
            html.Div("Mengapa hanya 10 yang ditonjolkan?", className="chart-card-title"),
            html.P(
                "Menampilkan seluruh 135 pola sekaligus sebagai kartu besar akan membanjiri halaman dan "
                "menyulitkan pengambilan keputusan cepat. 10 pola dengan kombinasi lift & relevansi bisnis "
                "tertinggi ditonjolkan di atas; pola lain tetap tersimpan dan dapat dicari/diurutkan pada "
                "tabel di bawah, ditandai 'Insight tambahan'.", className="segment-text",
            ),
        ], className="chart-card"),
    ], className="grid-2-equal"),

    section_header("Seluruh Pola yang Ditemukan", "Cari atau filter berdasarkan kelompok/pencarian di atas - urutan default: pola utama dahulu, lalu lift tertinggi."),
    html.Div(id=f"{PAGE}-all-rules-table-wrap"),

    dcc.Store(id=f"{PAGE}-active-group", data=GROUP_ALL),
], className="page-fade-in")


@callback(
    Output(f"{PAGE}-active-group", "data"),
    Output(f"{PAGE}-group-chips", "children"),
    Input({"type": f"{PAGE}-chip", "index": dash.ALL}, "n_clicks"),
    State(f"{PAGE}-active-group", "data"),
)
def _toggle_group(_n_clicks, current):
    triggered = dash.ctx.triggered_id
    active = triggered["index"] if triggered else (current or GROUP_ALL)
    chips = [
        html.Button(g, id={"type": f"{PAGE}-chip", "index": g}, n_clicks=0,
                    className="chip" + (" chip-active" if g == active else ""))
        for g in GROUP_CHOICES
    ]
    return active, chips


@callback(
    Output(f"{PAGE}-kpi-container", "children"),
    Output(f"{PAGE}-top10-cards", "children"),
    Output(f"{PAGE}-lift-bar", "figure"),
    Output(f"{PAGE}-group-donut", "figure"),
    Output(f"{PAGE}-all-rules-table-wrap", "children"),
    Input(f"{PAGE}-active-group", "data"),
    Input(f"{PAGE}-filter-search", "value"),
)
def _update(active_group, search):
    group_param = None if active_group in (None, GROUP_ALL) else active_group
    search = search or ""

    all_rules = BACKEND.get_rules(rule_group=group_param, search=search)
    top10 = [r for r in all_rules if r.get("is_top10")]
    all_for_chart = BACKEND.get_rules()  # tak difilter, utk donut komposisi keseluruhan yg stabil

    kpis = kpi_row([
        dict(label="Total Pola Ditemukan", value=str(len(all_for_chart)), icon="🔗", tone="brand"),
        dict(label="Pola Utama", value=str(len(BACKEND.get_rules(limit=10)) if not group_param else len(top10)),
             icon="⭐", tone="warning", sublabel="ditonjolkan sbg kartu besar"),
        dict(label="Cocok Filter Saat Ini", value=str(len(all_rules)), icon="🔎", tone="default"),
        dict(label="Lift Tertinggi", value=cfg.format_multiplier(max((r["lift"] for r in all_rules), default=0)),
             icon="📈", tone="success"),
    ])

    top10_cards = [rule_card(r) for r in (top10 or all_rules[:10])] if all_rules else [empty_state("Tidak ada pola yang cocok dengan pencarian/filter ini.")]
    fig_lift = ch.rules_lift_bar(top10 or all_rules, top_n=10)
    fig_donut = ch.rule_group_donut(all_for_chart)

    table_rows = [
        {
            "Status": r.get("penting", ""),
            "Kelompok": r["rule_group"],
            "JIKA": r["when_text"],
            "MAKA": r["then_text"],
            "Coverage": r["coverage_fmt"],
            "Confidence": r["confidence_fmt"],
            "Lift": r["lift_fmt"],
        }
        for r in all_rules
    ]
    table = html.Div(dash_table.DataTable(
        data=table_rows,
        columns=[{"name": c, "id": c} for c in ["Status", "Kelompok", "JIKA", "MAKA", "Coverage", "Confidence", "Lift"]],
        page_size=15,
        sort_action="native",
        filter_action="native",
        style_table={"overflowX": "auto"},
        style_cell={"fontFamily": "Inter, sans-serif", "fontSize": "13px", "padding": "10px 12px",
                    "textAlign": "left", "whiteSpace": "normal", "height": "auto", "maxWidth": "320px"},
        style_header={"backgroundColor": "#122A52", "color": "white", "fontWeight": "600", "textTransform": "uppercase", "fontSize": "11px"},
        style_data_conditional=[
            {"if": {"filter_query": '{Status} = "Insight utama"'}, "backgroundColor": "#FBEDD4"},
        ],
    ), className="fance-table") if table_rows else empty_state("Tidak ada pola yang cocok.")

    return kpis, top10_cards, fig_lift, fig_donut, table
