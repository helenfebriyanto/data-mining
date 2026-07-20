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