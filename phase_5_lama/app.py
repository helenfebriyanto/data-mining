from __future__ import annotations

import os
from pathlib import Path
import pandas as pd

from dash import Dash, html, dcc, Input, Output

import fallback_data

from business_labels import (
    add_rule_business_columns,
)

from utils.figures import build_figures

# layouts
from layouts.executive import executive_layout
from layouts.segmentation import segmentation_layout
from layouts.patterns import patterns_layout
from layouts.unusual import unusual_layout
from layouts.recommendation import recommendation_layout
from layouts.explorer import explorer_layout


BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = Path(os.environ.get("DASHBOARD_CACHE_DIR", BASE_DIR / "cache"))


# =====================================================
# Helper
# =====================================================

def read_parquet_or_csv(name, fallback):

    parquet = CACHE_DIR / f"{name}.parquet"
    csv = CACHE_DIR / f"{name}.csv"

    if parquet.exists():
        return pd.read_parquet(parquet)

    if csv.exists():
        return pd.read_csv(csv)

    return fallback()


def load_data():

    data = {

        "risk_summary":
            read_parquet_or_csv(
                "risk_summary",
                fallback_data.risk_summary
            ),

        "cluster_summary":
            read_parquet_or_csv(
                "cluster_summary",
                fallback_data.cluster_summary
            ),

        "rules":
            read_parquet_or_csv(
                "top_rules_business",
                fallback_data.rules
            ),

        "fraud_by_score":
            read_parquet_or_csv(
                "fraud_by_score",
                fallback_data.fraud_by_score
            ),

        "method_overlap":
            read_parquet_or_csv(
                "method_overlap",
                fallback_data.method_overlap
            ),

        "anomaly_type_summary":
            read_parquet_or_csv(
                "anomaly_type_summary",
                fallback_data.anomaly_type_summary
            ),

        "investigation_summary":
            read_parquet_or_csv(
                "investigation_summary",
                fallback_data.investigation_summary
            ),

        "top_suspicious":
            read_parquet_or_csv(
                "top_suspicious_light",
                fallback_data.top_suspicious
            ),

        "fraud_validation_metrics":
            read_parquet_or_csv(
                "fraud_validation_metrics",
                fallback_data.fraud_validation_metrics
            ),

        "data_quality":
            fallback_data.data_quality_findings()

    }

    data["rules"] = add_rule_business_columns(data["rules"])

    return data

# Load Everything Once
DATA = load_data()

FIGURES = build_figures(DATA)

# Dash

app = Dash(
    __name__,
    suppress_callback_exceptions=True,
    title="PaySim Banking Discovery Dashboard"
)

server = app.server

# Layout

app.layout = html.Div(

    className="app-shell",

    children=[

        html.Div(

            className="hero",

            children=[

                html.Div(
                    "Phase 5 - Knowledge Discovery Dashboard",
                ),

                html.H1(
                    "PaySim Banking Discovery Dashboard"
                ),

                html.P(
                    "Business insights from customer segmentation, transaction patterns and anomaly detection."
                ),

            ]

        ),

        dcc.Tabs(

            id="tabs",
            value="executive",

            children=[

                dcc.Tab(
                    label="Executive Summary",
                    value="executive"
                ),

                dcc.Tab(
                    label="Customer Segments",
                    value="segmentation"
                ),

                dcc.Tab(
                    label="Hidden Patterns",
                    value="patterns"
                ),

                dcc.Tab(
                    label="Unusual Activities",
                    value="unusual"
                ),

                dcc.Tab(
                    label="Recommendations",
                    value="recommendation"
                ),

                dcc.Tab(
                    label="Data Explorer",
                    value="explorer"
                ),

            ]

        ),

        html.Div(id="tab-content")

    ]

)


# =====================================================
# Tab Routing
# =====================================================

@app.callback(

    Output("tab-content", "children"),

    Input("tabs", "value")

)
def render_tab(tab):

    if tab == "segmentation":
        return segmentation_layout(DATA, FIGURES)

    elif tab == "patterns":
        return patterns_layout(DATA, FIGURES)

    elif tab == "unusual":
        return unusual_layout(DATA, FIGURES)

    elif tab == "recommendation":
        return recommendation_layout(DATA, FIGURES)

    elif tab == "explorer":
        return explorer_layout(DATA, FIGURES)

    return executive_layout(DATA, FIGURES)


# =====================================================
# Run
# =====================================================

if __name__ == "__main__":

    app.run(
        debug=False,
        host="127.0.0.1",
        port=8050
    )