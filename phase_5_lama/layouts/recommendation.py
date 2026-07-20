from dash import html


def recommendation_layout(DATA, FIGURES):

    return html.Div(

        className="tab-body",

        children=[

            html.H2("Business Recommendations"),

            html.P(
                "Recommended actions based on discovered transaction patterns."
            ),

            html.Hr(),

            html.Div(
                "🚧 Business recommendations will appear here.",
                className="placeholder-box",
            ),
        ],
    )