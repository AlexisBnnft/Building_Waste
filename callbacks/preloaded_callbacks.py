from dash import Input, Output, callback, html, dcc
import pandas as pd
import os
import dash
import plotly.graph_objects as go
import pickle

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

        # Update the tables and plots
        results_layout.children[1].children[2].children[0].children = summary_table

        # Add wasteful zones plot
        wasteful_zones_plot_div = html.Div(
            dcc.Graph(figure=wasteful_zones_plot),
        )
        results_layout.children[1].children[2].children[1].children[
            2
        ].children = wasteful_zones_plot_div

        # Add demanding zones plot
        demanding_zones_plot_div = html.Div(
            dcc.Graph(figure=demanding_zones_plot),
        )
        results_layout.children[1].children[2].children[2].children[
            2
        ].children = demanding_zones_plot_div

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
