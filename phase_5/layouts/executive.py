from dash import html, dcc
from components.card import kpi_card


def executive_layout(DATA, FIGURES):

    risk = DATA["risk_summary"]
    cluster = DATA["cluster_summary"]
    rules = DATA["rules"]
    investigation = DATA["investigation_summary"]

    potential_fraud = (
        investigation.loc[
            investigation["investigation_category"] == "Potential Fraud",
            "transactions",
        ]
        .sum()
    )

    total_transactions_n = risk["transactions"].sum()
    total_transactions = f"{total_transactions_n:,.0f}"
    total_segments = len(cluster)
    total_rules = len(rules)

    flagged_txn = risk.loc[
        risk["risk_level"].isin(["High", "Critical"]),
        "transactions"
    ].sum()

    flagged_share = (
        flagged_txn / total_transactions_n * 100
        if total_transactions_n
        else 0
    )

    if flagged_share < 2:
        status_label = "Low"
        status_desc = (
            "Only a small share of transactions are flagged for further review"
        )
    elif flagged_share < 5:
        status_label = "Elevated"
        status_desc = (
            "A larger share of transactions are flagged and should be monitored"
        )
    else:
        status_label = "High"
        status_desc = (
            "A significant share of transactions require further review"
        )

    return html.Div(
        className="tab-body",
        children=[

            # ==========================================
            # Header
            # ==========================================

            html.H2("Executive Summary"),

            html.P(
                "A high-level overview of customer behaviour, transaction trends, hidden patterns, and potential risks.",
                className="tab-subtitle",
            ),

            # ==========================================
            # KPI
            # ==========================================

            html.Div(
                [
                    kpi_card(
                        "Transactions",
                        total_transactions,
                        "Transactions analysed"
                    ),

                    kpi_card(
                        "Segments",
                        total_segments,
                        "Customer groups"
                    ),

                    kpi_card(
                        "Patterns",
                        total_rules,
                        "Association rules found"
                    ),

                    kpi_card(
                        "Potential Fraud",
                        f"{potential_fraud:,}",
                        "Needs investigation"
                    ),

                    kpi_card(
                        "Transactions Flagged for Review",
                        f"{flagged_share:.2f}%",
                        "Share of all transactions identified as needing further review"
                    ),

                    kpi_card(
                        "Overall Review Level",
                        status_label,
                        status_desc
                    ),
                ],
                className="kpi-grid",
            ),

            # ==========================================
            # Charts
            # ==========================================

            html.Div(
                [
                    html.Div(
                        [
                            html.H3("Risk Distribution"),

                            dcc.Graph(
                                figure=FIGURES["risk_distribution"],
                                config={"displayModeBar": False},
                            ),
                        ],
                        className="table-card",
                    ),

                    html.Div(
                        [
                            html.H3("Customer Segments"),

                            dcc.Graph(
                                figure=FIGURES["cluster_size"],
                                config={"displayModeBar": False},
                            ),
                        ],
                        className="table-card",
                    ),
                ],
                className="two-col",
            ),

            # ==========================================
            # Business Highlights
            # ==========================================

            html.Div(
                [
                    html.Div(
                        [
                            html.H4("Customer Behavior"),

                            html.P(
                                f"{total_segments} behavior segments emerged automatically from the data. One "
                                "barely-there segment (0.03% of transactions) carries zero fraud labels yet is "
                                "frequently flagged for review — see Customer Segments for the full picture."
                            ),
                        ],
                        className="insight-card",
                    ),

                    html.Div(
                        [
                            html.H4("Transaction Patterns"),

                            html.P(
                                f"{total_rules} recurring trait combinations were found. The strongest links a "
                                "drained sender balance with near-perfect reconciliation math to confirmed fraud "
                                "with 100% confidence — see Hidden Patterns for the rest."
                            ),
                        ],
                        className="insight-card",
                    ),

                    html.Div(
                        [
                            html.H4("Risk Monitoring"),

                            html.P(
                                f"{flagged_share:.2f}% of transactions are flagged for further review. "
                                "Confirmed fraud is more concentrated among these transactions than across "
                                "all transactions — see Unusual Activities for further analysis."
                            ),
                        ],
                        className="insight-card",
                    ),
                ],
                className="insight-grid",
            ),

            # ==========================================
            # Recommendation
            # ==========================================

            html.Div(
                [
                    html.H3("Recommended Actions"),

                    html.Ul(
                        [
                            html.Li(
                                "Give the Exceptional High-Value Transfer segment a manual review process of its "
                                "own — it has no fraud labels on record, but the highest internal risk score of "
                                "any segment."
                            ),

                            html.Li(
                                "Automate a real-time check for the drained-balance-plus-clean-reconciliation "
                                "pattern — it predicts confirmed fraud with 100% confidence in this data."
                            ),

                            html.Li(
                                "Use transactions flagged for review to focus investigation efforts rather than "
                                "as a final fraud verdict. These flags concentrate confirmed fraud but do not "
                                "capture every fraud case."
                            ),

                            html.Li(
                                "See the Recommendations tab for the full list of findings with supporting "
                                "evidence for each one."
                            ),
                        ]
                    ),
                ],
                className="section-note",
            ),
        ],
    )