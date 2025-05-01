from dash import Input, Output, callback, html, dcc, State
import pandas as pd
import os
import dash
from dash import callback_context
import plotly.graph_objects as go
import pickle
from dash.dependencies import MATCH

from core.visualization import (
    create_stacked_area_plot,
    create_regrouped_stacked_area_plot,
    create_wasteful_zones_bar_plot,
    create_demanding_zones_bar_plot,
)
from layouts.main_layout import create_results_layout
from utils.constants import COLORS


@callback(
    Output("preloaded-analysis-content", "children"),
    [Input("app-tabs", "value"), Input("building-tabs", "value")],
)
def load_preloaded_analysis(app_tab_value, building_name):
    """
    Load pre-processed analysis data from saved pickle file
    """
    if app_tab_value != "tab-preloaded":
        # Only load the data when the preloaded tab is active
        return html.Div()

    if not building_name:
        # No building selected
        return html.Div(html.H3("Please select a building to view analysis"))

    try:
        # Path to the pre-processed data
        processed_data_path = os.path.join("processed_data", "preloaded_analysis.pkl")

        # Check if processed data exists - if not, show message to run pre-processing script
        if not os.path.exists(processed_data_path):
            return html.Div(
                [
                    html.H3(
                        "Pre-processed Data Not Found",
                        style={"color": COLORS["accent"]},
                    ),
                    html.P("Please run the pre-processing script first:"),
                    html.Pre(
                        "bash preprocess_data.sh",
                        style={
                            "backgroundColor": "#f5f5f5",
                            "padding": "10px",
                            "borderRadius": "5px",
                        },
                    ),
                    html.P("This will create the necessary processed data files."),
                ]
            )

        # Load the pre-processed data
        with open(processed_data_path, "rb") as f:
            all_buildings_data = pickle.load(f)

        # Check if the selected building exists in the data
        if building_name not in all_buildings_data:
            return html.Div(
                [
                    html.H3(
                        f"Building '{building_name}' Data Not Found",
                        style={"color": COLORS["accent"]},
                    ),
                    html.P(
                        "Selected building data is not available. Please select a different building or run the pre-processing script again."
                    ),
                ]
            )

        # Get the data for the selected building
        processed_data = all_buildings_data[building_name]

        # Extract the data components
        df_cooling_zonal = processed_data["df_cooling_zonal"]
        df_iat_binned = processed_data["df_iat_binned"]
        weekly_df_iat_binned = processed_data["weekly_df_iat_binned"]
        top_wasteful = processed_data["top_wasteful"]
        top_demanding = processed_data["top_demanding"]

        # Store the raw data for zone detail plots if available
        zone_data = {}
        if "iat" in processed_data:
            zone_data["iat"] = processed_data["iat"]
        if "hsp" in processed_data:
            zone_data["hsp"] = processed_data["hsp"]
        if "csp" in processed_data:
            zone_data["csp"] = processed_data["csp"]
        if "airflow" in processed_data:
            zone_data["airflow"] = processed_data["airflow"]

        # Use the weekly resampled data for creating visualizations
        df_iat_binned_for_viz = weekly_df_iat_binned

        # Create visualizations
        # 1. Stacked area plot - absolute values
        fig_bins_absolute = create_stacked_area_plot(
            df_iat_binned_for_viz,
            f"{building_name} - Cooling Energy by Week (Absolute)",
            "MMBtu",
            normalize=False,
        )

        # 2. Stacked area plot - normalized values
        fig_bins_fractional = create_stacked_area_plot(
            df_iat_binned_for_viz,
            f"{building_name} - Cooling Energy by Week (Fractional)",
            "%",
            normalize=True,
        )

        # 3. Regrouped stacked area - absolute values
        fig_regrouped_absolute = create_regrouped_stacked_area_plot(
            df_iat_binned_for_viz,
            f"{building_name} - Regrouped Cooling Energy by Week (Absolute)",
            "MMBtu",
            normalize=False,
        )

        # 4. Regrouped stacked area - normalized values
        fig_regrouped_fractional = create_regrouped_stacked_area_plot(
            df_iat_binned_for_viz,
            f"{building_name} - Regrouped Cooling Energy by Week (Fractional)",
            "%",
            normalize=True,
        )

        # Create result tables
        # Summary table
        cooling_total = df_iat_binned_for_viz.sum().sum()

        # Make sure these columns exist in df_iat_binned
        useful_cols = [
            col
            for col in ["bin4_50-75%", "bin5_75-100%", "bin6_IAT>CSP"]
            if col in df_iat_binned_for_viz.columns
        ]
        excess_cols = [
            col
            for col in ["bin2_0-25%", "bin3_25-50%"]
            if col in df_iat_binned_for_viz.columns
        ]
        wasteful_col = (
            "bin1_IAT<HSP" if "bin1_IAT<HSP" in df_iat_binned_for_viz.columns else None
        )

        # Calculate sums based on available columns
        demand = df_iat_binned_for_viz[useful_cols].sum().sum() if useful_cols else 0
        excess = df_iat_binned_for_viz[excess_cols].sum().sum() if excess_cols else 0
        wasteful = df_iat_binned_for_viz[wasteful_col].sum() if wasteful_col else 0

        summary_table = html.Div(
            [
                html.H3(
                    f"{building_name} - Analysis Summary",
                    style={"textAlign": "center", "fontSize": "1.1rem"},
                ),
                html.Table(
                    [
                        html.Thead(
                            html.Tr(
                                [
                                    html.Th("Category"),
                                    html.Th("Energy (MMBtu)"),
                                    html.Th("Percentage"),
                                ]
                            )
                        ),
                        html.Tbody(
                            [
                                html.Tr(
                                    [
                                        html.Td("Total Cooling"),
                                        html.Td(f"{cooling_total:.2f}"),
                                        html.Td("100%"),
                                    ]
                                ),
                                html.Tr(
                                    [
                                        html.Td("Useful Cooling"),
                                        html.Td(f"{demand:.2f}"),
                                        html.Td(
                                            f"{(demand / cooling_total * 100):.1f}%"
                                            if cooling_total > 0
                                            else "0%"
                                        ),
                                    ]
                                ),
                                html.Tr(
                                    [
                                        html.Td("Excess Cooling"),
                                        html.Td(f"{excess:.2f}"),
                                        html.Td(
                                            f"{(excess / cooling_total * 100):.1f}%"
                                            if cooling_total > 0
                                            else "0%"
                                        ),
                                    ]
                                ),
                                html.Tr(
                                    [
                                        html.Td("Wasteful Cooling"),
                                        html.Td(f"{wasteful:.2f}"),
                                        html.Td(
                                            f"{(wasteful / cooling_total * 100):.1f}%"
                                            if cooling_total > 0
                                            else "0%"
                                        ),
                                    ]
                                ),
                            ]
                        ),
                    ],
                    style={
                        "width": "100%",
                        "border": "1px solid #ddd",
                        "borderCollapse": "collapse",
                    },
                ),
            ],
        )

        # Create wasteful and demanding zone plots using pre-processed data
        if not top_wasteful.empty:
            wasteful_zones_plot = create_wasteful_zones_bar_plot(top_wasteful)
            wasteful_zones_plot.update_layout(
                title=f"{building_name} - Top Wasteful Zones"
            )
        else:
            # Create an empty plot if no data
            wasteful_zones_plot = go.Figure()
            wasteful_zones_plot.update_layout(
                title=f"{building_name} - No wasteful zones found"
            )

        if not top_demanding.empty:
            demanding_zones_plot = create_demanding_zones_bar_plot(top_demanding)
            demanding_zones_plot.update_layout(
                title=f"{building_name} - Top Demanding Zones"
            )
        else:
            # Create an empty plot if no data
            demanding_zones_plot = go.Figure()
            demanding_zones_plot.update_layout(
                title=f"{building_name} - No demanding zones found"
            )

        # Create a results layout with our charts
        results_layout = create_results_layout()

        # Update the graph objects in the layout
        results_layout.children[1].children[0].children[0].children[
            1
        ].figure = fig_bins_absolute
        results_layout.children[1].children[0].children[1].children[
            1
        ].figure = fig_bins_fractional
        results_layout.children[1].children[1].children[0].children[
            1
        ].figure = fig_regrouped_absolute
        results_layout.children[1].children[1].children[1].children[
            1
        ].figure = fig_regrouped_fractional

        # Update the summary table (now in its own row)
        results_layout.children[1].children[2].children[0].children = summary_table

        # Add wasteful zones plot with click capability
        wasteful_zones_plot.update_traces(
            marker_color=COLORS["wasteful"],
            hovertemplate="<b>%{y}</b><br>Wasteful Cooling: %{x:.2f} MMBtu<extra></extra>",
        )

        wasteful_zones_plot_div = html.Div(
            [
                dcc.Graph(
                    id="wasteful-zones-plot",
                    figure=wasteful_zones_plot,
                    config={"displayModeBar": False},
                ),
            ]
        )
        # Now in the fourth row, first column
        results_layout.children[1].children[3].children[0].children[
            2
        ].children = wasteful_zones_plot_div

        # Add demanding zones plot with click capability
        demanding_zones_plot.update_traces(
            marker_color=COLORS["useful"],
            hovertemplate="<b>%{y}</b><br>Total Cooling: %{x:.2f} MMBtu<extra></extra>",
        )

        demanding_zones_plot_div = html.Div(
            [
                dcc.Graph(
                    id="demanding-zones-plot",
                    figure=demanding_zones_plot,
                    config={"displayModeBar": False},
                ),
            ]
        )
        # Now in the fourth row, second column
        results_layout.children[1].children[3].children[1].children[
            2
        ].children = demanding_zones_plot_div

        # Create a hidden div to store the current building's zone data for the callbacks
        zone_data_store = html.Div(
            id="zone-data-store",
            style={"display": "none"},
            children=dcc.Store(
                id="zone-data",
                data={"building": building_name, "has_zone_data": bool(zone_data)},
            ),
        )

        # Add the data store to the layout
        results_layout.children.append(zone_data_store)

        return results_layout

    except Exception as e:
        # Return error message if something goes wrong
        return html.Div(
            [
                html.H3(
                    "Error Loading Pre-analyzed Data", style={"color": COLORS["accent"]}
                ),
                html.P(f"Error details: {str(e)}"),
                html.P(
                    "Please run the pre-processing script to regenerate the analysis data:"
                ),
                html.Pre(
                    "bash preprocess_data.sh",
                    style={
                        "backgroundColor": "#f5f5f5",
                        "padding": "10px",
                        "borderRadius": "5px",
                    },
                ),
            ]
        )


@callback(Output("building-tabs", "value"), Input("building-tabs", "children"))
def set_default_building(tabs):
    """
    Set the default building tab when tabs are loaded
    """
    if not tabs or len(tabs) == 0:
        return None

    # Get the value of the first tab
    first_tab = tabs[0]
    return first_tab.get("props", {}).get("value", None)


@callback(
    Output("zone-details-container", "children"),
    [
        Input("wasteful-zones-plot", "clickData"),
        Input("demanding-zones-plot", "clickData"),
    ],
    State("building-tabs", "value"),
)
def update_zone_details(wasteful_click, demanding_click, building_name):
    """
    Update the zone details when either a wasteful or demanding zone is clicked
    """
    ctx = callback_context

    if not ctx.triggered:
        return html.Div()

    # Determine which chart was clicked
    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
    click_data = (
        wasteful_click if trigger_id == "wasteful-zones-plot" else demanding_click
    )

    if click_data is None:
        return html.Div()

    try:
        # Extract the zone name from the click data
        zone_name = click_data["points"][0]["y"]

        # Create and return the zone detail plots
        return html.Div(
            children=create_zone_detail_plots(zone_name, building_name),
            style={
                "width": "100%",
                "marginTop": "20px",
                "border": f"1px solid {COLORS['border']}",
                "borderRadius": "5px",
                "padding": "15px",
                "backgroundColor": COLORS["light"],
            },
        )
    except Exception as e:
        return html.Div(
            [html.P(f"Error displaying zone details: {str(e)}", style={"color": "red"})]
        )


def create_zone_detail_plots(zone_name, building_name):
    """
    Create temperature/setpoint and airflow plots for a specific zone
    """
    try:
        # Load the building data
        processed_data_path = os.path.join("processed_data", "preloaded_analysis.pkl")
        with open(processed_data_path, "rb") as f:
            all_buildings_data = pickle.load(f)

        # Get the raw data for the selected building
        processed_data = all_buildings_data[building_name]
        df_cooling_zonal = processed_data["df_cooling_zonal"]

        # Check if we have the raw data for this zone
        if zone_name not in df_cooling_zonal.columns:
            return html.Div(
                [
                    html.H4(
                        f"Zone '{zone_name}' Details", style={"color": COLORS["accent"]}
                    ),
                    html.P("No detailed data available for this zone."),
                ]
            )

        # Get zone temperature and setpoint data
        raw_data = {}
        for data_type in ["iat", "hsp", "csp", "airflow"]:
            if data_type in processed_data:
                df = processed_data[data_type]
                if zone_name in df.columns:
                    raw_data[data_type] = df[zone_name]

        # If no raw data is available
        if not raw_data:
            return html.Div(
                [
                    html.H4(
                        f"Zone '{zone_name}' Details", style={"color": COLORS["accent"]}
                    ),
                    html.P("No detailed data available for this zone."),
                ]
            )

        # Create temperature and setpoint plot
        temp_fig = go.Figure()

        if "iat" in raw_data:
            # Resample to daily for better visualization
            iat_daily = raw_data["iat"].resample("D").mean()
            temp_fig.add_trace(
                go.Scatter(
                    x=iat_daily.index,
                    y=iat_daily.values,
                    mode="lines",
                    name="Zone Temperature",
                    line=dict(color=COLORS["demanding"]),
                )
            )

        if "hsp" in raw_data:
            # Resample to daily for better visualization
            hsp_daily = raw_data["hsp"].resample("D").mean()
            temp_fig.add_trace(
                go.Scatter(
                    x=hsp_daily.index,
                    y=hsp_daily.values,
                    mode="lines",
                    name="Heating Setpoint",
                    line=dict(color=COLORS["wasteful"], dash="dash"),
                )
            )

        if "csp" in raw_data:
            # Resample to daily for better visualization
            csp_daily = raw_data["csp"].resample("D").mean()
            temp_fig.add_trace(
                go.Scatter(
                    x=csp_daily.index,
                    y=csp_daily.values,
                    mode="lines",
                    name="Cooling Setpoint",
                    line=dict(color=COLORS["excess"], dash="dash"),
                )
            )

        temp_fig.update_layout(
            title=f"Zone '{zone_name}' - Temperature and Setpoints",
            xaxis_title="Date",
            yaxis_title="Temperature (°F)",
            legend=dict(
                orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
            ),
            margin=dict(l=40, r=40, t=40, b=40),
        )

        # Create airflow plot
        airflow_fig = go.Figure()

        if "airflow" in raw_data:
            # Resample to daily for better visualization
            airflow_daily = raw_data["airflow"].resample("D").mean()
            airflow_fig.add_trace(
                go.Scatter(
                    x=airflow_daily.index,
                    y=airflow_daily.values,
                    mode="lines",
                    name="Airflow",
                    line=dict(color=COLORS["useful"]),
                    fill="tozeroy",
                )
            )

        airflow_fig.update_layout(
            title=f"Zone '{zone_name}' - Airflow",
            xaxis_title="Date",
            yaxis_title="Airflow (CFM)",
            margin=dict(l=40, r=40, t=40, b=40),
        )

        # Return the plots side by side in a row
        return [
            html.H4(f"Zone '{zone_name}' Details", style={"textAlign": "center"}),
            html.Div(
                [
                    # Temperature plot (left)
                    html.Div(
                        [
                            dcc.Graph(
                                figure=temp_fig, config={"displayModeBar": False}
                            ),
                        ],
                        style={
                            "width": "49%",
                            "display": "inline-block",
                            "verticalAlign": "top",
                        },
                    ),
                    # Airflow plot (right)
                    html.Div(
                        [
                            dcc.Graph(
                                figure=airflow_fig, config={"displayModeBar": False}
                            ),
                        ],
                        style={
                            "width": "49%",
                            "display": "inline-block",
                            "verticalAlign": "top",
                            "marginLeft": "2%",
                        },
                    ),
                ]
            ),
        ]

    except Exception as e:
        return html.Div(
            [
                html.H4(
                    f"Zone '{zone_name}' Details", style={"color": COLORS["accent"]}
                ),
                html.P(f"Error creating zone detail plots: {str(e)}"),
            ]
        )


@callback(Output("building-tabs", "children"), Input("app-tabs", "value"))
def load_building_tabs(app_tab_value):
    """
    Load building tabs when the preloaded tab is selected
    """
    if app_tab_value != "tab-preloaded":
        return []

    try:
        # Try to load buildings info file
        buildings_info_path = os.path.join("processed_data", "buildings_info.pkl")

        if not os.path.exists(buildings_info_path):
            # Check if preloaded analysis exists in old format
            preloaded_path = os.path.join("processed_data", "preloaded_analysis.pkl")
            if os.path.exists(preloaded_path):
                # Try to check if it's the old format with a single building
                with open(preloaded_path, "rb") as f:
                    try:
                        data = pickle.load(f)
                        # If it's a dict with expected keys but not nested by building
                        if isinstance(data, dict) and "df_cooling_zonal" in data:
                            # This is the old single-building format
                            return [
                                dcc.Tab(
                                    label="Default Building", value="Default Building"
                                )
                            ]
                    except:
                        pass

            # If we get here, either no data exists or it's in an unknown format
            return [
                dcc.Tab(
                    label="No buildings found",
                    value="none",
                    disabled=True,
                    style={"color": COLORS["accent"]},
                )
            ]

        # Load the buildings info
        with open(buildings_info_path, "rb") as f:
            buildings_info = pickle.load(f)

        building_names = buildings_info.get("names", [])

        if not building_names:
            return [
                dcc.Tab(
                    label="No buildings found",
                    value="none",
                    disabled=True,
                    style={"color": COLORS["accent"]},
                )
            ]

        # Create a tab for each building
        return [
            dcc.Tab(
                label=name,
                value=name,
                className="custom-tab",
                selected_className="custom-tab--selected",
            )
            for name in building_names
        ]

    except Exception as e:
        # Return a placeholder tab if there's an error
        return [
            dcc.Tab(
                label=f"Error loading buildings: {str(e)}",
                value="error",
                disabled=True,
                style={"color": "red"},
            )
        ]
