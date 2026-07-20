"""All Dash callbacks for the dashboard, kept separate from layout/data code.

Performance design:
- Switching top-level tabs, the segment spotlight, and the rule-pattern filter are all
  handled by trivial CLIENTSIDE callbacks (pure JS, no server round trip at all). Every
  panel/card is already rendered once at startup; these callbacks only flip a
  `data-*` attribute that CSS uses to show/hide the right elements, so the interaction
  is effectively instant (well under 100ms) regardless of server latency.
- The Data Explorer table is the one place that genuinely needs server-side logic
  (filtering/sorting/paging a real dataframe). That dataframe is at most ~20,000 rows
  and lives in memory already, so filtering it is a low-single-digit-millisecond
  pandas operation — the only added latency is the Dash server round trip itself.
"""
from dash import Input, Output

from layouts.explorer import filter_and_paginate, queue_count_text, build_tooltip_data

_PASSTHROUGH_JS = "function(value) { return value; }"


def register_callbacks(app, DATA):
    # ------------------------------------------------------------------
    # Instant, fully clientside show/hide (no server round trip)
    # ------------------------------------------------------------------
    app.clientside_callback(_PASSTHROUGH_JS, Output("app-body", "data-tab"), Input("tabs", "value"))

    app.clientside_callback(
        _PASSTHROUGH_JS,
        Output("segment-cards-wrapper", "data-selected"),
        Input("segment-focus-selector", "value"),
    )

    app.clientside_callback(
        _PASSTHROUGH_JS,
        Output("rules-grid", "data-filter"),
        Input("rule-focus-selector", "value"),
    )

    # ------------------------------------------------------------------
    # Data Explorer: server-side filter + sort + page (only when data exists)
    # ------------------------------------------------------------------
    df_suspicious = DATA.get("top_suspicious")
    if df_suspicious is None or df_suspicious.empty:
        return

    filter_inputs = (
        Input("explorer-filter-risk", "value"),
        Input("explorer-filter-category", "value"),
        Input("explorer-filter-type", "value"),
        Input("explorer-filter-segment", "value"),
    )

    # Runs first (when a filter changes) and snaps the table back to page 0.
    # Kept as its own callback so `page_current` is never both an Input and an
    # Output of the same callback — this callback only ever WRITES page_current,
    # the other only ever READS it.
    @app.callback(
        Output("explorer-table", "page_current"),
        *filter_inputs,
        prevent_initial_call=True,
    )
    def reset_explorer_page(risk_sel, cat_sel, type_sel, seg_sel):
        return 0

    @app.callback(
        Output("explorer-table", "data"),
        Output("explorer-table", "tooltip_data"),
        Output("explorer-table", "page_count"),
        Output("explorer-queue-count", "children"),
        Input("explorer-table", "page_current"),
        Input("explorer-table", "page_size"),
        Input("explorer-table", "sort_by"),
        *filter_inputs,
    )
    def update_explorer_table(page_current, page_size, sort_by, risk_sel, cat_sel, type_sel, seg_sel):
        records, page_count, total_matched, _ = filter_and_paginate(
            df_suspicious,
            page_current=page_current,
            page_size=page_size,
            sort_by=sort_by,
            risk_sel=risk_sel,
            cat_sel=cat_sel,
            type_sel=type_sel,
            seg_sel=seg_sel,
        )
        text = queue_count_text(len(records), total_matched, len(df_suspicious))
        return records, build_tooltip_data(records), page_count, text

    @app.callback(
        Output("explorer-filter-risk", "value"),
        Output("explorer-filter-category", "value"),
        Output("explorer-filter-type", "value"),
        Output("explorer-filter-segment", "value"),
        Input("explorer-reset-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def reset_explorer_filters(n_clicks):
        return None, None, None, None
