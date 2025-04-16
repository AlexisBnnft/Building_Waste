from dash import html, dcc

from utils.constants import COLORS, FILE_DESCRIPTIONS


def create_upload_component(id_name, label, description):
    """Create a file upload component with consistent styling"""
    # Extract the component type from the id (e.g., "iat" from "upload-iat")
    # Handle special case for ahu-dat and ensure we get the full component name
    if "ahu-dat" in id_name:
        component_id = "ahu-dat"
    else:
        component_id = id_name.split("-")[1]

    return html.Div(
        [
            html.Div(
                [
                    html.Label(label, className="upload-label"),
                    html.Div(
                        [
                            dcc.Upload(
                                id=id_name,
                                children=html.Div(
                                    [
                                        html.I(
                                            className="fas fa-file-upload",
                                            style={"marginRight": "10px"},
                                        ),
                                        "Drag and Drop or ",
                                        html.A("Select File"),
                                    ]
                                ),
                                style={
                                    "width": "100%",
                                    "height": "60px",
                                    "lineHeight": "60px",
                                    "borderWidth": "1px",
                                    "borderStyle": "dashed",
                                    "borderRadius": "5px",
                                    "textAlign": "center",
                                    "backgroundColor": COLORS["light"],
                                    "cursor": "pointer",
                                },
                                multiple=False,
                            ),
                            html.Span(
                                id=f"status-{component_id}",
                                style={
                                    "marginLeft": "10px",
                                    "color": COLORS["primary"],
                                },
                            ),
                        ]
                    ),
                ]
            ),
            html.Details(
                [
                    html.Summary(
                        "View Expected Format",
                        style={"cursor": "pointer", "color": COLORS["primary"]},
                    ),
                    html.Pre(
                        description,
                        style={
                            "backgroundColor": "#f8f9fa",
                            "padding": "10px",
                            "borderRadius": "5px",
                            "fontSize": "12px",
                            "maxHeight": "200px",
                            "overflow": "auto",
                            "whiteSpace": "pre-wrap",
                        },
                    ),
                ],
                style={"marginTop": "5px"},
            ),
        ],
        className="upload-container",
    )


def create_header():
    """Create the application header"""
    return html.Div(
        [
            html.H1(
                "Building Cooling Distribution Analysis",
                style={"color": COLORS["dark"]},
            ),
            html.P(
                "Upload building data files to analyze cooling distribution across temperature zones. "
                "This dashboard visualizes how cooling is distributed relative to temperature setpoints.",
                style={
                    "fontSize": "1.1em",
                    "color": COLORS["text"],
                    "maxWidth": "800px",
                    "margin": "0 auto 20px auto",
                },
            ),
        ],
        style={
            "textAlign": "center",
            "padding": "20px 0",
            "backgroundColor": COLORS["light"],
            "borderBottom": f"3px solid {COLORS['primary']}",
        },
    )


def create_footer():
    """Create the application footer with explanations"""
    return html.Div(
        [
            html.Hr(style={"margin": "40px 0 20px 0"}),
            html.H3("About This Dashboard", style={"color": COLORS["dark"]}),
            html.P(
                [
                    "This tool analyzes how cooling energy is distributed across temperature zones in a building. ",
                    "It categorizes cooling into bins based on the relationship between zone temperatures and setpoints:",
                ]
            ),
            html.Ul(
                [
                    html.Li(
                        [
                            "Bin 1 (IAT<HSP): ",
                            html.Span(
                                "Wasted cooling - zone temp below heating setpoint",
                                style={"color": "#e74c3c"},
                            ),
                        ]
                    ),
                    html.Li(
                        [
                            "Bin 2-3 (0-50%): ",
                            html.Span(
                                "Excess cooling - zone temp in lower half between setpoints",
                                style={"color": "#f39c12"},
                            ),
                        ]
                    ),
                    html.Li(
                        [
                            "Bin 4-6 (50-100%+): ",
                            html.Span(
                                "Useful cooling - zone temp in upper half or above setpoints",
                                style={"color": "#27ae60"},
                            ),
                        ]
                    ),
                ]
            ),
            html.P(
                "The analysis helps identify opportunities for energy savings and improved comfort."
            ),
            html.P(
                [
                    "Created with ",
                    html.A("Dash", href="https://dash.plotly.com/", target="_blank"),
                    " and ",
                    html.A("Plotly", href="https://plotly.com/", target="_blank"),
                ],
                style={
                    "fontSize": "0.9em",
                    "textAlign": "center",
                    "marginTop": "30px",
                    "color": COLORS["dark"],
                },
            ),
        ],
        style={
            "marginTop": "40px",
            "backgroundColor": COLORS["light"],
            "padding": "20px",
            "borderRadius": "8px",
        },
    )
