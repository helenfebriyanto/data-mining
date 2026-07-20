from dash import html


def unusual_layout(DATA, FIGURES):

    return html.Div(

        className="tab-body",

        children=[

            html.H2("Unusual Activities"),

            html.P(
                "This page summarizes unusual transactions that require further review."
            ),

            html.Hr(),

            html.Div(
                "🚧 Anomaly dashboard will be added here.",
                className="placeholder-box",
            ),
        ],
    )