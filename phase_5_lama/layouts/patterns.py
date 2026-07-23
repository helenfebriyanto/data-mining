from dash import html


def patterns_layout(DATA, FIGURES):

    return html.Div(

        className="tab-body",

        children=[

            html.H2("Hidden Transaction Patterns"),

            html.P(
                "This page presents transaction behaviors that frequently occur together."
            ),

            html.Hr(),

            html.Div(
                "🚧 Association rule visualization will be added here.",
                className="placeholder-box",
            ),
        ],
    )