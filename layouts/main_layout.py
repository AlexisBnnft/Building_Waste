from dash import html, dcc, Input, Output, State

from utils.constants import COLORS, FILE_DESCRIPTIONS
from layouts.components import create_upload_component, create_header, create_footer


def create_app_layout():
    """
    Create the main application layout
    """
    return html.Div(
        [
            # Header section
            html.Div(
                [
                    html.H1(
                        "Building Cooling Analysis",
                        className="app-header",
                        style={"color": COLORS["text"], "marginBottom": "10px"},
                    ),
                    html.P(
                        "Analyze and visualize cooling energy in buildings",
                        style={"color": COLORS["dark"]},
                    ),
                ],
                style={"textAlign": "center", "padding": "20px"},
            ),
            # Main tabs
            dcc.Tabs(
                id="app-tabs",
                value="tab-preloaded",  # Default tab
                children=[
                    dcc.Tab(
                        label="Pre-loaded Analysis",
                        value="tab-preloaded",
                        className="custom-tab",
                        selected_className="custom-tab--selected",
                        children=[
                            html.Div(
                                [
                                    # Building selector tabs
                                    html.Div(
                                        [
                                            html.H3("Select Building:"),
                                            dcc.Tabs(
                                                id="building-tabs",
                                                value=None,
                                                className="building-tabs",
                                            ),
                                        ],
                                        style={"marginBottom": "20px"},
                                    ),
                                    # Content will be loaded here
                                    html.Div(id="preloaded-analysis-content"),
                                ],
                                style={"padding": "20px", "width": "100%"},
                            ),
                        ],
                    ),
                    dcc.Tab(
                        label="Upload Data",
                        value="tab-upload",
                        className="custom-tab",
                        selected_className="custom-tab--selected",
                        children=[
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.H3("Upload Your Data Files"),
                                            html.Div(
                                                [
                                                    dcc.Upload(
                                                        id="upload-cooling",
                                                        children=html.Div(
                                                            [
                                                                "Drag and Drop or ",
                                                                html.A(
                                                                    "Select Cooling Data"
                                                                ),
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
                                                            "margin": "10px 0",
                                                            "backgroundColor": COLORS[
                                                                "light"
                                                            ],
                                                        },
                                                        multiple=False,
                                                    ),
                                                    html.Div(
                                                        id="cooling-upload-status",
                                                        style={"margin": "5px 0"},
                                                    ),
                                                ],
                                                style={"margin": "10px 0"},
                                            ),
                                            html.Div(
                                                [
                                                    dcc.Upload(
                                                        id="upload-iat",
                                                        children=html.Div(
                                                            [
                                                                "Drag and Drop or ",
                                                                html.A(
                                                                    "Select Indoor Air Temperature Data"
                                                                ),
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
                                                            "margin": "10px 0",
                                                            "backgroundColor": COLORS[
                                                                "light"
                                                            ],
                                                        },
                                                        multiple=False,
                                                    ),
                                                    html.Div(
                                                        id="iat-upload-status",
                                                        style={"margin": "5px 0"},
                                                    ),
                                                ],
                                                style={"margin": "10px 0"},
                                            ),
                                            html.Div(
                                                [
                                                    dcc.Upload(
                                                        id="upload-csp",
                                                        children=html.Div(
                                                            [
                                                                "Drag and Drop or ",
                                                                html.A(
                                                                    "Select Cooling Setpoint Data"
                                                                ),
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
                                                            "margin": "10px 0",
                                                            "backgroundColor": COLORS[
                                                                "light"
                                                            ],
                                                        },
                                                        multiple=False,
                                                    ),
                                                    html.Div(
                                                        id="csp-upload-status",
                                                        style={"margin": "5px 0"},
                                                    ),
                                                ],
                                                style={"margin": "10px 0"},
                                            ),
                                            html.Div(
                                                [
                                                    dcc.Upload(
                                                        id="upload-hsp",
                                                        children=html.Div(
                                                            [
                                                                "Drag and Drop or ",
                                                                html.A(
                                                                    "Select Heating Setpoint Data (Optional)"
                                                                ),
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
                                                            "margin": "10px 0",
                                                            "backgroundColor": COLORS[
                                                                "light"
                                                            ],
                                                        },
                                                        multiple=False,
                                                    ),
                                                    html.Div(
                                                        id="hsp-upload-status",
                                                        style={"margin": "5px 0"},
                                                    ),
                                                ],
                                                style={"margin": "10px 0"},
                                            ),
                                            # Zone Airflow Upload
                                            html.Div(
                                                [
                                                    dcc.Upload(
                                                        id="upload-airflow",
                                                        children=html.Div(
                                                            [
                                                                "Drag and Drop or ",
                                                                html.A(
                                                                    "Select Zone Airflow Data"
                                                                ),
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
                                                            "margin": "10px 0",
                                                            "backgroundColor": COLORS[
                                                                "light"
                                                            ],
                                                        },
                                                        multiple=False,
                                                    ),
                                                    html.Div(
                                                        id="airflow-upload-status",
                                                        style={"margin": "5px 0"},
                                                    ),
                                                ],
                                                style={"margin": "10px 0"},
                                            ),
                                            # AHU Discharge Temperatures Upload
                                            html.Div(
                                                [
                                                    dcc.Upload(
                                                        id="upload-ahu-dat",
                                                        children=html.Div(
                                                            [
                                                                "Drag and Drop or ",
                                                                html.A(
                                                                    "Select AHU Discharge Temperature Data"
                                                                ),
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
                                                            "margin": "10px 0",
                                                            "backgroundColor": COLORS[
                                                                "light"
                                                            ],
                                                        },
                                                        multiple=False,
                                                    ),
                                                    html.Div(
                                                        id="ahu-dat-upload-status",
                                                        style={"margin": "5px 0"},
                                                    ),
                                                ],
                                                style={"margin": "10px 0"},
                                            ),
                                            # Zone to AHU Map Upload
                                            html.Div(
                                                [
                                                    dcc.Upload(
                                                        id="upload-map",
                                                        children=html.Div(
                                                            [
                                                                "Drag and Drop or ",
                                                                html.A(
                                                                    "Select Zone to AHU Map Data"
                                                                ),
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
                                                            "margin": "10px 0",
                                                            "backgroundColor": COLORS[
                                                                "light"
                                                            ],
                                                        },
                                                        multiple=False,
                                                    ),
                                                    html.Div(
                                                        id="map-upload-status",
                                                        style={"margin": "5px 0"},
                                                    ),
                                                ],
                                                style={"margin": "10px 0"},
                                            ),
                                            # Resample frequency settings
                                            html.Div(
                                                [
                                                    html.Label(
                                                        "Data Aggregation: ",
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
                                                            {
                                                                "label": "Daily",
                                                                "value": "D",
                                                            },
                                                            {
                                                                "label": "Weekly",
                                                                "value": "W",
                                                            },
                                                            {
                                                                "label": "Monthly",
                                                                "value": "M",
                                                            },
                                                        ],
                                                        value="W",
                                                        style={
                                                            "width": "100%",
                                                        },
                                                    ),
                                                ],
                                                style={"margin": "20px 0 10px 0"},
                                            ),
                                            html.Button(
                                                "Process Data",
                                                id="process-data-button",
                                                n_clicks=0,
                                                style={
                                                    "marginTop": "20px",
                                                    "backgroundColor": COLORS[
                                                        "primary"
                                                    ],
                                                    "color": "white",
                                                    "border": "none",
                                                    "padding": "10px 20px",
                                                    "borderRadius": "5px",
                                                    "cursor": "pointer",
                                                },
                                            ),
                                            # Status message
                                            html.Div(
                                                id="status-output",
                                                style={
                                                    "marginTop": "15px",
                                                    "padding": "10px",
                                                    "borderRadius": "5px",
                                                    "fontWeight": "bold",
                                                },
                                            ),
                                        ],
                                        style={
                                            "width": "100%",
                                            "display": "block",
                                            "verticalAlign": "top",
                                            "padding": "20px",
                                        },
                                        id="upload-form-container",
                                    ),
                                    html.Div(
                                        id="upload-analysis-results",
                                        style={
                                            "width": "100%",
                                            "display": "block",
                                            "padding": "20px",
                                            "marginTop": "20px",
                                        },
                                    ),
                                ],
                                style={"width": "100%"},
                            ),
                        ],
                    ),
                    dcc.Tab(
                        label="About",
                        value="tab-about",
                        className="custom-tab",
                        selected_className="custom-tab--selected",
                        children=[
                            html.Div(
                                [
                                    html.H2(
                                        "Building Cooling Energy Analysis",
                                        style={"textAlign": "center"},
                                    ),
                                    # Add MathJax script for LaTeX rendering
                                    html.Script(
                                        src="https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.5/MathJax.js?config=TeX-MML-AM_CHTML"
                                    ),
                                    html.Div(
                                        [
                                            dcc.Markdown(
                                                """
                                        ## 1. Introduction
                                        
                                        This application provides a comprehensive analysis framework for evaluating building cooling energy usage patterns. By categorizing cooling energy consumption based on the relationship between indoor air temperature (IAT) and setpoint temperatures, we can identify energy waste, inefficiencies, and opportunities for optimization.
                                        
                                        The fundamental premise of this analysis is that cooling energy should be utilized when it provides meaningful comfort benefits. When cooling energy is consumed while indoor conditions are already below setpoint temperatures, this represents waste and inefficiency.
                                        
                                        ## 2. Methodology
                                        
                                        Our methodology employs a binning approach where cooling energy is categorized based on the temperature difference between the indoor air temperature (IAT) and the cooling setpoint (CSP). We define the normalized temperature position (T<sub>norm</sub>) as:
                                        
                                        T<sub>norm</sub> = (IAT - HSP) / (CSP - HSP) × 100%
                                        
                                        Where:
                                        - IAT is the Indoor Air Temperature
                                        - HSP is the Heating Setpoint
                                        - CSP is the Cooling Setpoint
                                        
                                        Based on this normalized position, we classify cooling energy into six categories:
                                        
                                        | Category | Condition | Classification | Interpretation |
                                        |----------|-----------|----------------|----------------|
                                        | Bin 1 | IAT < HSP | **Wasteful** | Cooling when temperature is already below heating setpoint |
                                        | Bin 2 | 0% < T<sub>norm</sub> < 25% | **Excess** | Cooling when temperature is in lower part of deadband |
                                        | Bin 3 | 25% < T<sub>norm</sub> < 50% | **Excess** | Cooling when temperature is in lower-middle of deadband |
                                        | Bin 4 | 50% < T<sub>norm</sub> < 75% | **Useful** | Cooling when temperature is in upper-middle of deadband |
                                        | Bin 5 | 75% < T<sub>norm</sub> < 100% | **Useful** | Cooling when temperature is in upper part of deadband |
                                        | Bin 6 | IAT > CSP | **Useful** | Cooling when temperature exceeds cooling setpoint |
                                        
                                        ## 3. Key Benefits
                                        
                                        This analysis provides several key benefits:
                                        
                                        1. **Waste Identification**: Cooling energy used when IAT < HSP represents pure waste. The analysis quantifies this waste in both absolute terms (energy units) and as a percentage of total cooling energy.
                                        
                                        2. **Efficiency Optimization**: Energy used in Bins 2-3 may indicate opportunities for setpoint adjustments or control improvements, as cooling is being used when indoor conditions may already be comfortable.
                                        
                                        3. **Zone-Level Insights**: By analyzing at the zone level, we can identify specific areas of the building with the most significant waste or inefficiencies.
                                        
                                        4. **Temporal Patterns**: Visualizing cooling energy usage over time reveals seasonal patterns, operational changes, or system degradation.
                                        
                                        ## 4. Applications
                                        
                                        This tool can be used for:
                                        
                                        - **Commissioning & Retro-commissioning**: Identify control issues, sensor problems, or system faults
                                        - **Energy Management**: Target high-waste zones for operational improvements
                                        - **Financial Analysis**: Quantify potential cost savings from reducing wasteful cooling
                                        - **Measurement & Verification**: Assess before/after impacts of energy efficiency measures
                                        
                                        ## 5. Mathematical Framework
                                        
                                        The total cooling energy waste (W) can be expressed as:
                                        
                                        W = ∑<sub>t=1</sub><sup>T</sup> ∑<sub>z=1</sub><sup>Z</sup> E<sub>t,z</sub> · I(IAT<sub>t,z</sub> < HSP<sub>t,z</sub>)
                                        
                                        Where:
                                        - E<sub>t,z</sub> is the cooling energy for zone z at time t
                                        - I(·) is an indicator function that equals 1 when the condition is true and 0 otherwise
                                        
                                        The fractional waste (W<sub>f</sub>) is calculated as:
                                        
                                        W<sub>f</sub> = W/E<sub>total</sub> × 100%
                                        
                                        Where E<sub>total</sub> is the total cooling energy consumption.
                                        """,
                                                style={
                                                    "fontSize": "0.9rem",
                                                    "lineHeight": "1.5",
                                                    "width": "90%",
                                                    "margin": "0 auto",
                                                },
                                                dangerously_allow_html=True,
                                            ),
                                        ],
                                        style={
                                            "overflowY": "auto",
                                            "maxHeight": "600px",
                                        },
                                    ),
                                ],
                                style={"padding": "20px"},
                            )
                        ],
                    ),
                ],
            ),
            # Store data in browser's session
            dcc.Store(id="processed-data-store"),
        ],
        style={
            "backgroundColor": COLORS["background"],
            "color": COLORS["text"],
            "fontFamily": "'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', sans-serif",
            "maxWidth": "1400px",
            "margin": "0 auto",
            "minHeight": "100vh",
            "padding": "20px",
        },
    )


def create_results_layout():
    """
    Create layout for displaying analysis results
    """
    return html.Div(
        [
            html.H2("Analysis Results", style={"textAlign": "center"}),
            html.Div(
                [
                    # First row - Absolute and Normalized stacked area charts
                    html.Div(
                        [
                            # Absolute values stacked area chart
                            html.Div(
                                [
                                    html.H3(
                                        "Cooling Energy by Temperature Bin (Absolute)",
                                        style={
                                            "textAlign": "center",
                                            "fontSize": "1rem",
                                        },
                                    ),
                                    dcc.Graph(id="bins-stacked-area-absolute"),
                                ],
                                style={
                                    "width": "48%",
                                    "display": "inline-block",
                                    "verticalAlign": "top",
                                    "border": f"1px solid {COLORS['border']}",
                                    "borderRadius": "5px",
                                    "padding": "15px",
                                    "backgroundColor": COLORS["light"],
                                    "boxSizing": "border-box",
                                },
                            ),
                            # Normalized values stacked area chart
                            html.Div(
                                [
                                    html.H3(
                                        "Cooling Energy by Temperature Bin (Normalized)",
                                        style={
                                            "textAlign": "center",
                                            "fontSize": "1rem",
                                        },
                                    ),
                                    dcc.Graph(id="bins-stacked-area-fractional"),
                                ],
                                style={
                                    "width": "48%",
                                    "display": "inline-block",
                                    "verticalAlign": "top",
                                    "border": f"1px solid {COLORS['border']}",
                                    "borderRadius": "5px",
                                    "padding": "15px",
                                    "backgroundColor": COLORS["light"],
                                    "marginLeft": "4%",
                                    "boxSizing": "border-box",
                                },
                            ),
                        ],
                        style={
                            "marginBottom": "20px",
                            "width": "100%",
                            "textAlign": "center",
                        },
                    ),
                    # Second row - Regrouped stacked area charts
                    html.Div(
                        [
                            # Regrouped absolute values
                            html.Div(
                                [
                                    html.H3(
                                        "Cooling Energy by Category (Absolute)",
                                        style={
                                            "textAlign": "center",
                                            "fontSize": "1rem",
                                        },
                                    ),
                                    dcc.Graph(id="regrouped-stacked-area-absolute"),
                                ],
                                style={
                                    "width": "48%",
                                    "display": "inline-block",
                                    "verticalAlign": "top",
                                    "border": f"1px solid {COLORS['border']}",
                                    "borderRadius": "5px",
                                    "padding": "15px",
                                    "backgroundColor": COLORS["light"],
                                    "boxSizing": "border-box",
                                },
                            ),
                            # Regrouped normalized values
                            html.Div(
                                [
                                    html.H3(
                                        "Cooling Energy by Category (Normalized)",
                                        style={
                                            "textAlign": "center",
                                            "fontSize": "1rem",
                                        },
                                    ),
                                    dcc.Graph(id="regrouped-stacked-area-fractional"),
                                ],
                                style={
                                    "width": "48%",
                                    "display": "inline-block",
                                    "verticalAlign": "top",
                                    "border": f"1px solid {COLORS['border']}",
                                    "borderRadius": "5px",
                                    "padding": "15px",
                                    "backgroundColor": COLORS["light"],
                                    "marginLeft": "4%",
                                    "boxSizing": "border-box",
                                },
                            ),
                        ],
                        style={
                            "marginBottom": "20px",
                            "width": "100%",
                            "textAlign": "center",
                        },
                    ),
                    # Third row - Tables and summary
                    html.Div(
                        [
                            # Summary table
                            html.Div(
                                id="summary-table",
                                style={
                                    "width": "30%",
                                    "display": "inline-block",
                                    "border": f"1px solid {COLORS['border']}",
                                    "borderRadius": "5px",
                                    "padding": "15px",
                                    "backgroundColor": COLORS["light"],
                                    "verticalAlign": "top",
                                    "boxSizing": "border-box",
                                },
                            ),
                            # Wasteful zones plot
                            html.Div(
                                [
                                    html.H3(
                                        "Top Wasteful Zones",
                                        style={
                                            "textAlign": "center",
                                            "fontSize": "1rem",
                                        },
                                    ),
                                    html.P(
                                        "These zones have the most cooling energy used when indoor temperature is below the heating setpoint:",
                                        style={
                                            "fontSize": "0.9rem",
                                            "marginBottom": "10px",
                                        },
                                    ),
                                    html.Div(id="wasteful-zones-plot"),
                                ],
                                style={
                                    "width": "33%",
                                    "display": "inline-block",
                                    "border": f"1px solid {COLORS['border']}",
                                    "borderRadius": "5px",
                                    "padding": "15px",
                                    "backgroundColor": COLORS["light"],
                                    "marginLeft": "1.5%",
                                    "verticalAlign": "top",
                                    "boxSizing": "border-box",
                                },
                            ),
                            # Demanding zones plot
                            html.Div(
                                [
                                    html.H3(
                                        "Top Demanding Zones",
                                        style={
                                            "textAlign": "center",
                                            "fontSize": "1rem",
                                        },
                                    ),
                                    html.P(
                                        "These zones have the most cooling energy used when indoor temperature is above the cooling setpoint:",
                                        style={
                                            "fontSize": "0.9rem",
                                            "marginBottom": "10px",
                                        },
                                    ),
                                    html.Div(id="demanding-zones-plot"),
                                ],
                                style={
                                    "width": "33%",
                                    "display": "inline-block",
                                    "border": f"1px solid {COLORS['border']}",
                                    "borderRadius": "5px",
                                    "padding": "15px",
                                    "backgroundColor": COLORS["light"],
                                    "marginLeft": "1.5%",
                                    "verticalAlign": "top",
                                    "boxSizing": "border-box",
                                },
                            ),
                        ],
                        style={"width": "100%", "textAlign": "center"},
                    ),
                ]
            ),
        ],
        style={"width": "100%"},
    )
