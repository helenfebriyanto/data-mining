from dash import html, dcc

from components.card import kpi_card, segment_card


def _short_name(full: str) -> str:
    """'Segment 0 — Exceptional High-Value Transfer' -> 'Exceptional High-Value Transfer'"""
    text = str(full)
    return text.split("—")[-1].strip() if "—" in text else text


def _empty_state() -> html.Div:
    return html.Div(
        className="tab-body",
        children=[
            html.H2("Customer & Transaction Segments"),
            html.Div(
                "No segment data available yet. Run build_dashboard_cache.py after Phase 2 and Phase 4 "
                "have produced their outputs, then reload this dashboard.",
                className="placeholder-box",
            ),
        ],
    )


def segmentation_layout(DATA, FIGURES):
    print(DATA["cluster_summary"].head())
    print(DATA["cluster_summary"].columns)
    cluster = DATA.get("cluster_summary")
    if cluster is None or cluster.empty or "cluster_kmeans" not in cluster.columns:
        return _empty_state()
    
    print(
        cluster[
            [
                "cluster_kmeans",
                "transactions",
                "high_risk_count",
                "high_risk_rate_pct",
                "high_risk_rate",
            ]
        ]
    )

    print(cluster["high_risk_rate"].dtype)

    cluster = cluster.sort_values("cluster_kmeans").reset_index(drop=True)
    n_segments = len(cluster)
    total_txn = cluster["transactions"].sum()
    largest = cluster.loc[cluster["transactions"].idxmax()]
    riskiest = cluster.loc[cluster["high_risk_rate"].idxmax()]

    kpi_row = html.Div(
        className="kpi-grid",
        children=[
            kpi_card(
                "Segments discovered",
                str(n_segments),
                "Behavior groups found automatically from transaction patterns — nobody told the model what to look for",
            ),
            kpi_card(
                "Transactions covered",
                f"{total_txn:,.0f}",
                "Combined size of every segment analyzed",
            ),
            kpi_card(
                "Largest segment",
                _short_name(largest["Segment"]),
                f"{largest['Share of activity']} of all activity",
            ),
            kpi_card(
                "Needs the closest watch",
                _short_name(riskiest["Segment"]),
                f"{riskiest['High-risk queue rate']} of its transactions land in the high-risk review queue",
            ),
        ],
    )

    intro = html.Div(
        className="section-intro",
        children=[
            html.P(
                [
                    "We grouped every transaction into behavioral segments using ",
                    html.B("K-Means clustering"),
                    " — a technique that automatically sorts records into naturally occurring groups based on shared "
                    "behavior, without being told in advance what those groups should look like. It's the same idea as "
                    "a retailer discovering \u201cbargain hunters\u201d and \u201cbig spenders\u201d from purchase "
                    "history alone, with no labels provided upfront. Three grouping methods were tested; K-Means gave "
                    "the clearest and most stable segments, so it is the primary lens used throughout this dashboard.",
                ]
            )
        ],
    )

    # --- Interactive spotlight selector -------------------------------------------------
    options = [{"label": "All segments", "value": "all"}] + [
        {"label": _short_name(row["Segment"]), "value": str(int(row["cluster_kmeans"]))}
        for _, row in cluster.iterrows()
    ]
    selector = html.Div(
        className="selector-row",
        children=[
            html.Span("Focus on:", className="selector-label"),
            dcc.RadioItems(
                id="segment-focus-selector",
                options=options,
                value="all",
                className="pill-selector",
                inputClassName="pill-input",
                labelClassName="pill-label",
            ),
        ],
    )

    cards = [
        segment_card(
            card_id=f"segment-card-{int(row['cluster_kmeans'])}",
            cluster_id=int(row["cluster_kmeans"]),
            segment_name=row["Segment"],
            share=row["Share of activity"],
            transactions=row["Transactions"],
            fraud_rate=row["Fraud rate"],
            high_risk_rate=row["High-risk queue rate"],
            profile=row.get("business_profile", ""),
            value=row.get("business_value", ""),
            behavior=row.get("main_behavior", ""),
        )
        for _, row in cluster.iterrows()
    ]
    cards_wrapper = html.Div(
        id="segment-cards-wrapper",
        className="segment-cards-grid",
        **{"data-selected": "all"},
        children=cards,
    )

    charts = html.Div(
        className="two-col",
        children=[
            html.Div(className="table-card", children=[dcc.Graph(figure=FIGURES["cluster_size"], config={"displayModeBar": False})]),
            html.Div(className="table-card", children=[dcc.Graph(figure=FIGURES["cluster_risk"], config={"displayModeBar": False})]),
        ],
    )

    landscape = html.Div(
        className="table-card",
        children=[
            dcc.Graph(figure=FIGURES["segment_landscape"], config={"displayModeBar": False}),
            html.P(
                "Each bubble is one segment. Position shows how big it is and how often confirmed fraud shows up in "
                "it; bubble size shows the average internal risk score. A segment can be tiny and still deserve "
                "attention if its bubble is large.",
                className="chart-footnote",
            ),
        ],
    )

    callout = html.Div(
        className="callout callout-warn",
        children=[
            html.Div("Key finding", className="callout-tag"),
            html.P(
                [
                    html.B("Exceptional High-Value Transfer"),
                    " is only 0.03% of all transactions and carries ",
                    html.B("zero confirmed fraud labels"),
                    " — yet ",
                    html.B("79% of its transactions land in the high-risk queue"),
                    ", the highest rate of any segment by a wide margin. Historical fraud labels alone would miss "
                    "this group entirely. It behaves like a small population of unusually large, hard-to-reconcile "
                    "transfers that deserves a manual review process of its own, separate from mainstream fraud "
                    "monitoring.",
                ]
            ),
        ],
    )

    return html.Div(
        className="tab-body",
        children=[
            html.H2("Customer & Transaction Segments"),
            html.P(
                "How the 6.3 million transactions naturally group into behavior segments, and what each one means "
                "for the business.",
                className="tab-subtitle",
            ),
            intro,
            kpi_row,
            selector,
            cards_wrapper,
            html.Hr(),
            html.H3("Segment size and risk, visually"),
            charts,
            landscape,
            callout,
        ],
    )
