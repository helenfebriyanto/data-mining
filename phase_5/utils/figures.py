import pandas as pd

import plotly.express as px
import plotly.graph_objects as go

from business_labels import CLUSTER_LABELS, humanize_item

RISK_ORDER = [
    "Normal",
    "Low",
    "Medium",
    "High",
    "Critical",
]

METHOD_LABELS = {
    "flag_IQR": "Large amount by range check",
    "flag_ZScore": "Statistically extreme amount",
    "flag_IsoForest": "Unusual behavior pattern",
    "flag_HDBSCAN": "Cluster outlier",
}

def chart_layout(fig: go.Figure, height: int = 360) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=20, r=20, t=42, b=20),
        template="plotly_white",
        font=dict(family="Inter, Arial, sans-serif", size=12),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend_title_text="",
    )
    return fig

def empty_figure(message: str = "No data available") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, x=0.5, y=0.5, showarrow=False, font=dict(size=14))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return chart_layout(fig)


def make_risk_distribution(risk_summary) -> go.Figure:
    df = pd.DataFrame(risk_summary).copy()
    if df.empty:
        return empty_figure()
    df["risk_level"] = pd.Categorical(df["risk_level"], categories=RISK_ORDER, ordered=True)
    df = df.sort_values("risk_level")
    fig = px.bar(df, x="risk_level", y="transactions", text="percentage", title="Risk queue size by business priority")
    fig.update_traces(texttemplate="%{text:.2f}%", textposition="outside", cliponaxis=False)
    fig.update_xaxes(title="Risk priority")
    fig.update_yaxes(title="Transactions")
    return chart_layout(fig)


def make_fraud_by_score(fraud_by_score) -> go.Figure:
    df = pd.DataFrame(fraud_by_score).copy()
    if df.empty:
        return empty_figure()
    df["fraud_rate_pct"] = pd.to_numeric(df["fraud_rate"], errors="coerce") * 100
    fig = go.Figure()
    fig.add_bar(x=df["risk_score"], y=df["transactions"], name="Transactions", yaxis="y")
    fig.add_scatter(x=df["risk_score"], y=df["fraud_rate_pct"], name="Fraud rate", mode="lines+markers", yaxis="y2")
    fig.update_layout(
        title="Fraud concentration by risk score",
        yaxis=dict(title="Transactions"),
        yaxis2=dict(title="Fraud rate (%)", overlaying="y", side="right"),
        xaxis=dict(title="Weighted risk score"),
    )
    return chart_layout(fig)


def make_cluster_size(cluster_summary) -> go.Figure:
    df = pd.DataFrame(cluster_summary).copy()
    if df.empty:
        return empty_figure()
    df["segment"] = df["cluster_kmeans"].map(CLUSTER_LABELS).fillna(df["cluster_kmeans"].astype(str))
    fig = px.bar(df, x="segment", y="transactions", title="Customer-transaction segments by size", hover_data=["fraud_rate", "high_risk_rate"])
    fig.update_xaxes(title="K-Means segment", tickangle=-25)
    fig.update_yaxes(title="Transactions")
    return chart_layout(fig, height=420)


def make_cluster_risk(cluster_summary) -> go.Figure:
    df = pd.DataFrame(cluster_summary).copy()
    if df.empty:
        return empty_figure()
    df["segment"] = df["cluster_kmeans"].map(CLUSTER_LABELS).fillna(df["cluster_kmeans"].astype(str))
    df["fraud_rate_pct"] = pd.to_numeric(df["fraud_rate"], errors="coerce") * 100
    df["high_risk_rate_pct"] = pd.to_numeric(df["high_risk_rate"], errors="coerce") * 100
    fig = go.Figure()
    fig.add_bar(x=df["segment"], y=df["fraud_rate_pct"], name="Confirmed fraud rate")
    fig.add_bar(x=df["segment"], y=df["high_risk_rate_pct"], name="High-risk queue rate")
    fig.update_layout(title="Risk concentration by segment", barmode="group", xaxis=dict(tickangle=-25), yaxis=dict(title="Rate (%)"))
    return chart_layout(fig, height=420)


def _short_rule_label(antecedents_str: str, consequents_str: str, max_len: int = 46) -> str:
    ants = [a.strip() for a in str(antecedents_str).split(",") if a.strip()]
    cons = [c.strip() for c in str(consequents_str).split(",") if c.strip()]
    ant_text = humanize_item(ants[0]) if ants else "?"
    if len(ants) > 1:
        ant_text += f" +{len(ants) - 1}"
    con_text = humanize_item(cons[0]) if cons else "?"
    if len(cons) > 1:
        con_text += f" +{len(cons) - 1}"
    label = f"{ant_text}  →  {con_text}"
    if len(label) > max_len:
        label = label[: max_len - 1] + "…"
    return label


def make_rules_lift(rules) -> go.Figure:
    df = pd.DataFrame(rules).copy()
    if df.empty:
        return empty_figure("No association rules available")
    df = df.head(10).copy()
    if "antecedents_str" not in df.columns and "antecedents" in df.columns:
        df["antecedents_str"] = df["antecedents"].astype(str)
    if "consequents_str" not in df.columns and "consequents" in df.columns:
        df["consequents_str"] = df["consequents"].astype(str)
    df["rule_short"] = [
        _short_rule_label(a, c) for a, c in zip(df["antecedents_str"], df["consequents_str"])
    ]
    hover_cols = [c for c in ["When this is seen", "This usually comes with", "Rule group"] if c in df.columns]
    fig = px.bar(
        df.sort_values("lift"),
        x="lift",
        y="rule_short",
        orientation="h",
        title="Top association rules by business uplift",
        hover_data=hover_cols,
    )
    fig.update_xaxes(title="How many times more common than pure chance")
    fig.update_yaxes(title="")
    return chart_layout(fig, height=430)


def make_investigation_mix(investigation_summary) -> go.Figure:
    df = pd.DataFrame(investigation_summary).copy()
    if df.empty:
        return empty_figure()
    fig = px.bar(df.sort_values("transactions"), x="transactions", y="investigation_category", orientation="h", text="percentage", title="Anomaly investigation categories")
    fig.update_traces(texttemplate="%{text:.2f}%", textposition="outside", cliponaxis=False)
    fig.update_xaxes(title="Transactions")
    fig.update_yaxes(title="")
    return chart_layout(fig, height=400)


def make_anomaly_type(anomaly_type_summary) -> go.Figure:
    df = pd.DataFrame(anomaly_type_summary).copy()
    if df.empty:
        return empty_figure()
    fig = px.bar(df.sort_values("transactions"), x="transactions", y="anomaly_type", orientation="h", text="percentage", title="What kind of anomaly was found?")
    fig.update_traces(texttemplate="%{text:.2f}%", textposition="outside", cliponaxis=False)
    fig.update_xaxes(title="Transactions")
    fig.update_yaxes(title="")
    return chart_layout(fig, height=400)


def make_method_overlap(method_overlap) -> go.Figure:
    df = pd.DataFrame(method_overlap).copy()
    if df.empty or "method" not in df.columns:
        return empty_figure()
    df = df.set_index("method")
    df = df.rename(index=METHOD_LABELS, columns=METHOD_LABELS)
    fig = px.imshow(
        df.astype(float),
        text_auto=".0f",
        aspect="auto",
        title="Where anomaly methods agree",
        labels=dict(x="Method", y="Method", color="Shared transactions"),
    )
    return chart_layout(fig, height=430)

def make_segment_landscape(cluster_summary) -> go.Figure:
    df = pd.DataFrame(cluster_summary).copy()
    if df.empty:
        return empty_figure()
    if "Segment" in df.columns:
        df["segment"] = df["Segment"]
    else:
        df["segment"] = df["cluster_kmeans"].map(CLUSTER_LABELS).fillna(df["cluster_kmeans"].astype(str))
    df["fraud_rate_pct"] = pd.to_numeric(df["fraud_rate"], errors="coerce") * 100
    df["avg_risk_score"] = pd.to_numeric(df.get("avg_risk_score", 0), errors="coerce").fillna(0.01).clip(lower=0.01)
    df["transactions"] = pd.to_numeric(df["transactions"], errors="coerce")
    fig = px.scatter(
        df,
        x="transactions",
        y="fraud_rate_pct",
        size="avg_risk_score",
        color="segment",
        size_max=55,
        log_x=True,
        title="Segment landscape: size vs. fraud rate (bubble size = average risk score)",
    )
    fig.update_traces(marker=dict(line=dict(width=1, color="white")))
    fig.update_xaxes(title="Segment size (transactions, log scale)")
    fig.update_yaxes(title="Confirmed fraud rate (%)")
    return chart_layout(fig, height=420)


def make_enrichment_comparison(fraud_validation_metrics) -> go.Figure:
    df = pd.DataFrame(fraud_validation_metrics).copy()
    if df.empty or "metric" not in df.columns:
        return empty_figure()
    lookup = dict(zip(df["metric"], df["value"]))
    overall = float(lookup.get("Overall Fraud Rate", 0) or 0) * 100
    flagged = float(lookup.get("High Risk Fraud Rate", 0) or 0) * 100
    comp = pd.DataFrame(
        {
            "group": ["All transactions (baseline)", "Transactions flagged for review"],
            "fraud_rate_pct": [overall, flagged],
        }
    )
    fig = px.bar(
        comp,
        x="group",
        y="fraud_rate_pct",
        text="fraud_rate_pct",
        title="Fraud is more common in transactions flagged for review",
        color="group",
        color_discrete_sequence=["#94a3b8", "#dc2626"],
    )
    fig.update_traces(texttemplate="%{text:.2f}%", textposition="outside", cliponaxis=False)
    fig.update_xaxes(title="")
    fig.update_yaxes(title="Confirmed fraud rate (%)")
    fig.update_layout(showlegend=False)
    return chart_layout(fig, height=340)


def build_figures(data):
    return {
        "risk_distribution": make_risk_distribution(data["risk_summary"]),
        "fraud_by_score": make_fraud_by_score(data["fraud_by_score"]),
        "cluster_size": make_cluster_size(data["cluster_summary"]),
        "cluster_risk": make_cluster_risk(data["cluster_summary"]),
        "rules_lift": make_rules_lift(data["rules"]),
        "investigation_mix": make_investigation_mix(data["investigation_summary"]),
        "anomaly_type": make_anomaly_type(data["anomaly_type_summary"]),
        "method_overlap": make_method_overlap(data["method_overlap"]),
        "segment_landscape": make_segment_landscape(data["cluster_summary"]),
        "enrichment_comparison": make_enrichment_comparison(data["fraud_validation_metrics"]),
    }