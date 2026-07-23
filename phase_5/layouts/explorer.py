import math

from dash import html, dcc, dash_table

from business_labels import RISK_BADGE_CLASS, INVESTIGATION_BADGE_CLASS, TRANSACTION_TYPE_LABELS

PAGE_SIZE = 12

EXPLORER_COLUMNS = [
    {"id": "Day", "name": "When"},
    {"id": "Transaction Type", "name": "Type"},
    {"id": "amount", "name": "Amount (standardized)"},
    {"id": "risk_score", "name": "Risk Score"},
    {"id": "risk_level", "name": "Risk Level"},
    {"id": "investigation_category", "name": "Investigation Category"},
    {"id": "anomaly_type", "name": "Anomaly Type"},
    {"id": "cluster_kmeans", "name": "Segment"},
    {"id": "Historical Label", "name": "Confirmed Fraud?"},
    {"id": "anomaly_reason", "name": "Why Flagged"},
]

_COLUMN_IDS = [c["id"] for c in EXPLORER_COLUMNS]

RISK_ROW_COLORS = {
    "Critical": ("#fee2e2", "#991b1b"),
    "High": ("#ffedd5", "#9a3412"),
    "Medium": ("#fef9c3", "#854d0e"),
    "Low": ("#e0f2fe", "#075985"),
    "Normal": ("#f1f5f9", "#475569"),
}


def style_data_conditional():
    rules = []
    for level, (bg, fg) in RISK_ROW_COLORS.items():
        rules.append(
            {
                "if": {"filter_query": '{{risk_level}} = "{}"'.format(level)},
                "backgroundColor": bg,
                "color": fg,
            }
        )
    return rules


def filter_and_paginate(df, page_current=0, page_size=PAGE_SIZE, sort_by=None, risk_sel=None, cat_sel=None, type_sel=None, seg_sel=None):
    """Pure filtering/sorting/paging logic shared by the initial layout render and the update callback.

    Operates entirely on the already in-memory `top_suspicious` dataframe (at most ~20,000 rows),
    so this always executes in low single-digit milliseconds — the only per-interaction cost is
    the Dash server round trip itself.
    """
    filtered = df
    if risk_sel:
        filtered = filtered[filtered["risk_level"].isin(risk_sel)]
    if cat_sel:
        filtered = filtered[filtered["investigation_category"].isin(cat_sel)]
    if type_sel:
        filtered = filtered[filtered["transaction_type"].isin(type_sel)]
    if seg_sel:
        filtered = filtered[filtered["cluster_kmeans"].isin(seg_sel)]

    total_matched = len(filtered)
    page_size = page_size or PAGE_SIZE
    page_count = max(1, math.ceil(total_matched / page_size))
    page_current = min(max(page_current or 0, 0), page_count - 1)

    if sort_by:
        cols = [s["column_id"] for s in sort_by if s["column_id"] in filtered.columns]
        ascending = [s["direction"] == "asc" for s in sort_by if s["column_id"] in filtered.columns]
        if cols:
            filtered = filtered.sort_values(cols, ascending=ascending)
    else:
        filtered = filtered.sort_values("risk_score", ascending=False)

    start = page_current * page_size
    page_df = filtered.iloc[start : start + page_size]
    records = page_df[_COLUMN_IDS].to_dict("records")
    return records, page_count, total_matched, page_current


def queue_count_text(shown: int, total_matched: int, total_rows: int) -> str:
    if total_matched == total_rows:
        return f"Showing {shown:,} of {total_matched:,} flagged transactions in the full review queue."
    return f"Showing {shown:,} of {total_matched:,} flagged transactions matching your filters (out of {total_rows:,} in the full review queue)."


def build_tooltip_data(records):
    """Full-text tooltip for the truncated 'Why Flagged' cell. Must be recomputed
    alongside `data` on every page/filter/sort change, or tooltips go stale."""
    return [{"anomaly_reason": {"value": str(r.get("anomaly_reason", "")), "type": "text"}} for r in records]


def _empty_state() -> html.Div:
    return html.Div(
        className="tab-body",
        children=[
            html.H2("Data Explorer"),
            html.Div(
                "No transaction-level records are available in this build. This view needs "
                "top_suspicious_light.parquet, produced by build_dashboard_cache.py once Phase 4 has run. Every "
                "other tab on this dashboard still works from the summary cache in the meantime.",
                className="placeholder-box",
            ),
        ],
    )


def explorer_layout(DATA, FIGURES):
    df = DATA.get("top_suspicious")
    if df is None or df.empty:
        return _empty_state()

    total_rows = len(df)

    risk_options = [{"label": lvl, "value": lvl} for lvl in RISK_BADGE_CLASS if lvl in set(df["risk_level"])]
    category_options = [
        {"label": cat, "value": cat} for cat in INVESTIGATION_BADGE_CLASS if cat in set(df["investigation_category"])
    ]
    type_options = [
        {"label": lbl, "value": t} for t, lbl in TRANSACTION_TYPE_LABELS.items() if t in set(df["transaction_type"])
    ]
    segment_options = [{"label": s, "value": s} for s in sorted(set(df["cluster_kmeans"].dropna()))]

    filters = html.Div(
        className="filter-row",
        children=[
            html.Div(
                className="filter-box",
                children=[
                    html.Label("Risk level"),
                    dcc.Dropdown(id="explorer-filter-risk", options=risk_options, multi=True, placeholder="All risk levels"),
                ],
            ),
            html.Div(
                className="filter-box",
                children=[
                    html.Label("Investigation category"),
                    dcc.Dropdown(id="explorer-filter-category", options=category_options, multi=True, placeholder="All categories"),
                ],
            ),
            html.Div(
                className="filter-box",
                children=[
                    html.Label("Transaction type"),
                    dcc.Dropdown(id="explorer-filter-type", options=type_options, multi=True, placeholder="All types"),
                ],
            ),
            html.Div(
                className="filter-box",
                children=[
                    html.Label("Segment"),
                    dcc.Dropdown(id="explorer-filter-segment", options=segment_options, multi=True, placeholder="All segments"),
                ],
            ),
            html.Button("Reset filters", id="explorer-reset-btn", className="button", n_clicks=0),
        ],
    )

    records, page_count, total_matched, page_current = filter_and_paginate(df, page_current=0, page_size=PAGE_SIZE)

    queue_count = html.Div(
        id="explorer-queue-count",
        className="queue-count",
        children=queue_count_text(len(records), total_matched, total_rows),
    )

    table = html.Div(
        className="dash-table-container",
        children=[
            dash_table.DataTable(
                id="explorer-table",
                columns=EXPLORER_COLUMNS,
                data=records,
                page_current=0,
                page_count=page_count,
                page_size=PAGE_SIZE,
                page_action="custom",
                sort_action="custom",
                sort_mode="single",
                sort_by=[],
                style_as_list_view=True,
                style_table={"overflowX": "auto"},
                style_cell={
                    "padding": "10px 12px",
                    "fontFamily": "Inter, Arial, sans-serif",
                    "fontSize": "13px",
                    "textAlign": "left",
                    "maxWidth": 260,
                    "overflow": "hidden",
                    "textOverflow": "ellipsis",
                },
                style_header={"backgroundColor": "#f8fafc", "fontWeight": "700", "borderBottom": "2px solid #e2e8f0"},
                style_data_conditional=style_data_conditional(),
                tooltip_data=build_tooltip_data(records),
                tooltip_duration=None,
            )
        ],
    )

    caption = html.P(
        "This view lists the top 20,000 highest-priority transactions identified for review, not the full 6.3 "
        "million transaction history. Amounts are shown on a standardized scale (0 = a typical transaction size; "
        "higher means larger than typical) because original dollar values are not retained after preprocessing. "
        "\u201cConfirmed Fraud?\u201d reflects the historical outcome label, not a live prediction.",
        className="chart-footnote",
    )

    return html.Div(
        className="tab-body",
        children=[
            html.H2("Data Explorer"),
            html.P("Search and filter the transactions our system flagged for review.", className="tab-subtitle"),
            filters,
            queue_count,
            dcc.Loading(type="dot", children=[table]),
            caption,
        ],
    )
