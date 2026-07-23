from dash import html

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


def source_badge(using_cache: bool) -> html.Div:
    if using_cache:
        text = "Data source: dashboard cache generated from local parquet/CSV outputs."
        cls = "source-badge ok"
    else:
        text = "Data source: fallback notebook summaries. Run build_dashboard_cache.py for final local data."
        cls = "source-badge warn"
    return html.Div(text, className=cls)


def badge(text: str, class_name: str = "badge badge-normal") -> html.Span:
    return html.Span(text, className=class_name)


def stat_pill(label: str, value: str) -> html.Div:
    return html.Div(
        className="stat-pill",
        children=[
            html.Span(value, className="stat-pill-value"),
            html.Span(label, className="stat-pill-label"),
        ],
    )


def rule_card(
    rule_number: int,
    when_text: str,
    then_text: str,
    coverage: str,
    hit_rate: str,
    uplift: str,
    takeaway: str,
    group: str,
    group_badge_class: str,
) -> html.Div:
    return html.Div(
        className="rule-card",
        **{"data-category": group},
        children=[
            html.Div(
                className="rule-card-head",
                children=[
                    html.Span(f"Pattern #{rule_number}", className="rule-number"),
                    html.Span(group, className=group_badge_class),
                ],
            ),
            html.P(
                className="rule-sentence",
                children=["When ", html.B(when_text), ", it usually comes with ", html.B(then_text), "."],
            ),
            html.Div(
                className="rule-stats",
                children=[
                    stat_pill("Coverage", coverage),
                    stat_pill("Hit rate", hit_rate),
                    stat_pill("Uplift vs. chance", uplift),
                ],
            ),
            html.Div(takeaway, className="rule-takeaway"),
        ],
    )


def segment_card(
    card_id: str,
    cluster_id,
    segment_name: str,
    share: str,
    transactions: str,
    fraud_rate: str,
    high_risk_rate: str,
    profile: str,
    value: str,
    behavior: str,
) -> html.Div:
    return html.Div(
        id=card_id,
        className="segment-card",
        **{"data-segment": str(cluster_id)},
        children=[
            html.H4(segment_name),
            html.Div(
                className="segment-stats",
                children=[
                    stat_pill("Share of activity", share),
                    stat_pill("Transactions", transactions),
                    stat_pill("Fraud rate", fraud_rate),
                    stat_pill("High-risk rate", high_risk_rate),
                ],
            ),
            html.P(profile, className="segment-profile"),
            html.P([html.B("Main behavior: "), behavior], className="segment-line"),
            html.P([html.B("How to use it: "), value], className="segment-line"),
        ],
    )