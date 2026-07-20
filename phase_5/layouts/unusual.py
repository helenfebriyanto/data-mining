from dash import html, dcc

from components.card import kpi_card, stat_pill
from business_labels import metrics_lookup


def _empty_state() -> html.Div:
    return html.Div(
        className="tab-body",
        children=[
            html.H2("Unusual Activities"),
            html.Div(
                "No anomaly data available yet. Run build_dashboard_cache.py after Phase 4 has produced its "
                "outputs, then reload this dashboard.",
                className="placeholder-box",
            ),
        ],
    )


def unusual_layout(DATA, FIGURES):
    risk_summary = DATA.get("risk_summary")
    metrics_df = DATA.get("fraud_validation_metrics")
    if risk_summary is None or risk_summary.empty:
        return _empty_state()

    total_txn = risk_summary["transactions"].sum()
    high_row = risk_summary[risk_summary["risk_level"] == "High"]
    critical_row = risk_summary[risk_summary["risk_level"] == "Critical"]
    high_ct = int(high_row["transactions"].sum()) if not high_row.empty else 0
    critical_ct = int(critical_row["transactions"].sum()) if not critical_row.empty else 0
    queue_ct = high_ct + critical_ct
    queue_share = (queue_ct / total_txn * 100) if total_txn else 0

    metrics = metrics_lookup(metrics_df)
    tp = metrics.get("TP", 0)
    fp = metrics.get("FP", 0)
    fn = metrics.get("FN", 0)
    recall = metrics.get("Recall", 0) * 100
    baseline_rate = metrics.get("Overall Fraud Rate", 0) * 100
    queue_rate = metrics.get("High Risk Fraud Rate", 0) * 100
    enrichment = metrics.get("Fraud Enrichment", 0)

    kpi_row = html.Div(
        className="kpi-grid",
        children=[
            kpi_card(
                "Transactions flagged for review",
                f"{queue_ct:,.0f}",
                f"{queue_share:.2f}% of all transactions identified as needing further review",
            ),
            kpi_card(
                "Confirmed fraud among flagged transactions",
                f"{tp:,.0f}",
                "Confirmed fraud cases found among transactions flagged for review",
            ),
            kpi_card(
                "Share of all fraud captured",
                f"{recall:.1f}%",
                "Share of all confirmed fraud cases found among flagged transactions",
            ),
            kpi_card(
                "Fraud concentration increase",
                f"{enrichment:.1f}x",
                "How many times more concentrated fraud is among flagged transactions compared with all transactions",
            ),
        ],
    )

    intro = html.Div(
        className="section-intro",
        children=[
            html.P(
                [
                    "Every transaction is checked four different, independent ways: a simple range check on amount, "
                    "a statistical extremeness check, a multi-behavior check that looks past amount alone, and a "
                    "check for whether the transaction sits outside the natural clusters found in segmentation. "
                    "Each check that a transaction fails adds to a combined ",
                    html.B("risk score from 0 to 6"),
                    ". More failed checks, and more serious ones, push the score — and the priority level — higher.",
                ]
            ),
        ],
    )

    validation = html.Div(
        className="validation-panel",
        children=[
            html.H3("How effective is the transaction flagging?"),
            html.P(
                [
                    "Confirmed fraud is extremely rare — about ",
                    html.B(f"{baseline_rate:.2f}%"),
                    " of all 6.3 million transactions. The system flags a smaller group of transactions for review. "
                    "What matters is whether confirmed fraud is more concentrated among these flagged transactions.",
                ]
            ),
            html.Div(
                className="validation-stats",
                children=[
                    stat_pill("Baseline fraud rate", f"{baseline_rate:.2f}%"),
                    stat_pill("Fraud rate among flagged transactions", f"{queue_rate:.2f}%"),
                    stat_pill("Confirmed fraud found", f"{tp:,.0f}"),
                    stat_pill("Flagged but turned out fine", f"{fp:,.0f}"),
                    stat_pill("Fraud that slipped through", f"{fn:,.0f}"),
                ],
            ),
            html.P(
                [
                    "In short, the system narrows 6.3 million transactions down to around 64,000 transactions "
                    "that need further review. These flagged transactions contain a higher concentration of confirmed "
                    "fraud. However, about ",
                    f"{100 - recall:.0f}% ",
                    "of fraud cases are not captured by these flags and still require other detection controls.",
                ],
                className="chart-footnote",
            ),
        ],
    )

    enrichment_chart = html.Div(
        className="table-card",
        children=[dcc.Graph(figure=FIGURES["enrichment_comparison"], config={"displayModeBar": False})],
    )

    top_charts = html.Div(
        className="two-col",
        children=[
            html.Div(className="table-card", children=[dcc.Graph(figure=FIGURES["risk_distribution"], config={"displayModeBar": False})]),
            html.Div(className="table-card", children=[dcc.Graph(figure=FIGURES["fraud_by_score"], config={"displayModeBar": False})]),
        ],
    )

    mid_charts = html.Div(
        className="two-col",
        children=[
            html.Div(className="table-card", children=[dcc.Graph(figure=FIGURES["investigation_mix"], config={"displayModeBar": False})]),
            html.Div(className="table-card", children=[dcc.Graph(figure=FIGURES["anomaly_type"], config={"displayModeBar": False})]),
        ],
    )

    overlap_chart = html.Div(
        className="table-card",
        children=[
            dcc.Graph(figure=FIGURES["method_overlap"], config={"displayModeBar": False}),
            html.P(
                "Each cell shows how many transactions two checks flagged in common (the diagonal shows how many "
                "each check flagged on its own). Heavy overlap between two checks is a stronger, more trustworthy "
                "signal than any single check alone.",
                className="chart-footnote",
            ),
        ],
    )

    callout = html.Div(
        className="callout callout-info",
        children=[
            html.Div("Worth noting", className="callout-tag"),
            html.P(
                [
                    "Risk score isn't perfectly linear with fraud risk. Transactions scoring ",
                    html.B("Medium (2)"),
                    " actually show a higher confirmed-fraud rate (",
                    html.B("44.3%"),
                    ") than transactions scoring ",
                    html.B("Critical (6)"),
                    " (",
                    html.B("20.7%"),
                    "). A Medium score can come from either two mild signals or one focused statistical signal, and "
                    "in this data that specific combination lines up unusually well with fraud. When prioritizing "
                    "reviews, it's worth looking at which checks a transaction failed, not only its final score.",
                ]
            ),
        ],
    )

    return html.Div(
        className="tab-body",
        children=[
            html.H2("Unusual Activities"),
            html.P(
                "How suspicious activity is scored, how much of it is real, and where to focus review effort.",
                className="tab-subtitle",
            ),
            intro,
            kpi_row,
            validation,
            enrichment_chart,
            html.Hr(),
            html.H3("Why transactions are flagged for review"),
            top_charts,
            mid_charts,
            overlap_chart,
            callout,
        ],
    )
