from dash import html, dcc

from utils.constants import COLORS, FILE_DESCRIPTIONS
from layouts.components import create_upload_component, create_header, create_footer


def create_main_layout():
    """Create the main application layout"""
    return html.Div(
        [
            # Header
            create_header(),
            # Main content
            html.Div(
                [
                    # File upload section
                    html.Div(
                        [
                            html.H2(
                                "Data Upload",
                                style={
                                    "borderBottom": f"2px solid {COLORS['primary']}",
                                    "paddingBottom": "10px",
                                },
                            ),
                            html.P(
                                "Upload the required CSV files for your building analysis. Each file should have the format shown in the expandable sections."
                            ),
                            # First row of uploads
                            html.Div(
                                [
                                    create_upload_component(
                                        "upload-iat",
                                        "Zone Temperatures",
                                        FILE_DESCRIPTIONS["iat"],
                                    ),
                                    create_upload_component(
                                        "upload-hsp",
                                        "Zone Heating Setpoints",
                                        FILE_DESCRIPTIONS["hsp"],
                                    ),
                                ],
                                style={
                                    "display": "grid",
                                    "gridTemplateColumns": "1fr 1fr",
                                    "gap": "20px",
                                    "marginBottom": "20px",
                                },
                            ),
                            # Second row of uploads
                            html.Div(
                                [
                                    create_upload_component(
                                        "upload-csp",
                                        "Zone Cooling Setpoints",
                                        FILE_DESCRIPTIONS["csp"],
                                    ),
                                    create_upload_component(
                                        "upload-airflow",
                                        "Zone Airflow",
                                        FILE_DESCRIPTIONS["airflow"],
                                    ),
                                ],
                                style={
                                    "display": "grid",
                                    "gridTemplateColumns": "1fr 1fr",
                                    "gap": "20px",
                                    "marginBottom": "20px",
                                },
                            ),
                            # Third row of uploads
                            html.Div(
                                [
                                    create_upload_component(
                                        "upload-ahu-dat",
                                        "AHU Discharge Temps",
                                        FILE_DESCRIPTIONS["ahu_dat"],
                                    ),
                                    create_upload_component(
                                        "upload-map",
                                        "Zone to AHU Map",
                                        FILE_DESCRIPTIONS["map"],
                                    ),
                                ],
                                style={
                                    "display": "grid",
                                    "gridTemplateColumns": "1fr 1fr",
                                    "gap": "20px",
                                    "marginBottom": "20px",
                                },
                            ),
                            # Fourth row - just the cooling data
                            html.Div(
                                [
                                    create_upload_component(
                                        "upload-cooling",
                                        "Building Total Cooling",
                                        FILE_DESCRIPTIONS["cooling"],
                                    ),
                                ],
                                style={"marginBottom": "20px"},
                            ),
                            # Analysis controls
                            html.Div(
                                [
                                    html.Label(
                                        "Resample Frequency: ",
                                        style={
                                            "fontWeight": "bold",
                                            "marginRight": "10px",
                                        },
                                    ),
                                    dcc.Dropdown(
                                        id="resample-freq-dropdown",
                                        options=[
                                            {
                                                "label": "Hourly (No Resampling)",
                                                "value": "H",
                                            },
                                            {"label": "Daily", "value": "D"},
                                            {"label": "Weekly", "value": "W"},
                                            {"label": "Monthly", "value": "M"},
                                        ],
                                        value="W",
                                        style={
                                            "width": "200px",
                                            "display": "inline-block",
                                        },
                                    ),
                                    html.Button(
                                        "Run Analysis",
                                        id="run-button",
                                        n_clicks=0,
                                        style={
                                            "marginLeft": "20px",
                                            "backgroundColor": COLORS["primary"],
                                            "color": "white",
                                            "border": "none",
                                            "padding": "10px 20px",
                                            "borderRadius": "5px",
                                            "fontWeight": "bold",
                                            "cursor": "pointer",
                                            "boxShadow": "0 2px 4px rgba(0,0,0,0.1)",
                                        },
                                    ),
                                ],
                                style={
                                    "marginTop": "30px",
                                    "padding": "15px",
                                    "backgroundColor": COLORS["light"],
                                    "borderRadius": "5px",
                                },
                            ),
                            # Status message
                            html.Div(
                                id="status-output",
                                style={
                                    "marginTop": "20px",
                                    "padding": "10px",
                                    "borderRadius": "5px",
                                    "backgroundColor": COLORS["light"],
                                    "textAlign": "center",
                                    "fontWeight": "bold",
                                },
                            ),
                        ],
                        style={
                            "backgroundColor": "white",
                            "padding": "25px",
                            "borderRadius": "8px",
                            "boxShadow": "0 4px 6px rgba(0,0,0,0.1)",
                            "marginBottom": "30px",
                        },
                    ),
                    # Results section
                    dcc.Loading(
                        id="loading-graphs",
                        type="circle",
                        color=COLORS["primary"],
                        children=[
                            html.Div(
                                [
                                    html.H2(
                                        "Analysis Results",
                                        style={
                                            "borderBottom": f"2px solid {COLORS['primary']}",
                                            "paddingBottom": "10px",
                                            "marginTop": "40px",
                                        },
                                    ),
                                    # Graphs in a grid layout
                                    html.Div(
                                        [
                                            # First row of graphs
                                            html.Div(
                                                [
                                                    html.Div(
                                                        [
                                                            html.H3(
                                                                "Cooling by Detailed IAT Bins (Absolute)",
                                                                style={
                                                                    "fontSize": "1.1rem",
                                                                    "textAlign": "center",
                                                                },
                                                            ),
                                                            dcc.Graph(
                                                                id="graph-bins-absolute"
                                                            ),
                                                        ],
                                                        style={
                                                            "backgroundColor": "white",
                                                            "padding": "15px",
                                                            "borderRadius": "8px",
                                                            "boxShadow": "0 2px 4px rgba(0,0,0,0.05)",
                                                        },
                                                    ),
                                                    html.Div(
                                                        [
                                                            html.H3(
                                                                "Cooling by Detailed IAT Bins (Fractional)",
                                                                style={
                                                                    "fontSize": "1.1rem",
                                                                    "textAlign": "center",
                                                                },
                                                            ),
                                                            dcc.Graph(
                                                                id="graph-bins-fractional"
                                                            ),
                                                        ],
                                                        style={
                                                            "backgroundColor": "white",
                                                            "padding": "15px",
                                                            "borderRadius": "8px",
                                                            "boxShadow": "0 2px 4px rgba(0,0,0,0.05)",
                                                        },
                                                    ),
                                                ],
                                                style={
                                                    "display": "grid",
                                                    "gridTemplateColumns": "1fr 1fr",
                                                    "gap": "20px",
                                                    "marginBottom": "20px",
                                                },
                                            ),
                                            # Second row of graphs
                                            html.Div(
                                                [
                                                    html.Div(
                                                        [
                                                            html.H3(
                                                                "Cooling by Regrouped Category (Absolute)",
                                                                style={
                                                                    "fontSize": "1.1rem",
                                                                    "textAlign": "center",
                                                                },
                                                            ),
                                                            dcc.Graph(
                                                                id="graph-regrouped-absolute"
                                                            ),
                                                        ],
                                                        style={
                                                            "backgroundColor": "white",
                                                            "padding": "15px",
                                                            "borderRadius": "8px",
                                                            "boxShadow": "0 2px 4px rgba(0,0,0,0.05)",
                                                        },
                                                    ),
                                                    html.Div(
                                                        [
                                                            html.H3(
                                                                "Cooling by Regrouped Category (Fractional)",
                                                                style={
                                                                    "fontSize": "1.1rem",
                                                                    "textAlign": "center",
                                                                },
                                                            ),
                                                            dcc.Graph(
                                                                id="graph-regrouped-fractional"
                                                            ),
                                                        ],
                                                        style={
                                                            "backgroundColor": "white",
                                                            "padding": "15px",
                                                            "borderRadius": "8px",
                                                            "boxShadow": "0 2px 4px rgba(0,0,0,0.05)",
                                                        },
                                                    ),
                                                ],
                                                style={
                                                    "display": "grid",
                                                    "gridTemplateColumns": "1fr 1fr",
                                                    "gap": "20px",
                                                    "marginBottom": "20px",
                                                },
                                            ),
                                            # Zone Ranking Tables
                                            html.Div(
                                                [
                                                    # Most Wasteful Zones
                                                    html.Div(
                                                        [
                                                            html.Div(
                                                                id="wasteful-zones-plot-div",
                                                                style={
                                                                    "backgroundColor": "white",
                                                                    "padding": "15px",
                                                                    "borderRadius": "8px",
                                                                    "boxShadow": "0 2px 4px rgba(0,0,0,0.05)",
                                                                    "marginBottom": "15px",
                                                                },
                                                            ),
                                                            html.Div(
                                                                id="wasteful-zones-table-div",
                                                                style={
                                                                    "backgroundColor": "white",
                                                                    "padding": "20px",
                                                                    "borderRadius": "8px",
                                                                    "boxShadow": "0 2px 4px rgba(0,0,0,0.05)",
                                                                },
                                                            ),
                                                        ]
                                                    ),
                                                    # Most Demanding Zones
                                                    html.Div(
                                                        [
                                                            html.Div(
                                                                id="demanding-zones-plot-div",
                                                                style={
                                                                    "backgroundColor": "white",
                                                                    "padding": "15px",
                                                                    "borderRadius": "8px",
                                                                    "boxShadow": "0 2px 4px rgba(0,0,0,0.05)",
                                                                    "marginBottom": "15px",
                                                                },
                                                            ),
                                                            html.Div(
                                                                id="demanding-zones-table-div",
                                                                style={
                                                                    "backgroundColor": "white",
                                                                    "padding": "20px",
                                                                    "borderRadius": "8px",
                                                                    "boxShadow": "0 2px 4px rgba(0,0,0,0.05)",
                                                                },
                                                            ),
                                                        ]
                                                    ),
                                                ],
                                                style={
                                                    "display": "grid",
                                                    "gridTemplateColumns": "1fr 1fr",
                                                    "gap": "20px",
                                                    "marginBottom": "20px",
                                                },
                                            ),
                                        ]
                                    ),
                                    # Summary table
                                    html.Div(
                                        id="summary-table-div",
                                        style={
                                            "backgroundColor": "white",
                                            "padding": "20px",
                                            "borderRadius": "8px",
                                            "boxShadow": "0 2px 4px rgba(0,0,0,0.05)",
                                            "marginTop": "20px",
                                        },
                                    ),
                                ]
                            ),
                        ],
                    ),
                    # Footer with explanation
                    create_footer(),
                ],
                style={"maxWidth": "1200px", "margin": "0 auto", "padding": "20px"},
            ),
        ],
        style={
            "backgroundColor": COLORS["background"],
            "minHeight": "100vh",
            "fontFamily": "Arial, sans-serif",
        },
    )
