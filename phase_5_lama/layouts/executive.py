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

    total_transactions = f"{risk['transactions'].sum():,.0f}"
    total_segments = len(cluster)
    total_rules = len(rules)

    return html.Div(

        [

            # ==========================================
            # Header
            # ==========================================

            html.Div(

                [

                    html.H2("Executive Summary"),

                    html.P(
                        "A high-level overview of customer behaviour, transaction trends, hidden patterns, and potential risks.",
                    ),

                ],

                className="section-note",

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
                        "Risk Level",
                        "Low",
                        "Overall portfolio"
                    ),

                    kpi_card(
                        "Status",
                        "Healthy",
                        "Business overview"
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

                            html.H4("Customer Behaviour"),

                            html.P(
                                "Most customers perform routine banking activities with consistent transaction behaviour."
                            ),

                        ],

                        className="insight-card",

                    ),

                    html.Div(

                        [

                            html.H4("Transaction Patterns"),

                            html.P(
                                "Several recurring transaction combinations were discovered, indicating predictable customer habits."
                            ),

                        ],

                        className="insight-card",

                    ),

                    html.Div(

                        [

                            html.H4("Risk Monitoring"),

                            html.P(
                                "Only a small proportion of transactions require additional investigation for potential fraud."
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
                                "Focus fraud investigation on transactions with unusual behaviour."
                            ),

                            html.Li(
                                "Develop targeted marketing strategies for each customer segment."
                            ),

                            html.Li(
                                "Monitor high-value transactions continuously."
                            ),

                            html.Li(
                                "Leverage recurring transaction patterns to improve customer experience."
                            ),

                        ]

                    ),

                ],

                className="section-note",

            ),

        ]

    )