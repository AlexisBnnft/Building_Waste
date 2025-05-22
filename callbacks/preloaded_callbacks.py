from dash import Input, Output, callback, html, dcc, State
import pandas as pd
import os
import dash
from dash import callback_context
import plotly.graph_objects as go
import pickle
from dash.dependencies import MATCH, ALL
import boto3
import io
from botocore.exceptions import ClientError
import json
from os import environ
from dotenv import load_dotenv
import time
import numpy as np

# Load environment variables from .env file if it exists
load_dotenv()

from core.visualization import (
    create_stacked_area_plot,
    create_regrouped_stacked_area_plot,
    create_wasteful_zones_bar_plot,
    create_demanding_zones_bar_plot,
    create_top_savings_bar_plot,
)
from layouts.main_layout import create_results_layout
from utils.constants import COLORS


# Global variables for background loading
LOADING_QUEUE = []
LOADING_IN_PROGRESS = False
CURRENTLY_LOADING = set()  # Track which buildings are currently being loaded
CURRENT_USER_BUILDING = None  # Track which building the user is viewing
BACKGROUND_LOAD_INTERVAL = 5  # seconds


def get_s3_client():
    """
    Creates and returns an S3 client using environment variables
    """
    # Get S3 credentials from environment variables
    aws_access_key = environ.get("AWS_ACCESS_KEY_ID")
    aws_secret_key = environ.get("AWS_SECRET_ACCESS_KEY")
    s3_region = environ.get(
        "S3_REGION", "us-east-1"
    )  # Default to us-east-1 if not specified

    # Create and return S3 client
    s3_client = boto3.client(
        "s3",
        region_name=s3_region,
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
    )
    return s3_client


def load_pickle_from_s3(s3_path):
    """
    Loads a pickle file from S3 bucket

    Args:
        s3_path: Path to the pickle file in S3

    Returns:
        Unpickled data
    """
    try:
        # Get bucket name and object key from environment variables
        bucket_name = environ.get("S3_BUCKET_NAME")

        print(f"Attempting to load data from S3: {bucket_name}/{s3_path}")

        if not bucket_name:
            print("ERROR: S3_BUCKET_NAME environment variable not set")
            raise ValueError("S3_BUCKET_NAME environment variable not set")

        # Create S3 client
        s3_client = get_s3_client()

        # Get the object from S3
        print(f"Fetching object from S3...")
        response = s3_client.get_object(Bucket=bucket_name, Key=s3_path)

        # Load the pickle data from the response
        print(f"Successfully fetched object, loading pickle data...")
        pickle_data = response["Body"].read()
        data = pickle.loads(pickle_data)

        print(f"Successfully loaded data from S3")
        return data

    except ClientError as e:
        print(f"ERROR fetching from S3: {e}")
        if "404" in str(e):
            print(f"File not found in S3: s3://{bucket_name}/{s3_path}")
        elif "403" in str(e):
            print(
                f"Access denied to S3 bucket. Check your credentials and permissions."
            )
        else:
            print(f"S3 client error details: {str(e)}")
        return None
    except Exception as e:
        print(f"ERROR loading pickle data: {e}")
        print(f"Error type: {type(e).__name__}")
        print(f"Error details: {str(e)}")
        return None


def load_building_data_from_s3(building_name):
    """
    Load data for a specific building from S3

    Args:
        building_name: Name of the building to load

    Returns:
        Building data dictionary or None if not found
    """
    # Create a safe filename version of the building name
    safe_name = building_name.replace(" ", "_").replace("/", "_").replace("\\", "_")

    # Construct the S3 path for this building
    s3_path = f"buildings/{safe_name}.pkl"

    # Load the data from S3
    print(f"Loading data for building '{building_name}' from S3...")
    start_time = time.time()
    building_data = load_pickle_from_s3(s3_path)
    elapsed = time.time() - start_time

    if building_data:
        print(f"Successfully loaded {building_name} data in {elapsed:.2f} seconds")
        return building_data
    else:
        print(f"Failed to load building data for {building_name}")
        return None


@callback(
    Output("preloaded-analysis-content", "children"),
    [Input("app-tabs", "value"), Input("building-tabs", "value")],
)
def load_preloaded_analysis(app_tab_value, building_name):
    """
    Load pre-processed analysis data for a specific building from S3
    """
    global CURRENTLY_LOADING, CURRENT_USER_BUILDING

    if app_tab_value != "tab-preloaded":
        # Only load the data when the preloaded tab is active
        return html.Div()

    if not building_name:
        # No building selected
        return html.Div(html.H3("Please select a building to view analysis"))

    # Check if building_name is actually a hidden component ID
    if building_name in [
        "background-loading-interval",
        "building-names-store",
        "background-loading-status",
    ]:
        print(f"Ignoring hidden component '{building_name}' as building name")
        return html.Div(html.H3("Please select a building to view analysis"))

    # Track the current building the user is viewing
    CURRENT_USER_BUILDING = building_name

    # Show loading indicator while data is being fetched
    loading_div = html.Div(
        [
            html.H3(
                f"Loading {building_name} data...", style={"color": COLORS["accent"]}
            ),
            html.Div(className="loading-spinner"),
            html.P(
                "This may take a moment if the building data is large. Data will be cached after first load."
            ),
        ],
        style={"textAlign": "center", "marginTop": "50px"},
    )

    print(f"\n--- Loading analysis for building: {building_name} ---")

    # Create a cache object if it doesn't exist yet
    if not hasattr(load_preloaded_analysis, "building_cache"):
        load_preloaded_analysis.building_cache = {}

    # Check if we already have this building's data in the cache
    if building_name in load_preloaded_analysis.building_cache:
        print(f"Using cached data for building: {building_name}")
        processed_data = load_preloaded_analysis.building_cache[building_name]
    else:
        try:
            # Add to currently loading set to avoid background loader duplication
            CURRENTLY_LOADING.add(building_name)

            # Load data for the specific building
            print(f"Fetching data from S3 for building: {building_name}")
            building_data = load_building_data_from_s3(building_name)

            # Remove from currently loading set
            if building_name in CURRENTLY_LOADING:
                CURRENTLY_LOADING.remove(building_name)

            # Check if we couldn't load the data
            if building_data is None:
                print(f"Failed to load data from S3 for building {building_name}")
                return html.Div(
                    [
                        html.H3(
                            f"Building '{building_name}' Data Not Found in S3",
                            style={"color": COLORS["accent"]},
                        ),
                        html.P(
                            "Make sure you have uploaded the building data to your S3 bucket and set the correct environment variables:"
                        ),
                        html.Pre(
                            "Required environment variables:\n- S3_BUCKET_NAME\n- AWS_ACCESS_KEY_ID\n- AWS_SECRET_ACCESS_KEY\n- S3_REGION (optional, defaults to us-east-1)",
                            style={
                                "backgroundColor": "#f5f5f5",
                                "padding": "10px",
                                "borderRadius": "5px",
                            },
                        ),
                    ]
                )

            # Add to cache for future use
            load_preloaded_analysis.building_cache[building_name] = building_data
            processed_data = building_data
            print(f"Added building {building_name} to cache")

        except Exception as e:
            # Remove from currently loading set in case of error
            if building_name in CURRENTLY_LOADING:
                CURRENTLY_LOADING.remove(building_name)

            print(f"Error loading building data: {str(e)}")
            return html.Div(
                [
                    html.H3(
                        f"Error Loading Building Data",
                        style={"color": COLORS["accent"]},
                    ),
                    html.P(f"Error details: {str(e)}"),
                ]
            )

    # Extract the data components
    df_cooling_zonal = processed_data["df_cooling_zonal"]
    df_iat_binned = processed_data["df_iat_binned"]
    weekly_df_iat_binned = processed_data["weekly_df_iat_binned"]
    top_wasteful = processed_data["top_wasteful"]
    top_demanding = processed_data["top_demanding"]

    # NEW: Extract analysis_df_for_details and top_savings
    analysis_df_for_details = processed_data.get(
        "analysis_df_for_details", pd.DataFrame()
    )
    top_savings = processed_data.get("top_savings", pd.DataFrame())
    top_savings_all_zones = processed_data.get("top_savings_all_zones", pd.DataFrame())

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
    # Pass analysis_df_for_details to zone_data so it's available for create_zone_detail_plots
    if not analysis_df_for_details.empty:
        zone_data["analysis_df_for_details"] = analysis_df_for_details
        print(
            f"DEBUG - Added analysis_df_for_details to zone_data with shape {analysis_df_for_details.shape}"
        )
    else:
        print("DEBUG - analysis_df_for_details is empty, not adding to zone_data")

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
        wasteful_zones_plot.update_layout(title=f"{building_name} - Top Wasteful Zones")
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

    # NEW: Create top savings zones plot
    if not top_savings.empty:
        top_savings_plot = create_top_savings_bar_plot(top_savings)
        top_savings_plot.update_layout(
            title=f"{building_name} - Top Savings Zones (IAT < HSP Waste)"
        )
        top_savings_plot.update_traces(
            marker_color="#27ae60",  # Green color for savings
            hovertemplate="<b>%{y}</b><br>Potential Savings: %{x:.2f}<br>% of Total Building Savings: %{text}<extra></extra>",
        )
    else:
        # Create an empty plot if no data
        top_savings_plot = go.Figure()
        top_savings_plot.update_layout(
            title=f"{building_name} - No savings zones found"
        )

    # NEW: Create top savings for ALL zones plot
    if not top_savings_all_zones.empty:
        top_savings_all_zones_plot = create_top_savings_bar_plot(top_savings_all_zones)
        top_savings_all_zones_plot.update_layout(
            title=f"{building_name} - Top Savings Zones (ASHRAE Minimum Airflow)"
        )
        top_savings_all_zones_plot.update_traces(
            marker_color="#2ecc71",  # Light green color for all zones savings
            hovertemplate="<b>%{y}</b><br>Potential Savings: %{x:.2f}<br>% of Total Building Savings: %{text}<extra></extra>",
        )
    else:
        # Create an empty plot if no data
        top_savings_all_zones_plot = go.Figure()
        top_savings_all_zones_plot.update_layout(
            title=f"{building_name} - No savings zones found for all zones"
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

    # NEW: Add the ALL ZONES savings plot to the layout
    top_savings_all_zones_plot_div = html.Div(
        [
            dcc.Graph(
                id="top-savings-all-zones-plot",  # New ID for the all zones savings plot
                figure=top_savings_all_zones_plot,
                config={"displayModeBar": False},
            ),
        ]
    )

    # Now in the fourth row, third column
    results_layout.children[1].children[3].children[2].children[
        2
    ].children = top_savings_all_zones_plot_div

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


@callback(Output("building-tabs", "value"), Input("building-tabs", "children"))
def set_default_building(tabs):
    """
    Set the default building tab when tabs are loaded
    """
    if not tabs or len(tabs) == 0:
        return None

    # Look for the first tab that has a valid building value
    # (not a hidden component like interval or div)
    for tab in tabs:
        value = tab.get("props", {}).get("value", None)

        # Skip tabs that are actually hidden components
        if (
            value
            and not value.startswith("background-")
            and not value == "building-names-store"
        ):
            return value

    # If no valid building tab is found, return None
    return None


@callback(
    Output("zone-details-container", "children"),
    [
        Input("wasteful-zones-plot", "clickData"),
        Input("demanding-zones-plot", "clickData"),
        Input(
            "top-savings-all-zones-plot", "clickData"
        ),  # Only keep the all zones savings plot
    ],
    State("building-tabs", "value"),
)
def update_zone_details(
    wasteful_click, demanding_click, all_zones_savings_click, building_name
):
    """
    Update the zone details when any zone is clicked in any of the plots
    """
    ctx = callback_context

    if not ctx.triggered:
        return html.Div()

    # Determine which chart was clicked
    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
    click_data = None
    if trigger_id == "wasteful-zones-plot":
        click_data = wasteful_click
    elif trigger_id == "demanding-zones-plot":
        click_data = demanding_click
    elif (
        trigger_id == "top-savings-all-zones-plot"
    ):  # Only handle clicks for all zones savings plot
        click_data = all_zones_savings_click

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
        # Check if building data is already in cache
        if (
            hasattr(load_preloaded_analysis, "building_cache")
            and building_name in load_preloaded_analysis.building_cache
        ):
            print(
                f"Using cached data for zone details of {zone_name} in building {building_name}"
            )
            processed_data = load_preloaded_analysis.building_cache[building_name]
            # Debug: Check if analysis_df_for_details is in the cached data
            if "analysis_df_for_details" in processed_data:
                print(
                    f"DEBUG - Found analysis_df_for_details in cached data with shape {processed_data['analysis_df_for_details'].shape}"
                )
            else:
                print("DEBUG - analysis_df_for_details NOT found in cached data")
        else:
            # Load the building data from S3 as fallback
            print(f"Cache miss for building {building_name}, loading from S3...")
            building_data = load_building_data_from_s3(building_name)

            if building_data is None:
                return html.Div(
                    [
                        html.H4(
                            "S3 Data Access Error", style={"color": COLORS["accent"]}
                        ),
                        html.P(
                            f"Could not load building data for '{building_name}' from S3. Please check your S3 configuration and credentials."
                        ),
                    ]
                )

            # Store in cache for future use
            if not hasattr(load_preloaded_analysis, "building_cache"):
                load_preloaded_analysis.building_cache = {}
            load_preloaded_analysis.building_cache[building_name] = building_data
            processed_data = building_data

        # Get the raw data for the selected building
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
                else:
                    print(f"Warning: {data_type} data not found for zone {zone_name}")

        # NEW: Get analysis_df_for_details from processed_data
        analysis_df_for_details = processed_data.get(
            "analysis_df_for_details", pd.DataFrame()
        )

        # If no raw data is available
        if not raw_data:
            return html.Div(
                [
                    html.H4(
                        f"Zone '{zone_name}' Details", style={"color": COLORS["accent"]}
                    ),
                    html.P(
                        "No detailed time series data available for this zone. Only top wasteful and demanding zones have detailed data stored."
                    ),
                ]
            )

        # Create temperature and setpoint plot
        temp_fig = go.Figure()

        if "iat" in raw_data:
            # Filter for business hours (9 AM to 6 PM) and resample to daily
            iat_business = raw_data["iat"].between_time("9:00", "18:00")
            iat_daily = iat_business.resample("D").mean()
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
            # Filter for business hours (9 AM to 6 PM) and resample to daily
            hsp_business = raw_data["hsp"].between_time("9:00", "18:00")
            hsp_daily = hsp_business.resample("D").mean()
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
            # Filter for business hours (9 AM to 6 PM) and resample to daily
            csp_business = raw_data["csp"].between_time("9:00", "18:00")
            csp_daily = csp_business.resample("D").mean()
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
            title=f"Zone '{zone_name}' - Temperature and Setpoints (Business Hours: 9AM-6PM)",
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
            # Filter for business hours (9 AM to 6 PM) and resample to daily
            airflow_business = raw_data["airflow"].between_time("9:00", "18:00")
            airflow_daily = airflow_business.resample("D").mean()
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

            # NEW: Add ASHRAE Guideline Airflow as a dashed line
            ashrae_guideline_cfm = np.nan
            if (
                not analysis_df_for_details.empty
                and "VAV" in analysis_df_for_details.columns
                and "ASHRAE_Guideline_CFM" in analysis_df_for_details.columns
            ):
                # Add debug print to check analysis_df_for_details
                print(
                    f"DEBUG: analysis_df_for_details shape: {analysis_df_for_details.shape}"
                )
                print(
                    f"DEBUG: analysis_df_for_details columns: {analysis_df_for_details.columns.tolist()}"
                )
                print(f"DEBUG: Looking for zone '{zone_name}' in VAV column")

                # Ensure VAV column is string for matching
                guideline_row = analysis_df_for_details[
                    analysis_df_for_details["VAV"].astype(str).str.strip()
                    == str(zone_name).strip()
                ]
                if not guideline_row.empty:
                    ashrae_guideline_cfm = guideline_row["ASHRAE_Guideline_CFM"].iloc[0]
                    print(
                        f"DEBUG: Found ASHRAE guideline: {ashrae_guideline_cfm} CFM for zone {zone_name}"
                    )
                else:
                    print(
                        f"DEBUG: No matching VAV found for zone '{zone_name}' in analysis_df_for_details"
                    )
                    # Print some sample VAV values to help debug
                    if len(analysis_df_for_details) > 0:
                        sample_vavs = (
                            analysis_df_for_details["VAV"]
                            .astype(str)
                            .str.strip()
                            .head(100)
                            .tolist()
                        )
                        print(
                            f"DEBUG: Sample VAVs in analysis_df_for_details: {sample_vavs}"
                        )
            else:
                if analysis_df_for_details.empty:
                    print("DEBUG: analysis_df_for_details is empty")
                else:
                    print(
                        f"DEBUG: analysis_df_for_details missing required columns. Available columns: {analysis_df_for_details.columns.tolist()}"
                    )

            if pd.notna(ashrae_guideline_cfm):
                airflow_fig.add_trace(
                    go.Scatter(
                        x=airflow_daily.index,
                        y=[ashrae_guideline_cfm] * len(airflow_daily),
                        mode="lines",
                        name=f"ASHRAE Guideline ({ashrae_guideline_cfm:.0f} CFM)",
                        line=dict(color="red", dash="dash", width=2),
                    )
                )

        airflow_fig.update_layout(
            title=f"Zone '{zone_name}' - Airflow (Business Hours: 9AM-6PM)",
            xaxis_title="Date",
            yaxis_title="Airflow (CFM)",
            margin=dict(l=40, r=40, t=40, b=40),
            legend=dict(
                orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
            ),
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


def initialize_background_loading(building_names):
    """
    Initialize the background loading queue with all building names
    """
    global LOADING_QUEUE, LOADING_IN_PROGRESS

    # Don't re-add buildings that are already in queue
    for name in building_names:
        if name not in LOADING_QUEUE:
            LOADING_QUEUE.append(name)

    print(f"Background loading queue initialized with {len(LOADING_QUEUE)} buildings")


@callback(Output("building-tabs", "children"), Input("app-tabs", "value"))
def load_building_tabs(app_tab_value):
    """
    Load building tabs when the preloaded tab is selected
    """
    if app_tab_value != "tab-preloaded":
        return []

    try:
        # Try to load buildings info file from S3
        s3_buildings_info_path = environ.get(
            "S3_BUILDINGS_INFO_PATH", "buildings/buildings_info.pkl"
        )
        buildings_info = load_pickle_from_s3(s3_buildings_info_path)

        # Check if we couldn't load the data
        if buildings_info is None:
            # Try looking for individual building files directly
            try:
                s3_client = get_s3_client()
                bucket_name = environ.get("S3_BUCKET_NAME")

                if not bucket_name:
                    raise ValueError("S3_BUCKET_NAME not set")

                # List objects in the buildings directory
                response = s3_client.list_objects_v2(
                    Bucket=bucket_name, Prefix="buildings/"
                )

                # Extract building names from filenames
                building_names = []
                for obj in response.get("Contents", []):
                    filename = obj["Key"]
                    if filename.endswith(".pkl") and not filename.endswith(
                        "buildings_info.pkl"
                    ):
                        # Extract building name from filename
                        base_name = (
                            os.path.basename(filename)
                            .replace(".pkl", "")
                            .replace("building_", "")
                        )
                        # Convert back to original format
                        building_name = base_name.replace("_", " ")
                        building_names.append(building_name)

                if building_names:
                    print(
                        f"Found {len(building_names)} buildings by listing S3 directory"
                    )
                else:
                    return [
                        dcc.Tab(
                            label="No buildings found in S3",
                            value="none",
                            disabled=True,
                            style={"color": COLORS["accent"]},
                        )
                    ]
            except Exception as e:
                print(f"Error listing S3 directory: {str(e)}")
                return [
                    dcc.Tab(
                        label="Error loading buildings",
                        value="error",
                        disabled=True,
                        style={"color": "red"},
                    )
                ]
        else:
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

        # Initialize background loading with all building names
        initialize_background_loading(building_names)

        # Create a tab for each building, limited to 9 tabs
        building_tabs = []
        # Limit to the first 9 buildings
        visible_buildings = building_names[:9]
        for idx, name in enumerate(visible_buildings):
            # Add a loading state to each tab initially
            building_tabs.append(
                dcc.Tab(
                    label=f"{name}",
                    value=name,
                    className="custom-tab",
                    selected_className="custom-tab--selected",
                )
            )

        # Create the complete tabs array with both building tabs and hidden components
        tabs = building_tabs.copy()

        # Add a hidden interval component to handle background loading
        hidden_components = [
            dcc.Interval(
                id="background-loading-interval",
                interval=BACKGROUND_LOAD_INTERVAL * 1000,  # Convert to milliseconds
                n_intervals=0,
            ),
            # Also add a hidden div to store the building names
            html.Div(
                id="building-names-store",
                style={"display": "none"},
                children=json.dumps(building_names),
            ),
            # Add a hidden div for background loading status
            html.Div(
                id="background-loading-status",
                style={"display": "none"},
            ),
        ]

        # Add the hidden components separately from the tabs
        tabs.extend(hidden_components)

        return tabs

    except Exception as e:
        # Return a placeholder tab if there's an error
        print(f"Error in load_building_tabs: {str(e)}")
        return [
            dcc.Tab(
                label=f"Error loading buildings from S3: {str(e)}",
                value="error",
                disabled=True,
                style={"color": "red"},
            )
        ]


@callback(
    Output("background-loading-status", "children"),
    [Input("background-loading-interval", "n_intervals")],
    prevent_initial_call=True,  # Add this to prevent running on startup before queue is ready
)
def process_background_loading(n_intervals):
    """
    Process the background loading queue one building at a time
    """
    global LOADING_QUEUE, LOADING_IN_PROGRESS, CURRENTLY_LOADING, CURRENT_USER_BUILDING

    # Skip if nothing to do or already processing
    if not LOADING_QUEUE or LOADING_IN_PROGRESS:
        # print(f"Background loader skipping interval: Queue empty ({not LOADING_QUEUE}), In progress ({LOADING_IN_PROGRESS})")
        return dash.no_update

    # Create a cache object if it doesn't exist yet
    if not hasattr(load_preloaded_analysis, "building_cache"):
        load_preloaded_analysis.building_cache = {}

    LOADING_IN_PROGRESS = True
    print(f"\n--- Background Loader Interval {n_intervals} ---")
    print(f"Queue: {LOADING_QUEUE}")
    print(f"Cache keys: {list(load_preloaded_analysis.building_cache.keys())}")
    print(f"Currently Loading: {CURRENTLY_LOADING}")
    print(f"Current User Building: {CURRENT_USER_BUILDING}")

    building_to_load = None
    idx_to_process = -1  # Use -1 to indicate nothing found yet

    try:
        # Find the first item in the queue that we can either load or remove (if cached)
        for idx, building_name in enumerate(LOADING_QUEUE):
            idx_to_process = idx  # Store the index of the item we are considering

            # 1. Check if already cached
            if building_name in load_preloaded_analysis.building_cache:
                print(
                    f"Background loader: '{building_name}' already cached. Removing from queue."
                )
                # Action: Remove from queue, then stop processing for this interval
                LOADING_QUEUE.pop(idx_to_process)
                building_to_load = None  # Ensure we don't try to load it
                idx_to_process = -1  # Reset index as action is done
                break  # Stop checking queue for this interval

            # 2. Check if it's the current user building
            if building_name == CURRENT_USER_BUILDING:
                print(
                    f"Background loader: Skipping '{building_name}' (current user selection). Will check next interval."
                )
                # Action: Skip, do nothing else for this item, continue loop
                continue  # Check next item in the queue

            # 3. Check if it's already being loaded (by main or previous background)
            if building_name in CURRENTLY_LOADING:
                print(
                    f"Background loader: Skipping '{building_name}' (already loading). Will check next interval."
                )
                # Action: Skip, do nothing else for this item, continue loop
                continue  # Check next item in the queue

            # 4. If none of the above, we found one to load!
            print(f"Background loader: Found '{building_name}' to load.")
            building_to_load = building_name
            # Keep idx_to_process = idx
            break  # Stop checking queue, we have our target for this interval

        # --- End of loop ---

        # Now, perform the load if we found a building
        if building_to_load is not None and idx_to_process >= 0:
            # Remove from queue *before* loading
            actual_building_name = LOADING_QUEUE.pop(idx_to_process)
            if actual_building_name != building_to_load:
                # This should ideally not happen with pop(idx), but safety check
                print(
                    f"ERROR: Popped '{actual_building_name}' but expected '{building_to_load}'"
                )
                # Put it back maybe? Or handle error state
                LOADING_IN_PROGRESS = False
                return dash.no_update  # Avoid proceeding with wrong building

            # Mark this building as currently loading for the background task
            CURRENTLY_LOADING.add(building_to_load)
            print(f"Background loading building: {building_to_load}")
            print(f"Queue after pop: {LOADING_QUEUE}")
            start_time = time.time()

            try:
                # Load the building data
                building_data = load_building_data_from_s3(building_to_load)

                if building_data is not None:
                    # Add to cache
                    load_preloaded_analysis.building_cache[building_to_load] = (
                        building_data
                    )
                    elapsed = time.time() - start_time
                    print(
                        f"Background loaded and cached '{building_to_load}' in {elapsed:.2f} seconds"
                    )
                else:
                    # If loading failed, just log
                    print(f"Failed to background load {building_to_load}")
            finally:
                # Ensure we remove from loading set even if loading fails
                if building_to_load in CURRENTLY_LOADING:
                    CURRENTLY_LOADING.remove(building_to_load)
                print(f"Removed '{building_to_load}' from CURRENTLY_LOADING")

        elif idx_to_process == -1 and building_to_load is None:
            print(
                "Background loader: No action taken this interval (either removed cached item or only found skippable items)."
            )

    except Exception as e:
        print(f"Error in background loading interval: {str(e)}")
        # If error, attempt to clear the current building from loading status if applicable
        if building_to_load and building_to_load in CURRENTLY_LOADING:
            CURRENTLY_LOADING.remove(building_to_load)
            print(f"Removed '{building_to_load}' from CURRENTLY_LOADING due to error.")

    # Reset flag for next interval
    LOADING_IN_PROGRESS = False
    print(f"--- Background Loader Interval {n_intervals} Complete ---")

    # Return no visible changes
    return dash.no_update
