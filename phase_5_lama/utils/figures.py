import pandas as pd

import plotly.express as px
import plotly.graph_objects as go

from business_labels import CLUSTER_LABELS

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


def make_rules_lift(rules) -> go.Figure:
    df = pd.DataFrame(rules).copy()
    if df.empty:
        return empty_figure("No association rules available")
    df = df.head(10).copy()
    df["rule_short"] = [f"Rule {i+1}" for i in range(len(df))]
    fig = px.bar(df.sort_values("lift"), x="lift", y="rule_short", orientation="h", title="Top association rules by business uplift", hover_data=["When this is seen", "This usually comes with"])
    fig.update_xaxes(title="How many times more common than usual")
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
    }