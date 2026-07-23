"""
components/cards.py
=====================
Komponen kartu yang dipakai berulang di berbagai halaman: KPI, kartu segmen,
kartu pola/aturan, kartu metode anomali, kartu rekomendasi.
"""
from __future__ import annotations

from dash import html, dcc

import config as cfg


def kpi_card(label: str, value: str, sublabel: str = "", tone: str = "default", icon: str = "") -> html.Div:
    return html.Div([
        html.Div([html.Span(icon, className="kpi-icon"), html.Span(label, className="kpi-label")], className="kpi-top"),
        html.Div(value, className="kpi-value"),
        html.Div(sublabel, className="kpi-sublabel") if sublabel else None,
    ], className=f"kpi-card kpi-tone-{tone}")


def kpi_row(items: list[dict]) -> html.Div:
    return html.Div([kpi_card(**item) for item in items], className="kpi-row")


def section_header(title: str, subtitle: str = "", right_element=None) -> html.Div:
    return html.Div([
        html.Div([
            html.H3(title, className="section-title"),
            html.P(subtitle, className="section-subtitle") if subtitle else None,
        ]),
        html.Div(right_element, className="section-header-right") if right_element is not None else None,
    ], className="section-header")


def segment_card(row: dict, selected: bool = False) -> html.Div:
    cid = int(row["cluster_kmeans"])
    name = cfg.SEGMENT_NAMES[cid]
    profile = cfg.SEGMENT_PROFILE[cid]
    value = cfg.SEGMENT_VALUE[cid]
    behavior = cfg.SEGMENT_BEHAVIOR[cid]
    icon = cfg.SEGMENT_ICON[cid]
    return html.Div([
        html.Div([
            html.Div(f"Segmen {cid}", className=f"segment-badge segment-badge-{cid}"),
            html.Div(f"{cfg.format_pct(row['population_share'], 3)} dari populasi", className="segment-share"),
        ], className="segment-card-top"),
        html.H4([icon + " ", name], className="segment-name"),
        html.Div([
            html.Span("PERILAKU UTAMA", className="behavior-tag"),
            html.P(behavior, className="behavior-text"),
        ], className="behavior-callout"),
        html.P(profile, className="segment-text"),
        html.Div([html.B("Nilai bisnis: "), value], className="segment-text segment-value-line"),
        html.Div([
            _mini_stat(cfg.format_int(row["transactions"]), "transaksi"),
            _mini_stat(cfg.format_pct(row["fraud_rate"], 3), "tingkat fraud"),
            _mini_stat(f"{row['avg_risk_score']:.2f}".replace(".", ","), "rata² skor risiko"),
            _mini_stat(cfg.format_pct(row["high_risk_rate"], 2), "tingkat high-risk"),
        ], className="segment-stats-grid"),
    ], id={"type": "segment-card", "index": cid}, n_clicks=0,
       className="segment-card" + (" segment-card-selected" if selected else ""))


def _mini_stat(value: str, label: str) -> html.Div:
    return html.Div([html.Div(value, className="mini-stat-value"), html.Div(label, className="mini-stat-label")],
                     className="mini-stat")


def rule_card(row: dict) -> html.Div:
    badge_class = {
        cfg.RULE_GROUP_FRAUD: "badge-danger", cfg.RULE_GROUP_SEGMENT: "badge-info",
        cfg.RULE_GROUP_OUTLIER: "badge-warning", cfg.RULE_GROUP_GENERAL: "badge-neutral",
    }.get(row["rule_group"], "badge-neutral")
    importance_class = "badge-important" if row.get("is_top10") else "badge-secondary"
    return html.Div([
        html.Div([
            html.Span(row["rule_group"], className=f"badge {badge_class}"),
            html.Span(row.get("penting", ""), className=f"badge {importance_class}"),
        ], className="rule-badges"),
        html.Div([
            html.Span("JIKA", className="rule-keyword rule-keyword-if"),
            html.P(row["when_text"], className="rule-clause"),
            html.Span("MAKA", className="rule-keyword rule-keyword-then"),
            html.P(row["then_text"], className="rule-clause"),
        ], className="rule-statement"),
        html.P(row["takeaway"], className="rule-takeaway"),
        html.Div([
            html.Span("💡 ", className="rec-icon"),
            html.Span(row["recommendation"], className="rec-text"),
        ], className="rule-recommendation"),
        html.Div([
            _mini_stat(row["coverage_fmt"], "coverage"),
            _mini_stat(row["confidence_fmt"], "confidence"),
            _mini_stat(row["lift_fmt"], "lift"),
        ], className="segment-stats-grid rule-stats-grid"),
    ], className="rule-card")


def anomaly_method_card(method: dict) -> html.Div:
    return html.Div([
        html.Div([
            html.Span(method["nama"], className="method-name"),
            html.Span(method["kategori"], className="badge badge-neutral"),
        ], className="method-top"),
        html.Div([
            html.Span("Bobot skor: ", className="method-meta-label"),
            html.Span(f"{method['bobot']}" if method["bobot"] else "0 (cross-check)", className="method-meta-value"),
        ]),
        html.Div([
            html.Span("Fitur yang dipakai: ", className="method-meta-label"),
            html.Span(", ".join(method["fitur"]), className="method-meta-value"),
        ]),
        html.P(method["deskripsi"], className="method-desc"),
    ], className="method-card")


def recommendation_card(rec: dict) -> html.Div:
    priority_class = {"Tinggi": "badge-danger", "Sedang": "badge-warning", "Rendah": "badge-info"}.get(rec["priority"], "badge-neutral")
    return html.Div([
        html.Div([
            html.Span(rec["priority"] + " prioritas", className=f"badge {priority_class}"),
            html.Span(rec["category"], className="badge badge-neutral"),
        ], className="rule-badges"),
        html.H4(rec["title"], className="rec-title"),
        html.P(rec["description"], className="segment-text"),
        html.Div([html.B("Berdasarkan: "), rec["evidence"]], className="rec-evidence"),
        html.Div(id={"type": "rec-relevance", "index": rec["id"]}, className="rec-relevance"),
    ], className="recommendation-card")


def info_banner(text: str, icon: str = "ℹ️", tone: str = "info") -> html.Div:
    return html.Div([html.Span(icon, className="info-banner-icon"), html.Span(text, className="info-banner-text")],
                     className=f"info-banner info-banner-{tone}")


def empty_state(message: str) -> html.Div:
    return html.Div([html.Div("🔍", className="empty-state-icon"), html.P(message, className="empty-state-text")],
                     className="empty-state")
