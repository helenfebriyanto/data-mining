"""
components/charts.py
======================
Semua grafik di dashboard dibuat lewat fungsi-fungsi di sini supaya HOVER,
WARNA, dan FONT konsisten di semua halaman (catatan dosen: "yang di graph ada
yang di hover ada yang ga"). Setiap fungsi memanggil theme.apply_theme() di
akhir.

Prinsip "semua segmen harus kelihatan" (catatan dosen ke Kelompok Fance):
grafik populasi (population_share_bar) memakai skala LOG + label angka selalu
tampil di ujung bar, supaya segmen yang sangat kecil (mis. Segmen 0 = 0,03%)
tetap terlihat & terbaca, bukan hilang jadi garis setipis rambut.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

import config as cfg
from theme import COLORS, CATEGORICAL_SEQUENCE, RISK_COLOR_MAP, RISK_ORDER, segment_color, apply_theme, FONT_MONO


def _empty_figure(message: str = "Tidak ada data untuk filter/pencarian ini.") -> go.Figure:
    """Figure placeholder yang konsisten dgn tema, dipakai semua chart saat rows kosong
    (mis. hasil filter/pencarian tidak menemukan apa pun) - supaya tidak error/crash."""
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False, font=dict(size=13.5, color=COLORS["ink_faint"]),
                        xref="paper", yref="paper", x=0.5, y=0.5)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    apply_theme(fig, legend=False, height=240)
    return fig


def _segment_label(cid) -> str:
    try:
        return f"Segmen {int(cid)} — {cfg.SEGMENT_NAMES[int(cid)]}"
    except (KeyError, ValueError, TypeError):
        return str(cid)


def population_share_bar(rows: list[dict], selected_segment: int | None = None) -> go.Figure:
    if not rows:
        return _empty_figure()
    """Bar horizontal skala LOG + label persentase & jumlah SELALU tampil,
    supaya segmen sekecil apa pun tetap terlihat jelas (bukan cuma di hover)."""
    df = pd.DataFrame(rows).sort_values("cluster_kmeans")
    labels = [_segment_label(c) for c in df["cluster_kmeans"]]
    colors = [segment_color(c) for c in df["cluster_kmeans"]]
    if selected_segment is not None:
        colors = [c if int(seg) == int(selected_segment) else _fade(c) for c, seg in zip(colors, df["cluster_kmeans"])]

    text = [f"{cfg.format_int(t)} transaksi ({cfg.format_pct(s, 3)})"
            for t, s in zip(df["transactions"], df["population_share"])]

    fig = go.Figure(go.Bar(
        x=df["transactions"], y=labels, orientation="h",
        marker=dict(color=colors, line=dict(width=0)),
        text=text, textposition="outside", cliponaxis=False,
        customdata=np.stack([df["population_share"] * 100, df["fraud_rate"] * 100, df["high_risk_rate"] * 100], axis=-1),
        hovertemplate=(
            "<b>%{y}</b><br>Jumlah transaksi: %{x:,.0f}<br>Pangsa populasi: %{customdata[0]:.3f}%"
            "<br>Tingkat fraud: %{customdata[1]:.3f}%<br>Tingkat high-risk: %{customdata[2]:.2f}%<extra></extra>"
        ),
    ))
    fig.update_xaxes(type="log", title="Jumlah transaksi (skala log — supaya segmen kecil tetap terlihat)")
    fig.update_yaxes(title=None, autorange="reversed")
    apply_theme(fig, legend=False, height=280)
    fig.update_layout(margin=dict(l=10, r=90, t=20, b=45))
    return fig


def _fade(hex_color: str, alpha: float = 0.35) -> str:
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def segment_risk_bar(rows: list[dict], selected_segment: int | None = None) -> go.Figure:
    if not rows:
        return _empty_figure()
    df = pd.DataFrame(rows).sort_values("cluster_kmeans")
    labels = [_segment_label(c) for c in df["cluster_kmeans"]]
    colors = [segment_color(c) for c in df["cluster_kmeans"]]
    if selected_segment is not None:
        colors = [c if int(seg) == int(selected_segment) else _fade(c) for c, seg in zip(colors, df["cluster_kmeans"])]

    fig = go.Figure(go.Bar(
        x=labels, y=df["high_risk_rate"] * 100,
        marker=dict(color=colors),
        text=[f"{v:.1f}%".replace(".", ",") for v in df["high_risk_rate"] * 100],
        textposition="outside", cliponaxis=False,
        customdata=np.stack([df["avg_risk_score"], df["critical_count"]], axis=-1),
        hovertemplate=(
            "<b>%{x}</b><br>Tingkat transaksi high-risk: %{y:.2f}%<br>Rata-rata skor risiko: %{customdata[0]:.2f} / 6"
            "<br>Jumlah transaksi Kritis: %{customdata[1]:,.0f}<extra></extra>"
        ),
    ))
    fig.update_yaxes(title="% transaksi high-risk di segmen ini")
    fig.update_xaxes(title=None)
    apply_theme(fig, legend=False, height=280)
    return fig


def segment_radar(rows: list[dict], selected_segment: int | None = None) -> go.Figure:
    if not rows:
        return _empty_figure()
    """Radar perbandingan karakteristik antar segmen (dinormalisasi 0-1 per
    metrik) - menjawab catatan 'tambahkan grafik biar interaktif, bukan teks
    doang' pada bagian karakteristik segmen."""
    df = pd.DataFrame(rows).sort_values("cluster_kmeans")
    metrics = ["population_share", "fraud_rate", "avg_risk_score", "high_risk_rate"]
    metric_labels = ["Pangsa populasi", "Tingkat fraud", "Rata-rata skor risiko", "Tingkat high-risk"]
    norm = df[metrics].copy()
    for m in metrics:
        rng = norm[m].max() - norm[m].min()
        norm[m] = (norm[m] - norm[m].min()) / rng if rng > 0 else 0.5

    fig = go.Figure()
    for _, row in df.iterrows():
        cid = row["cluster_kmeans"]
        vals = norm.loc[row.name, metrics].tolist()
        vals.append(vals[0])
        is_dim = selected_segment is not None and int(cid) != int(selected_segment)
        fig.add_trace(go.Scatterpolar(
            r=vals, theta=metric_labels + [metric_labels[0]],
            name=_segment_label(cid), mode="lines+markers",
            line=dict(color=segment_color(cid), width=1 if is_dim else 3),
            opacity=0.25 if is_dim else 0.95,
            hovertemplate="<b>" + _segment_label(cid) + "</b><br>%{theta}: nilai relatif %{r:.2f}<extra></extra>",
        ))
    fig.update_layout(polar=dict(
        radialaxis=dict(visible=True, range=[0, 1], showticklabels=False, gridcolor=COLORS["border"]),
        angularaxis=dict(gridcolor=COLORS["border"]),
        bgcolor="rgba(0,0,0,0)",
    ))
    apply_theme(fig, legend=True, height=360)
    fig.update_layout(legend=dict(orientation="h", y=-0.15))
    return fig


def segment_landscape(rows: list[dict], selected_segment: int | None = None) -> go.Figure:
    if not rows:
        return _empty_figure()
    df = pd.DataFrame(rows).sort_values("cluster_kmeans")
    sizes = np.sqrt(df["transactions"].astype(float))
    sizes = 18 + 55 * (sizes - sizes.min()) / max(1e-9, (sizes.max() - sizes.min()))
    colors = [segment_color(c) for c in df["cluster_kmeans"]]
    if selected_segment is not None:
        colors = [c if int(seg) == int(selected_segment) else _fade(c, 0.4) for c, seg in zip(colors, df["cluster_kmeans"])]

    fig = go.Figure(go.Scatter(
        x=df["transactions"], y=df["avg_risk_score"], mode="markers+text",
        marker=dict(size=sizes, color=colors, line=dict(width=2, color=COLORS["surface"])),
        text=[f"Seg {c}" for c in df["cluster_kmeans"]], textposition="top center",
        customdata=np.stack([df["population_share"] * 100, df["fraud_rate"] * 100, df["high_risk_rate"] * 100], axis=-1),
        hovertemplate=(
            "<b>%{text}</b><br>Jumlah transaksi: %{x:,.0f} (%{customdata[0]:.3f}% populasi)"
            "<br>Rata-rata skor risiko: %{y:.2f} / 6<br>Tingkat fraud: %{customdata[1]:.3f}%"
            "<br>Tingkat high-risk: %{customdata[2]:.2f}%<extra></extra>"
        ),
    ))
    fig.update_xaxes(type="log", title="Jumlah transaksi (skala log)")
    fig.update_yaxes(title="Rata-rata skor risiko (0-6)")
    apply_theme(fig, legend=False, height=340)
    return fig


def risk_level_bar(rows: list[dict]) -> go.Figure:
    if not rows:
        return _empty_figure()
    df = pd.DataFrame(rows)
    df["risk_level"] = pd.Categorical(df["risk_level"], categories=RISK_ORDER, ordered=True)
    df = df.sort_values("risk_level")
    colors = [RISK_COLOR_MAP.get(r, COLORS["ink_faint"]) for r in df["risk_level"]]
    fig = go.Figure(go.Bar(
        x=df["risk_level"].astype(str), y=df["transactions"], marker=dict(color=colors),
        text=[f"{p:.2f}%".replace(".", ",") for p in df["percentage"]], textposition="outside", cliponaxis=False,
        hovertemplate="<b>Level %{x}</b><br>Jumlah transaksi: %{y:,.0f}<br>Persentase: %{text}<extra></extra>",
    ))
    fig.update_yaxes(title="Jumlah transaksi", type="log")
    fig.update_xaxes(title=None)
    apply_theme(fig, legend=False, height=300)
    return fig


def category_bar(rows: list[dict], cat_col: str, label_map: dict | None = None, color=None,
                  orientation: str = "h", height: int = 320) -> go.Figure:
    if not rows:
        return _empty_figure()
    df = pd.DataFrame(rows).sort_values("transactions", ascending=(orientation == "h"))
    labels = [label_map.get(v, v) if label_map else v for v in df[cat_col]]
    color = color or COLORS["brand"]
    text = [f"{cfg.format_int(t)} ({p:.2f}%)".replace(".", ",", 1) for t, p in zip(df["transactions"], df["percentage"])]
    if orientation == "h":
        fig = go.Figure(go.Bar(x=df["transactions"], y=labels, orientation="h", marker=dict(color=color),
                                text=text, textposition="outside", cliponaxis=False,
                                hovertemplate="<b>%{y}</b><br>Jumlah: %{x:,.0f}<extra></extra>"))
        fig.update_xaxes(title="Jumlah transaksi")
        fig.update_yaxes(title=None)
    else:
        fig = go.Figure(go.Bar(x=labels, y=df["transactions"], marker=dict(color=color),
                                text=text, textposition="outside", cliponaxis=False,
                                hovertemplate="<b>%{x}</b><br>Jumlah: %{y:,.0f}<extra></extra>"))
        fig.update_yaxes(title="Jumlah transaksi")
        fig.update_xaxes(title=None)
    apply_theme(fig, legend=False, height=height)
    return fig


def fraud_by_score_chart(rows: list[dict]) -> go.Figure:
    if not rows:
        return _empty_figure()
    """Dual-axis: batang = jumlah transaksi, garis = tingkat fraud. Menonjolkan
    temuan 'Sedang (skor 2) justru fraud rate-nya lebih tinggi dari Kritis'."""
    df = pd.DataFrame(rows).sort_values("risk_score")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["risk_score"], y=df["transactions"], name="Jumlah transaksi",
        marker=dict(color=COLORS["brand_soft"], line=dict(color=COLORS["brand"], width=1)),
        yaxis="y1",
        hovertemplate="Skor risiko %{x}<br>Jumlah transaksi: %{y:,.0f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=df["risk_score"], y=df["fraud_rate"] * 100, name="Tingkat fraud (%)", mode="lines+markers",
        line=dict(color=COLORS["danger"], width=3), marker=dict(size=9),
        yaxis="y2",
        hovertemplate="Skor risiko %{x}<br>Tingkat fraud: %{y:.2f}%<extra></extra>",
    ))
    fig.update_layout(
        xaxis=dict(title="Skor risiko (0 = normal, 6 = paling banyak indikator)", dtick=1),
        yaxis=dict(title="Jumlah transaksi", type="log"),
        yaxis2=dict(title="Tingkat fraud (%)", overlaying="y", side="right", showgrid=False),
    )
    apply_theme(fig, legend=True, height=340)
    return fig


def method_overlap_heatmap(matrix_rows: list[dict]) -> go.Figure:
    if not matrix_rows:
        return _empty_figure()
    methods = ["flag_IQR", "flag_ZScore", "flag_IsoForest", "flag_HDBSCAN"]
    short_labels = {"flag_IQR": "IQR", "flag_ZScore": "Z-Score", "flag_IsoForest": "Isolation Forest", "flag_HDBSCAN": "HDBSCAN"}
    z = [[row[m2] for m2 in methods] for row in matrix_rows]
    labels = [short_labels[m] for m in methods]
    fig = go.Figure(go.Heatmap(
        z=z, x=labels, y=labels, colorscale=[[0, COLORS["surface_sunken"]], [1, COLORS["brand"]]],
        text=[[cfg.format_int(v) for v in row] for row in z], texttemplate="%{text}",
        hovertemplate="%{y} ∩ %{x}<br>Jumlah transaksi: %{z:,.0f}<extra></extra>",
        showscale=False,
    ))
    apply_theme(fig, legend=False, height=320)
    fig.update_layout(margin=dict(l=110, r=20, t=20, b=90))
    return fig


def wilayah_bar(rows: list[dict], metric: str = "transactions") -> go.Figure:
    if not rows:
        return _empty_figure()
    df = pd.DataFrame(rows).sort_values(metric, ascending=True)
    if metric == "transactions":
        x = df["transactions"]; text = [f"{cfg.format_int(v)}" for v in df["transactions"]]
        xaxis_title = "Jumlah transaksi"
    else:
        x = df["fraud_rate"] * 100; text = [f"{v:.3f}%".replace(".", ",") for v in x]
        xaxis_title = "Tingkat fraud (%)"
    fig = go.Figure(go.Bar(
        x=x, y=df["wilayah"], orientation="h", marker=dict(color=COLORS["seg_1"]),
        text=text, textposition="outside", cliponaxis=False,
        customdata=np.stack([df["share"] * 100, df["high_risk_rate"] * 100, df["avg_risk_score"]], axis=-1),
        hovertemplate=(
            "<b>%{y}</b><br>Jumlah transaksi: " + ("%{x:,.0f}" if metric == "transactions" else "%{customdata[0]:.2f}% dari total")
            + "<br>Tingkat high-risk: %{customdata[1]:.2f}%<br>Rata-rata skor risiko: %{customdata[2]:.2f}<extra></extra>"
        ),
    ))
    fig.update_xaxes(title=xaxis_title)
    fig.update_yaxes(title=None)
    apply_theme(fig, legend=False, height=320)
    return fig


def rules_lift_bar(rules_rows: list[dict], top_n: int = 10) -> go.Figure:
    if not rules_rows:
        return _empty_figure()
    df = pd.DataFrame(rules_rows).head(top_n).iloc[::-1]
    labels = [f"{w} → {t}" for w, t in zip(df["when_text"], df["then_text"])]
    labels = [l if len(l) <= 55 else l[:52] + "..." for l in labels]
    fig = go.Figure(go.Bar(
        x=df["lift"], y=labels, orientation="h", marker=dict(color=COLORS["accent"]),
        text=[cfg.format_multiplier(v) for v in df["lift"]], textposition="outside", cliponaxis=False,
        customdata=np.stack([df["confidence"] * 100, df["support"] * 100], axis=-1),
        hovertemplate="%{y}<br>Lift: %{x:.1f}x<br>Confidence: %{customdata[0]:.1f}%<br>Coverage: %{customdata[1]:.3f}%<extra></extra>",
    ))
    fig.update_xaxes(title="Lift (seberapa kuat pola dibanding kebetulan)")
    fig.update_yaxes(title=None, automargin=True)
    apply_theme(fig, legend=False, height=max(280, 34 * len(df)))
    fig.update_layout(margin=dict(l=10, r=80, t=20, b=45))
    return fig


def rule_group_donut(rules_rows: list[dict]) -> go.Figure:
    if not rules_rows:
        return _empty_figure()
    df = pd.DataFrame(rules_rows)
    counts = df["rule_group"].value_counts().reindex(cfg.RULE_GROUP_ORDER).fillna(0)
    fig = go.Figure(go.Pie(
        labels=counts.index, values=counts.values, hole=0.55,
        marker=dict(colors=CATEGORICAL_SEQUENCE),
        hovertemplate="<b>%{label}</b><br>Jumlah pola: %{value}<br>%{percent}<extra></extra>",
        textinfo="value+percent",
    ))
    apply_theme(fig, legend=True, height=300)
    return fig
