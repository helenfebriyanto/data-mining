from dash import html, dcc

from business_labels import RULE_GROUP_ORDER, RULE_GROUP_BADGE
from components.card import kpi_card, rule_card


def _empty_state() -> html.Div:
    return html.Div(
        className="tab-body",
        children=[
            html.H2("Hidden Transaction Patterns"),
            html.Div(
                "No association rules available yet. Run build_dashboard_cache.py after Phase 3 has produced "
                "its outputs, then reload this dashboard.",
                className="placeholder-box",
            ),
        ],
    )


def patterns_layout(DATA, FIGURES):
    rules = DATA.get("rules")
    if rules is None or rules.empty:
        return _empty_state()

    rules = rules.sort_values("lift", ascending=False).reset_index(drop=True)
    n_rules = len(rules)
    top_rule = rules.iloc[0]
    fraud_rules = rules[rules.get("Rule group", "") == "Fraud pattern"] if "Rule group" in rules.columns else rules.iloc[0:0]

    kpi_row = html.Div(
        className="kpi-grid",
        children=[
            kpi_card("Patterns found", str(n_rules), "Recurring combinations of transaction traits worth knowing about"),
            kpi_card(
                "Strongest pattern",
                f"{top_rule.get('lift', 0):.0f}x",
                "More common together than pure chance would predict",
            ),
            kpi_card(
                "Fraud-linked patterns",
                str(len(fraud_rules)),
                "Patterns where the outcome is confirmed fraud, not just unusual behavior",
            ),
            kpi_card(
                "Best fraud pattern confidence",
                f"{fraud_rules['confidence'].max() * 100:.0f}%" if len(fraud_rules) else "—",
                "Of transactions matching the strongest fraud pattern, this share were confirmed fraud",
            ),
        ],
    )

    intro = html.Div(
        className="section-intro",
        children=[
            html.P(
                [
                    "Association rules answer a simple question: ",
                    html.I("\u201cwhen we see this, what else usually comes with it?\u201d"),
                    " It's the same logic retailers use for \u201ccustomers who bought diapers often also bought "
                    "baby wipes.\u201d Here, instead of shopping baskets, we look at transaction traits — amount "
                    "level, account type, balance behavior, segment — and find which combinations show up together "
                    "far more often than random chance would explain.",
                ]
            ),
            html.Div(
                className="legend-row",
                children=[
                    html.Div(
                        className="legend-item",
                        children=[html.B("Coverage — "), "how often this exact combination shows up across all transactions."],
                    ),
                    html.Div(
                        className="legend-item",
                        children=[html.B("Hit rate — "), "when the first part happens, how often the second part follows it."],
                    ),
                    html.Div(
                        className="legend-item",
                        children=[html.B("Uplift vs. chance — "), "how many times more often this pairing occurs than if the two traits were unrelated. 1x means no relationship; higher means a stronger real pattern."],
                    ),
                ],
            ),
        ],
    )

    present_groups = [g for g in RULE_GROUP_ORDER if "Rule group" in rules.columns and (rules["Rule group"] == g).any()]
    filter_options = [{"label": f"All patterns ({n_rules})", "value": "all"}] + [
        {"label": f"{g} ({(rules['Rule group'] == g).sum()})", "value": g} for g in present_groups
    ]
    selector = html.Div(
        className="selector-row",
        children=[
            html.Span("Show:", className="selector-label"),
            dcc.RadioItems(
                id="rule-focus-selector",
                options=filter_options,
                value="all",
                className="pill-selector",
                inputClassName="pill-input",
                labelClassName="pill-label",
            ),
        ],
    )

    cards = []
    for i, (_, row) in enumerate(rules.iterrows(), start=1):
        group = row.get("Rule group", "General behavior")
        cards.append(
            rule_card(
                rule_number=i,
                when_text=row.get("When this is seen", ""),
                then_text=row.get("This usually comes with", ""),
                coverage=row.get("Coverage", "—"),
                hit_rate=row.get("Hit rate inside that group", "—"),
                uplift=row.get("Uplift vs normal", "—"),
                takeaway=row.get("Business takeaway", ""),
                group=group,
                group_badge_class=RULE_GROUP_BADGE.get(group, "badge badge-normal"),
            )
        )

    cards_wrapper = html.Div(
        id="rules-grid",
        className="rules-grid",
        **{"data-filter": "all"},
        children=cards,
    )

    chart = html.Div(
        className="table-card",
        children=[
            dcc.Graph(figure=FIGURES["rules_lift"], config={"displayModeBar": False}),
            html.P(
                "Longer bars mean the pattern is far more common than coincidence would suggest. Hover any bar "
                "for the full plain-English description.",
                className="chart-footnote",
            ),
        ],
    )

    callout = html.Div(
        className="callout callout-critical",
        children=[
            html.Div("Key finding", className="callout-tag"),
            html.P(
                [
                    "When a sender's balance math is ",
                    html.B("perfectly consistent (very low reconciliation error)"),
                    " at the same time the sender's account is ",
                    html.B("drained all the way to zero"),
                    ", the transaction is confirmed fraud ",
                    html.B("100% of the time"),
                    " in this data — about ",
                    html.B("776 times"),
                    " more often than chance alone would predict. That single combination is one of the strongest, "
                    "most actionable real-time screening rules to come out of this analysis.",
                ]
            ),
        ],
    )

    return html.Div(
        className="tab-body",
        children=[
            html.H2("Hidden Transaction Patterns"),
            html.P(
                "Which transaction traits tend to travel together, explained in plain language.",
                className="tab-subtitle",
            ),
            intro,
            kpi_row,
            selector,
            cards_wrapper,
            html.Hr(),
            html.H3("All patterns ranked by strength"),
            chart,
            callout,
        ],
    )
