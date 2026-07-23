from dash import html


def explorer_layout(DATA, FIGURES):

    return html.Div(

        className="tab-body",

        children=[

            html.H2("Data Explorer"),

            html.P(
                "Browse transaction records using interactive filters."
            ),

            html.Hr(),

            html.Div(
                "🚧 Interactive table will be added here.",
                className="placeholder-box",
            ),
        ],
    )