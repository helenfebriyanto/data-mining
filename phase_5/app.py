from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, dcc, html, dash_table, no_update

import fallback_data

BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = Path(os.environ.get("DASHBOARD_CACHE_DIR", BASE_DIR / "cache"))

RISK_ORDER = ["Normal", "Low", "Medium", "High", "Critical"]

METHOD_LABELS = {
    "flag_IQR": "Large amount by range check",
    "flag_ZScore": "Statistically extreme amount",
    "flag_IsoForest": "Unusual behavior pattern",
    "flag_HDBSCAN": "Cluster outlier",
}

from business_labels import CLUSTER_LABELS, add_rule_business_columns


def read_parquet_or_csv(stem: str, fallback_func) -> pd.DataFrame:
    parquet_path = CACHE_DIR / f"{stem}.parquet"
    csv_path = CACHE_DIR / f"{stem}.csv"
    if parquet_path.exists():
        return pd.read_parquet(parquet_path)
    if csv_path.exists():
        return pd.read_csv(csv_path)
    return fallback_func()


def normalize_percentage(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "percentage" in df.columns:
        df["percentage"] = pd.to_numeric(df["percentage"], errors="coerce")
        if df["percentage"].max(skipna=True) <= 1.0:
            df["percentage"] = df["percentage"] * 100
    return df


def pct(value: Any, decimals: int = 2) -> str:
    try:
        value_float = float(value)
    except Exception:
        return "—"
    return f"{value_float * 100:.{decimals}f}%"


def pct_from_percent(value: Any, decimals: int = 2) -> str:
    try:
        value_float = float(value)
    except Exception:
        return "—"
    return f"{value_float:.{decimals}f}%"


def num(value: Any) -> str:
    try:
        return f"{int(round(float(value))):,}"
    except Exception:
        return "—"


def small_num(value: Any, decimals: int = 2) -> str:
    try:
        value_float = float(value)
    except Exception:
        return "—"
    return f"{value_float:,.{decimals}f}"



def load_data() -> dict[str, pd.DataFrame | dict[str, Any] | list[dict[str, str]] | bool]:
    using_cache = any(CACHE_DIR.glob("*.parquet")) or any(CACHE_DIR.glob("*.csv"))
    data: dict[str, Any] = {
        "using_cache": using_cache,
        "risk_summary": normalize_percentage(read_parquet_or_csv("risk_summary", fallback_data.risk_summary)),
        "anomaly_type_summary": normalize_percentage(read_parquet_or_csv("anomaly_type_summary", fallback_data.anomaly_type_summary)),
        "investigation_summary": normalize_percentage(read_parquet_or_csv("investigation_summary", fallback_data.investigation_summary)),
        "fraud_by_score": read_parquet_or_csv("fraud_by_score", fallback_data.fraud_by_score),
        "method_overlap": read_parquet_or_csv("method_overlap", fallback_data.method_overlap),
        "fraud_validation_metrics": read_parquet_or_csv("fraud_validation_metrics", fallback_data.fraud_validation_metrics),
        "cluster_summary": read_parquet_or_csv("cluster_summary", fallback_data.cluster_summary),
        "rules": read_parquet_or_csv("top_rules_business", fallback_data.rules),
        "top_suspicious": read_parquet_or_csv("top_suspicious_light", fallback_data.top_suspicious),
        "data_quality_findings": fallback_data.data_quality_findings(),
    }
    data["rules"] = add_rule_business_columns(pd.DataFrame(data["rules"]))
    return data


DATA = load_data()


def metric_value(metric: str, default: float | int = 0) -> float:
    df = pd.DataFrame(DATA["fraud_validation_metrics"])
    if df.empty or "metric" not in df.columns or "value" not in df.columns:
        return float(default)
    rows = df.loc[df["metric"].astype(str) == metric, "value"]
    if rows.empty:
        return float(default)
    return float(rows.iloc[0])


def derive_total_transactions() -> int:
    risk_df = pd.DataFrame(DATA["risk_summary"])
    if "transactions" in risk_df.columns and len(risk_df):
        return int(pd.to_numeric(risk_df["transactions"], errors="coerce").fillna(0).sum())
    return fallback_data.TOTAL_TRANSACTIONS


def high_critical_transactions() -> int:
    risk_df = pd.DataFrame(DATA["risk_summary"])
    if risk_df.empty:
        return 0
    return int(risk_df.loc[risk_df["risk_level"].isin(["High", "Critical"]), "transactions"].sum())


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


def make_risk_distribution() -> go.Figure:
    df = pd.DataFrame(DATA["risk_summary"]).copy()
    if df.empty:
        return empty_figure()
    df["risk_level"] = pd.Categorical(df["risk_level"], categories=RISK_ORDER, ordered=True)
    df = df.sort_values("risk_level")
    fig = px.bar(df, x="risk_level", y="transactions", text="percentage", title="Risk queue size by business priority")
    fig.update_traces(texttemplate="%{text:.2f}%", textposition="outside", cliponaxis=False)
    fig.update_xaxes(title="Risk priority")
    fig.update_yaxes(title="Transactions")
    return chart_layout(fig)


def make_fraud_by_score() -> go.Figure:
    df = pd.DataFrame(DATA["fraud_by_score"]).copy()
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


def make_cluster_size() -> go.Figure:
    df = pd.DataFrame(DATA["cluster_summary"]).copy()
    if df.empty:
        return empty_figure()
    df["segment"] = df["cluster_kmeans"].map(CLUSTER_LABELS).fillna(df["cluster_kmeans"].astype(str))
    fig = px.bar(df, x="segment", y="transactions", title="Customer-transaction segments by size", hover_data=["fraud_rate", "high_risk_rate"])
    fig.update_xaxes(title="K-Means segment", tickangle=-25)
    fig.update_yaxes(title="Transactions")
    return chart_layout(fig, height=420)


def make_cluster_risk() -> go.Figure:
    df = pd.DataFrame(DATA["cluster_summary"]).copy()
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


def make_rules_lift() -> go.Figure:
    df = pd.DataFrame(DATA["rules"]).copy()
    if df.empty:
        return empty_figure("No association rules available")
    df = df.head(10).copy()
    df["rule_short"] = [f"Rule {i+1}" for i in range(len(df))]
    fig = px.bar(df.sort_values("lift"), x="lift", y="rule_short", orientation="h", title="Top association rules by business uplift", hover_data=["When this is seen", "This usually comes with"])
    fig.update_xaxes(title="How many times more common than usual")
    fig.update_yaxes(title="")
    return chart_layout(fig, height=430)


def make_investigation_mix() -> go.Figure:
    df = pd.DataFrame(DATA["investigation_summary"]).copy()
    if df.empty:
        return empty_figure()
    fig = px.bar(df.sort_values("transactions"), x="transactions", y="investigation_category", orientation="h", text="percentage", title="Anomaly investigation categories")
    fig.update_traces(texttemplate="%{text:.2f}%", textposition="outside", cliponaxis=False)
    fig.update_xaxes(title="Transactions")
    fig.update_yaxes(title="")
    return chart_layout(fig, height=400)


def make_anomaly_type() -> go.Figure:
    df = pd.DataFrame(DATA["anomaly_type_summary"]).copy()
    if df.empty:
        return empty_figure()
    fig = px.bar(df.sort_values("transactions"), x="transactions", y="anomaly_type", orientation="h", text="percentage", title="What kind of anomaly was found?")
    fig.update_traces(texttemplate="%{text:.2f}%", textposition="outside", cliponaxis=False)
    fig.update_xaxes(title="Transactions")
    fig.update_yaxes(title="")
    return chart_layout(fig, height=400)


def make_method_overlap() -> go.Figure:
    df = pd.DataFrame(DATA["method_overlap"]).copy()
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


FIGURES = {
    "risk_distribution": make_risk_distribution(),
    "fraud_by_score": make_fraud_by_score(),
    "cluster_size": make_cluster_size(),
    "cluster_risk": make_cluster_risk(),
    "rules_lift": make_rules_lift(),
    "investigation_mix": make_investigation_mix(),
    "anomaly_type": make_anomaly_type(),
    "method_overlap": make_method_overlap(),
}


def kpi_card(title: str, value: str, caption: str) -> html.Div:
    return html.Div(
        className="kpi-card",
        children=[
            html.Div(title, className="kpi-title"),
            html.Div(value, className="kpi-value"),
            html.Div(caption, className="kpi-caption"),
        ],
    )


def insight_card(title: str, body: str) -> html.Div:
    return html.Div(className="insight-card", children=[html.H4(title), html.P(body)])


def source_badge() -> html.Div:
    if DATA["using_cache"]:
        text = "Data source: dashboard cache generated from local parquet/CSV outputs."
        cls = "source-badge ok"
    else:
        text = "Data source: fallback notebook summaries. Run build_dashboard_cache.py for final local data."
        cls = "source-badge warn"
    return html.Div(text, className=cls)


def overview_tab() -> html.Div:
    total = derive_total_transactions()
    high_critical = high_critical_transactions()
    fraud_rate = metric_value("Overall Fraud Rate")
    high_risk_fraud_rate = metric_value("High Risk Fraud Rate")
    enrichment = metric_value("Fraud Enrichment")
    critical = int(pd.DataFrame(DATA["risk_summary"]).query("risk_level == 'Critical'")["transactions"].sum())

    return html.Div(
        className="tab-body",
        children=[
            html.Div(
                className="kpi-grid",
                children=[
                    kpi_card("Total transactions", num(total), "Cleaned analysis-ready records after Phase 1."),
                    kpi_card("Overall fraud rate", pct(fraud_rate, 3), "Fraud is rare, so detection should be treated as prioritization."),
                    kpi_card("High + critical queue", num(high_critical), "Transactions recommended for review, not automatic fraud decisions."),
                    kpi_card("Critical queue", num(critical), "Smallest and most urgent investigation group."),
                    kpi_card("Fraud rate in high-risk queue", pct(high_risk_fraud_rate, 2), "Fraud concentration inside the high-risk group."),
                    kpi_card("Fraud enrichment", f"{enrichment:,.1f}x", "How much richer the queue is versus the baseline fraud rate."),
                ],
            ),
            html.Div(
                className="two-col",
                children=[
                    dcc.Graph(figure=FIGURES["risk_distribution"], config={"displayModeBar": False}),
                    dcc.Graph(figure=FIGURES["fraud_by_score"], config={"displayModeBar": False}),
                ],
            ),
            html.Div(
                className="insight-grid",
                children=[
                    insight_card(
                        "Central discovery",
                        "Fraud is not spread evenly across transaction behavior. It concentrates in specific patterns: account-draining behavior, structural outliers, high-balance cash-in segments, and high-risk anomaly combinations.",
                    ),
                    insight_card(
                        "Business use",
                        "The dashboard should be read as an investigation funnel. A high risk score means 'review first', not 'automatically fraud'. This prevents false positives from being interpreted as model failure.",
                    ),
                    insight_card(
                        "Most actionable finding",
                        "Rules involving a sender account drained to zero and unusual balance behavior are rare but strongly tied to confirmed fraud. These patterns should be prioritized for alerts and manual review.",
                    ),
                ],
            ),
        ],
    )


def segments_tab() -> html.Div:
    clusters = pd.DataFrame(DATA["cluster_summary"]).copy()
    display_cols = [
        "segment_name",
        "transactions",
        "fraud_rate",
        "high_risk_rate",
        "main_behavior",
        "business_value",
    ]
    if not clusters.empty:
        clusters["fraud_rate"] = clusters["fraud_rate"].apply(lambda x: pct(x, 3))
        clusters["high_risk_rate"] = clusters["high_risk_rate"].apply(lambda x: pct(x, 2))
        clusters["transactions"] = clusters["transactions"].apply(num)
    return html.Div(
        className="tab-body",
        children=[
            html.Div(
                className="section-note",
                children=[
                    html.H3("Why K-Means is the main segmentation lens"),
                    html.P(
                        "K-Means is used as the primary customer-transaction segmentation reference because it produced four stable, interpretable groups. Direct HDBSCAN was useful as a stress test, but it labelled most rows as noise, while BIRCH plus HDBSCAN is better used for outlier cross-checking than for business segmentation."
                    ),
                ],
            ),
            html.Div(
                className="two-col",
                children=[
                    dcc.Graph(figure=FIGURES["cluster_size"], config={"displayModeBar": False}),
                    dcc.Graph(figure=FIGURES["cluster_risk"], config={"displayModeBar": False}),
                ],
            ),
            html.Div(
                className="table-card",
                children=[
                    html.H3("Segment characteristics in business language"),
                    dash_table.DataTable(
                        data=clusters[display_cols].to_dict("records") if not clusters.empty else [],
                        columns=[
                            {"name": "Segment", "id": "segment_name"},
                            {"name": "Transactions", "id": "transactions"},
                            {"name": "Fraud rate", "id": "fraud_rate"},
                            {"name": "High-risk rate", "id": "high_risk_rate"},
                            {"name": "Main behavior", "id": "main_behavior"},
                            {"name": "Business value", "id": "business_value"},
                        ],
                        page_size=4,
                        style_as_list_view=True,
                        style_table={"overflowX": "auto"},
                        style_cell={"whiteSpace": "normal", "height": "auto", "textAlign": "left", "fontFamily": "Inter, Arial", "fontSize": 13},
                        style_header={"fontWeight": "700"},
                    ),
                ],
            ),
        ],
    )


def rules_tab() -> html.Div:
    rules = pd.DataFrame(DATA["rules"]).head(10).copy()
    table_cols = ["When this is seen", "This usually comes with", "Coverage", "Hit rate inside that group", "Uplift vs normal", "Business takeaway"]
    return html.Div(
        className="tab-body",
        children=[
            html.Div(
                className="section-note",
                children=[
                    html.H3("How to read association rules"),
                    html.P(
                        "Each rule says: when a group of conditions appears, another condition is unusually likely to appear with it. Coverage means how often the pattern appears in all transactions. Hit rate means how often the result appears inside that group. Uplift means how much more common the result is compared with normal baseline behavior."
                    ),
                ],
            ),
            html.Div(className="two-col", children=[dcc.Graph(figure=FIGURES["rules_lift"], config={"displayModeBar": False}), insight_card("Plain-English takeaway", "The strongest rules are not broad patterns. They are rare combinations that sharply increase the concentration of confirmed fraud. This is why they are useful for alert prioritization even when they do not cover most transactions.")]),
            html.Div(
                className="table-card",
                children=[
                    html.H3("Top association rules translated for business users"),
                    dash_table.DataTable(
                        data=rules[table_cols].to_dict("records") if not rules.empty else [],
                        columns=[{"name": col, "id": col} for col in table_cols],
                        page_size=10,
                        style_as_list_view=True,
                        style_table={"overflowX": "auto"},
                        style_cell={"whiteSpace": "normal", "height": "auto", "textAlign": "left", "fontFamily": "Inter, Arial", "fontSize": 13, "minWidth": "130px"},
                        style_header={"fontWeight": "700"},
                    ),
                ],
            ),
        ],
    )


def risk_tab() -> html.Div:
    suspicious = pd.DataFrame(DATA["top_suspicious"])
    risk_levels = sorted([str(x) for x in suspicious.get("risk_level", pd.Series(dtype=str)).dropna().unique()]) if not suspicious.empty else []
    categories = sorted([str(x) for x in suspicious.get("investigation_category", pd.Series(dtype=str)).dropna().unique()]) if not suspicious.empty else []
    return html.Div(
        className="tab-body",
        children=[
            html.Div(
                className="two-col",
                children=[
                    dcc.Graph(figure=FIGURES["investigation_mix"], config={"displayModeBar": False}),
                    dcc.Graph(figure=FIGURES["anomaly_type"], config={"displayModeBar": False}),
                ],
            ),
            html.Div(
                className="two-col",
                children=[
                    dcc.Graph(figure=FIGURES["method_overlap"], config={"displayModeBar": False}),
                    html.Div(
                        className="section-note",
                        children=[
                            html.H3("Business interpretation"),
                            html.P("A transaction can be unusual for more than one reason: unusually large amount, structural behavior, cluster outlier status, balance mismatch, or account-draining behavior."),
                            html.P("The investigation category separates operational data-quality issues, rare legitimate cases, monitored risk, and potential fraud signals."),
                            html.P("This framing is better for business users than showing a raw model score only."),
                        ],
                    ),
                ],
            ),
            html.Div(
                className="table-card",
                children=[
                    html.H3("Suspicious transaction review queue"),
                    html.P("This table uses the exported top suspicious transaction parquet when available. The displayed records are meant for investigation prioritization, not automatic blocking."),
                    html.Div(
                        className="filter-row",
                        children=[
                            dcc.Dropdown(risk_levels, value=risk_levels, multi=True, placeholder="Risk level", id="risk-filter", className="filter-box"),
                            dcc.Dropdown(categories, value=categories, multi=True, placeholder="Investigation category", id="category-filter", className="filter-box"),
                            dcc.Input(id="queue-search", placeholder="Search reason, type, or segment...", debounce=True, className="search-box"),
                            html.Button("Reset", id="reset-filters", className="button"),
                        ],
                    ),
                    html.Div(id="queue-count", className="queue-count"),
                    dash_table.DataTable(
                        id="suspicious-table",
                        data=[],
                        columns=[
                            {"name": "Step", "id": "step"},
                            {"name": "Type", "id": "transaction_type"},
                            {"name": "Amount", "id": "amount"},
                            {"name": "Risk score", "id": "risk_score"},
                            {"name": "Risk level", "id": "risk_level"},
                            {"name": "Investigation", "id": "investigation_category"},
                            {"name": "Anomaly type", "id": "anomaly_type"},
                            {"name": "Reason", "id": "anomaly_reason"},
                            {"name": "KMeans segment", "id": "cluster_kmeans"},
                            {"name": "Confirmed fraud", "id": "isFraud"},
                        ],
                        page_size=15,
                        page_action="native",
                        sort_action="native",
                        style_as_list_view=True,
                        style_table={"overflowX": "auto"},
                        style_cell={"whiteSpace": "normal", "height": "auto", "textAlign": "left", "fontFamily": "Inter, Arial", "fontSize": 12},
                        style_header={"fontWeight": "700"},
                    ),
                ],
            ),
        ],
    )


def data_quality_tab() -> html.Div:
    facts = DATA["data_quality_findings"]
    return html.Div(
        className="tab-body",
        children=[
            html.Div(
                className="section-note",
                children=[
                    html.H3("Data quality findings that shape interpretation"),
                    html.P("These are business guardrails from Phase 1. They explain which patterns should be treated as real data characteristics rather than errors."),
                ],
            ),
            html.Div(
                className="insight-grid",
                children=[insight_card(fact["finding"], fact["business_meaning"]) for fact in facts],
            ),
            html.Div(
                className="section-note",
                children=[
                    html.H3("What we discovered beyond raw data"),
                    html.P("The raw data shows transaction values and labels. The mining process reveals a business structure: fraud is concentrated in certain transaction types and balance behaviors; K-Means creates interpretable customer-transaction segments; association rules expose rare but high-value risk combinations; anomaly detection turns those combinations into an investigation queue."),
                ],
            ),
        ],
    )


app = Dash(__name__, title="PaySim Banking Discovery Dashboard", suppress_callback_exceptions=True)
server = app.server

app.layout = html.Div(
    className="app-shell",
    children=[
        html.Div(
            className="hero",
            children=[
                html.Div(
                    children=[
                        html.Div("Phase 5 — Knowledge Presentation", className="eyebrow"),
                        html.H1("PaySim Banking Discovery Dashboard"),
                        html.P("Business-facing summary of data quality, customer segmentation, association rules, and anomaly investigation."),
                    ]
                ),
                source_badge(),
            ],
        ),
        dcc.Tabs(
            id="tabs",
            value="overview",
            className="tabs",
            children=[
                dcc.Tab(label="Executive Overview", value="overview"),
                dcc.Tab(label="Customer Segments", value="segments"),
                dcc.Tab(label="Association Rules", value="rules"),
                dcc.Tab(label="Anomaly & Risk", value="risk"),
                dcc.Tab(label="Data Quality", value="data_quality"),
            ],
        ),
        html.Div(id="tab-content"),
    ],
)


@app.callback(Output("tab-content", "children"), Input("tabs", "value"))
def render_tab(tab: str):
    if tab == "segments":
        return segments_tab()
    if tab == "rules":
        return rules_tab()
    if tab == "risk":
        return risk_tab()
    if tab == "data_quality":
        return data_quality_tab()
    return overview_tab()


@app.callback(
    Output("risk-filter", "value"),
    Output("category-filter", "value"),
    Output("queue-search", "value"),
    Input("reset-filters", "n_clicks"),
    State("risk-filter", "options"),
    State("category-filter", "options"),
    prevent_initial_call=True,
)
def reset_filters(_n_clicks, risk_options, category_options):
    risk_values = [opt["value"] if isinstance(opt, dict) else opt for opt in (risk_options or [])]
    category_values = [opt["value"] if isinstance(opt, dict) else opt for opt in (category_options or [])]
    return risk_values, category_values, ""


@app.callback(
    Output("suspicious-table", "data"),
    Output("queue-count", "children"),
    Input("risk-filter", "value"),
    Input("category-filter", "value"),
    Input("queue-search", "value"),
)
def update_suspicious_table(risk_levels, categories, search_value):
    df = pd.DataFrame(DATA["top_suspicious"]).copy()
    if df.empty:
        return [], "No transaction-level queue loaded. Run build_dashboard_cache.py after Phase 4 exports the suspicious transaction parquet."

    if risk_levels:
        df = df[df["risk_level"].astype(str).isin([str(x) for x in risk_levels])]
    if categories:
        df = df[df["investigation_category"].astype(str).isin([str(x) for x in categories])]
    if search_value:
        needle = str(search_value).lower().strip()
        searchable_cols = [
            c
            for c in ["transaction_type", "risk_level", "investigation_category", "anomaly_type", "anomaly_reason", "cluster_kmeans"]
            if c in df.columns
        ]
        mask = pd.Series(False, index=df.index)
        for col in searchable_cols:
            mask = mask | df[col].astype(str).str.lower().str.contains(needle, na=False)
        df = df[mask]

    display_df = df.head(500).copy()
    if "amount" in display_df.columns:
        display_df["amount"] = pd.to_numeric(display_df["amount"], errors="coerce").round(3)
    if "isFraud" in display_df.columns:
        display_df["isFraud"] = display_df["isFraud"].map({1: "Yes", 0: "No", True: "Yes", False: "No"}).fillna(display_df["isFraud"])

    msg = f"Showing {len(display_df):,} of {len(df):,} matching suspicious transactions."
    return display_df.to_dict("records"), msg


if __name__ == "__main__":
    app.run(debug=False, host="127.0.0.1", port=int(os.environ.get("PORT", "8050")))
