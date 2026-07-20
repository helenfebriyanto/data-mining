from dash import html, dcc

from business_labels import metrics_lookup
from utils.figures import METHOD_LABELS


def _empty_state() -> html.Div:
    return html.Div(
        className="tab-body",
        children=[
            html.H2("Business Recommendations"),
            html.Div(
                "Recommendations will appear once segment, pattern, and anomaly data are available. Run "
                "build_dashboard_cache.py after Phases 2-4 have produced their outputs, then reload this dashboard.",
                className="placeholder-box",
            ),
        ],
    )


def _finding_card(number: int, title: str, tag: str, insight, so_what, action) -> html.Div:
    return html.Div(
        className="finding-card",
        children=[
            html.Div(
                className="finding-head",
                children=[
                    html.Span(f"Finding {number}", className="finding-number"),
                    html.Span(tag, className="badge badge-info"),
                ],
            ),
            html.H4(title),
            html.Div(className="finding-block", children=[html.B("What we found: "), insight]),
            html.Div(className="finding-block", children=[html.B("Why it matters: "), so_what]),
            html.Div(className="finding-block finding-action", children=[html.B("Recommended action: "), action]),
        ],
    )


def recommendation_layout(DATA, FIGURES):
    cluster = DATA.get("cluster_summary")
    rules = DATA.get("rules")
    metrics_df = DATA.get("fraud_validation_metrics")
    method_overlap = DATA.get("method_overlap")

    if cluster is None or cluster.empty or rules is None or rules.empty:
        return _empty_state()

    metrics = metrics_lookup(metrics_df)
    enrichment = metrics.get("Fraud Enrichment", 0)
    recall = metrics.get("Recall", 0) * 100
    precision = metrics.get("Precision", 0) * 100

    seg0 = cluster[cluster["cluster_kmeans"] == 0]
    seg0 = seg0.iloc[0] if not seg0.empty else None
    seg2 = cluster[cluster["cluster_kmeans"] == 2]
    seg2 = seg2.iloc[0] if not seg2.empty else None

    best_rule_mask = rules["antecedents_str"].str.contains("origError_very_low", na=False) & rules[
        "antecedents_str"
    ].str.contains("orig_drained_yes", na=False)
    best_rule = rules[best_rule_mask].iloc[0] if best_rule_mask.any() else rules.sort_values("lift", ascending=False).iloc[0]

    smallest_method_label, smallest_method_count = None, None
    if method_overlap is not None and not method_overlap.empty and "method" in method_overlap.columns:
        diag = {row["method"]: row[row["method"]] for _, row in method_overlap.iterrows() if row["method"] in method_overlap.columns}
        if diag:
            smallest_method = min(diag, key=diag.get)
            smallest_method_label = METHOD_LABELS.get(smallest_method, smallest_method)
            smallest_method_count = diag[smallest_method]

    headline = html.Div(
        className="callout callout-critical",
        children=[
            html.Div("The central question: what wasn't obvious from the raw data?", className="callout-tag"),
            html.P(
                [
                    "None of the following would show up from scanning a spreadsheet of 6.3 million rows by eye. "
                    "They only surfaced by segmenting behavior, mining trait combinations, and scoring anomalies "
                    "with multiple independent methods at once:",
                ]
            ),
            html.Ul(
                children=[
                    html.Li(
                        [
                            "A ",
                            html.B("0.03%-sized transaction segment carries zero fraud labels"),
                            " yet is flagged high-risk ",
                            html.B(f"{seg0['High-risk queue rate']}" if seg0 is not None else "—"),
                            " of the time — a blind spot the fraud label alone would never reveal.",
                        ]
                    ),
                    html.Li(
                        [
                            "One specific two-trait combination predicts fraud with ",
                            html.B("100% confidence"),
                            " and ",
                            html.B(f"{best_rule['lift']:.0f}x"),
                            " the baseline rate — a near-deterministic, real-time-checkable rule.",
                        ]
                    ),
                    html.Li(
                        [
                            "The internal risk score is ",
                            html.B("not linear with fraud risk"),
                            " — a \u201cMedium\u201d score is, counter-intuitively, more fraud-concentrated than a "
                            "\u201cCritical\u201d one.",
                        ]
                    ),
                ]
            ),
        ],
    )

    cards = [
        _finding_card(
            1,
            "A tiny, fraud-unlabeled segment is the riskiest group in the data",
            "Segmentation",
            insight=[
                (seg0["Segment"] if seg0 is not None else "Segment 0"),
                f" is only {seg0['Share of activity']} of all transactions and has {seg0['Fraud rate']} confirmed "
                f"fraud — but {seg0['High-risk queue rate']} of it lands in the high-risk queue, the highest rate "
                "of any segment by a wide margin." if seg0 is not None else "No data available.",
            ],
            so_what=(
                "Fraud labels alone would tell you to ignore this group entirely. The multi-method risk score sees "
                "something the label doesn't: unusually large, hard-to-reconcile transfers that behave nothing like "
                "the mainstream population."
            ),
            action=(
                "Route this segment to a dedicated manual-review process rather than mainstream fraud monitoring, "
                "and investigate a sample to confirm whether it represents a distinct legitimate use case (e.g. "
                "large B2B transfers) or an emerging fraud pattern not yet reflected in historical labels."
            ),
        ),
        _finding_card(
            2,
            "One trait combination is a near-perfect, real-time fraud signal",
            "Pattern mining",
            insight=(
                f"When a sender's balance math is almost perfectly consistent (very low reconciliation error) at "
                f"the same time the sender's account is drained to zero, the transaction is confirmed fraud in "
                f"{best_rule['confidence'] * 100:.0f}% of matching cases — about {best_rule['lift']:.0f}x more "
                f"often than chance."
            ),
            so_what=(
                "This is rare enough to be missed in manual review, but consistent enough to automate. It is one "
                "of very few patterns in this analysis that approaches a deterministic rule rather than a "
                "probabilistic signal."
            ),
            action=(
                "Implement this exact combination as a real-time hard rule (auto-hold or step-up verification) "
                "rather than waiting for it to surface through periodic batch scoring."
            ),
        ),
        _finding_card(
            3,
            "Fraud risk is unevenly distributed across otherwise-similar segments",
            "Segmentation",
            insight=[
                (seg2["Segment"] if seg2 is not None else "The High-Balance Cash-In segment"),
                f" runs at {seg2['Fraud vs. baseline']} the baseline fraud rate — more than double the mainstream "
                "segment's rate — despite looking, on the surface, like ordinary high-balance banking activity."
                if seg2 is not None
                else "No data available.",
            ],
            so_what=(
                "Blanket, one-size-fits-all monitoring thresholds under-weight this segment's real risk and "
                "over-weight the mainstream segment's."
            ),
            action=(
                "Set segment-aware monitoring thresholds instead of a single global cutoff, with tighter review "
                "triggers for high-balance cash-in activity specifically."
            ),
        ),
        _finding_card(
            4,
            "The priority queue is a triage tool, not a verdict — and that's fine",
            "Anomaly scoring",
            insight=(
                f"The high-risk queue is only {precision:.1f}% precise in absolute terms, but it concentrates "
                f"fraud at {enrichment:.1f}x the baseline rate and captures {recall:.1f}% of all confirmed fraud "
                "in a queue that is a small fraction of total volume."
            ),
            so_what=(
                "Low absolute precision looks alarming out of context, but it is the expected result of fraud "
                "being extremely rare to begin with. The right yardstick is concentration versus random review, "
                "not precision versus 100%."
            ),
            action=(
                "Use the queue to prioritize investigator attention and resource allocation, not as an automatic "
                "fraud verdict. Pair it with the near-deterministic rule from Finding 2 for cases that warrant "
                "automatic action."
            ),
        ),
    ]

    if smallest_method_label:
        cards.append(
            _finding_card(
                5,
                "The segmentation-based outlier check is the most selective of the four",
                "Anomaly scoring",
                insight=(
                    f"\u201c{smallest_method_label}\u201d flags only {smallest_method_count:,.0f} transactions — "
                    "the smallest of the four detection methods used, by a wide margin."
                ),
                so_what=(
                    "A highly selective method is easy to overlook next to higher-volume checks, but its rarity is "
                    "exactly what makes any transaction it flags worth a second look."
                ),
                action=(
                    "Treat it as a priority booster: transactions it flags in combination with any other method "
                    "should be escalated ahead of single-method flags."
                ),
            )
        )

    chart = html.Div(
        className="table-card",
        children=[dcc.Graph(figure=FIGURES["enrichment_comparison"], config={"displayModeBar": False})],
    )

    return html.Div(
        className="tab-body",
        children=[
            html.H2("Business Recommendations"),
            html.P(
                "What the segments, patterns, and anomaly checks add up to — and what to do about it.",
                className="tab-subtitle",
            ),
            headline,
            html.H3("Findings and recommended actions"),
            html.Div(className="finding-grid", children=cards),
            chart,
        ],
    )
