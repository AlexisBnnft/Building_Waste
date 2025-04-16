import dash
from dash import dcc, html, Input, Output, State, dash_table
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
import base64
import io
from datetime import datetime

# ---------------------------------------------------------------------------- #
#                           Core Analysis Functions                            #
#          (Adapted from your original script to accept DataFrames)          #
# ---------------------------------------------------------------------------- #


def get_cooling_zonal_from_data(
    project_name, ahu_dat_df, iat_df, airflow_df, map_df, cooling_project_series
):
    """
    Computes zone-level cooling from DataFrames.
    Args:
        project_name (str): Name for logging/errors.
        ahu_dat_df (pd.DataFrame): AHU discharge temps (time x AHU).
        iat_df (pd.DataFrame): Zone temps (time x Zone).
        airflow_df (pd.DataFrame): Zone airflow (time x Zone).
        map_df (pd.DataFrame): Mapping with 'ZoneID' and 'AHUID' columns.
        cooling_project_series (pd.Series): Total building cooling (time index).
    Returns:
        pd.DataFrame or None: Zone-level cooling (time x Zone).
    """
    if ahu_dat_df is None or ahu_dat_df.empty:
        print(f"Skipping {project_name}: AHU data is missing or empty.")
        return None
    if iat_df is None or iat_df.empty:
        print(f"Skipping {project_name}: IAT data is missing or empty.")
        return None
    if airflow_df is None or airflow_df.empty:
        print(f"Skipping {project_name}: Airflow data is missing or empty.")
        return None
    if map_df is None or map_df.empty:
        print(f"Skipping {project_name}: Zone->AHU map is missing or empty.")
        return None
    if cooling_project_series is None or cooling_project_series.empty:
        print(f"Skipping {project_name}: Building cooling data is missing or empty.")
        return None

    # Ensure map_df has the right columns and set index
    if not {"ZoneID", "AHUID"}.issubset(map_df.columns):
        raise ValueError("Map DataFrame must contain 'ZoneID' and 'AHUID' columns.")
    map_df = map_df.set_index("ZoneID")

    # Align indices (assuming they are already datetime) - Use outer join initially
    all_indices = (
        ahu_dat_df.index.union(iat_df.index)
        .union(airflow_df.index)
        .union(cooling_project_series.index)
    )
    common_index = pd.date_range(
        start=all_indices.min(), end=all_indices.max(), freq="H"
    )  # Or choose appropriate freq

    # Reindex and forward fill (or choose another strategy)
    # Important: Ensure columns match VAV/Zone names expected
    ahu_dat_df = ahu_dat_df.reindex(common_index).ffill().bfill()
    iat_df = iat_df.reindex(common_index).ffill().bfill()
    airflow_df = airflow_df.reindex(common_index).ffill().bfill()
    cooling_project_series = (
        cooling_project_series.reindex(common_index).ffill().bfill()
    )

    # Filter IAT and Airflow columns to only those in the map
    valid_zones = map_df.index.intersection(iat_df.columns).intersection(
        airflow_df.columns
    )
    iat = iat_df[valid_zones]
    airflow = airflow_df[valid_zones]
    map_df = map_df.loc[valid_zones]  # Filter map too

    # Filter AHU columns to only those in the map
    valid_ahus = map_df["AHUID"].unique()
    dat_ahu = ahu_dat_df[[ahu for ahu in valid_ahus if ahu in ahu_dat_df.columns]]

    # --- Rest of the get_cooling_zonal logic ---
    dat_vav = pd.DataFrame(index=dat_ahu.index, columns=valid_zones)

    for ahu in map_df["AHUID"].unique():
        if ahu not in dat_ahu.columns:
            print(
                f"Warning: AHU {ahu} found in map but not in AHU data columns. Skipping."
            )
            continue
        # Get zones served by this AHU
        ahu_vavs = map_df[map_df["AHUID"] == ahu].index.tolist()

        # Assign AHU temp to these zones
        for vav in ahu_vavs:
            if vav in dat_vav.columns:
                dat_vav[vav] = dat_ahu[ahu]

    # Proportional factor
    prop = (iat - dat_vav) * airflow
    prop = prop.clip(lower=0)  # Equivalent to applymap(lambda x: max(x, 0))

    # Sum prop only over valid zones
    tot_prop = prop.sum(axis=1)

    cooling_zonal = pd.DataFrame(index=prop.index, columns=prop.columns)

    # Avoid division by zero
    safe_tot_prop = tot_prop.replace(
        0, np.nan
    )  # Replace 0 with NaN to avoid division errors

    for col in cooling_zonal.columns:
        # Check if cooling_project_series has values for the index
        cooling_values = cooling_project_series.reindex(prop.index).values
        # Element-wise multiplication and division
        cooling_zonal[col] = cooling_values * prop[col] / safe_tot_prop

    # Fill NaNs that resulted from division by zero or initial alignment
    cooling_zonal.fillna(0, inplace=True)
    # Drop rows where all zones are 0 (optional, might happen due to reindexing)
    cooling_zonal = cooling_zonal.loc[(cooling_zonal != 0).any(axis=1)]

    return cooling_zonal


def categorize_cooling_by_iat_bins_from_data(
    project_name, iat_df, hsp_df, csp_df, df_cooling_zonal
):
    """
    Categorizes zone-level cooling into 6 bins based on IAT relative to setpoints.
    Args:
        project_name (str): Name for logging.
        iat_df (pd.DataFrame): Zone temps (time x Zone).
        hsp_df (pd.DataFrame): Heating setpoints (time x Zone).
        csp_df (pd.DataFrame): Cooling setpoints (time x Zone).
        df_cooling_zonal (pd.DataFrame): Result from get_cooling_zonal_from_data.
    Returns:
        pd.DataFrame or None: Cooling summed into bins (time x Bin).
    """
    if df_cooling_zonal is None or df_cooling_zonal.empty:
        print(f"Skipping binning for {project_name}: No valid zone cooling data.")
        return None
    if iat_df is None or iat_df.empty:
        print(f"Skipping binning for {project_name}: IAT data is missing or empty.")
        return None
    if hsp_df is None or hsp_df.empty:
        print(f"Skipping binning for {project_name}: HSP data is missing or empty.")
        return None
    if csp_df is None or csp_df.empty:
        print(f"Skipping binning for {project_name}: CSP data is missing or empty.")
        return None

    # Align indices and columns - crucial step
    common_index = df_cooling_zonal.index
    common_cols = df_cooling_zonal.columns

    # Use reindex, allow filling but maybe log if shapes mismatch significantly
    iat = iat_df.reindex(index=common_index, columns=common_cols).ffill().bfill()
    hsp = hsp_df.reindex(index=common_index, columns=common_cols).ffill().bfill()
    csp = csp_df.reindex(index=common_index, columns=common_cols).ffill().bfill()

    # Check if alignment resulted in empty frames
    if iat.empty or hsp.empty or csp.empty:
        print(f"Error during alignment for {project_name}. Check data consistency.")
        return None

    # --- Rest of the categorize_cooling_by_iat_bins logic ---
    temp_range = (csp - hsp).clip(lower=0)
    bin_cut_25 = hsp + 0.25 * temp_range
    bin_cut_50 = hsp + 0.50 * temp_range
    bin_cut_75 = hsp + 0.75 * temp_range
    bin_cut_100 = csp  # Using CSP as the top of the 5th bin

    # Boolean masks (ensure they align with df_cooling_zonal's shape)
    bin1 = iat < hsp
    bin2 = (iat >= hsp) & (iat < bin_cut_25)
    bin3 = (iat >= bin_cut_25) & (iat < bin_cut_50)
    bin4 = (iat >= bin_cut_50) & (iat < bin_cut_75)
    bin5 = (iat >= bin_cut_75) & (iat < bin_cut_100)  # Updated bin5 definition
    bin6 = iat >= bin_cut_100  # New bin6

    # Sum cooling within each bin
    # Important: Use .where() which keeps the shape, then sum
    bin1_cooling = df_cooling_zonal.where(bin1, 0).sum(axis=1)
    bin2_cooling = df_cooling_zonal.where(bin2, 0).sum(axis=1)
    bin3_cooling = df_cooling_zonal.where(bin3, 0).sum(axis=1)
    bin4_cooling = df_cooling_zonal.where(bin4, 0).sum(axis=1)
    bin5_cooling = df_cooling_zonal.where(bin5, 0).sum(axis=1)
    bin6_cooling = df_cooling_zonal.where(bin6, 0).sum(axis=1)

    df_bin_cooling = pd.DataFrame(
        {
            "bin1_IAT<HSP": bin1_cooling,
            "bin2_0-25%": bin2_cooling,
            "bin3_25-50%": bin3_cooling,
            "bin4_50-75%": bin4_cooling,
            "bin5_75-100%": bin5_cooling,
            "bin6_IAT>CSP": bin6_cooling,  # Added bin6
        },
        index=common_index,
    )  # Ensure index is consistent

    return df_bin_cooling


# ---------------------------------------------------------------------------- #
#                             Plotting Functions                               #
#                      (Create Plotly figures)                                 #
# ---------------------------------------------------------------------------- #


def create_stacked_area_plot(df_bin_cooling, title, yaxis_title, normalize=False):
    """Creates a Plotly stacked area plot figure."""
    if df_bin_cooling is None or df_bin_cooling.empty:
        return go.Figure(layout=go.Layout(title=title + " (No Data)"))

    # Ensure specific column order for consistent coloring/stacking
    bin_cols_ordered = [
        "bin1_IAT<HSP",
        "bin2_0-25%",
        "bin3_25-50%",
        "bin4_50-75%",
        "bin5_75-100%",
        "bin6_IAT>CSP",
    ]
    # Only include columns that actually exist in the dataframe
    cols_to_plot = [col for col in bin_cols_ordered if col in df_bin_cooling.columns]
    df_plot = df_bin_cooling[cols_to_plot]

    if normalize:
        df_plot = df_plot.div(df_plot.sum(axis=1), axis=0).fillna(0)
        yaxis_title = "Fraction of Total Cooling"

    fig = go.Figure()

    # Use Plotly Express for simpler stacking? Or manual go.Scatter
    # Let's use manual go.Scatter for more control
    colors = px.colors.sequential.Blues  # Use a blue color scale

    for i, col in enumerate(cols_to_plot):
        fig.add_trace(
            go.Scatter(
                x=df_plot.index,
                y=df_plot[col],
                name=col.replace("_", " "),  # Nicer legend name
                mode="lines",
                line=dict(
                    width=0.5, color=colors[i + 2 if i + 2 < len(colors) else -1]
                ),  # Pick colors
                stackgroup="one",  # Defines groups for stacking
                # groupnorm='percent' if normalize else None # Alternative normalization
                hoverinfo="x+y+name",
            )
        )

    fig.update_layout(
        title=title,
        xaxis_title="Time",
        yaxis_title=yaxis_title,
        hovermode="x unified",
        legend_title="IAT Bins",
        margin=dict(l=40, r=40, t=60, b=40),
    )
    return fig


def create_regrouped_stacked_area_plot(
    df_bin_cooling, title, yaxis_title, normalize=False
):
    """Creates a Plotly stacked area plot for regrouped bins."""
    if df_bin_cooling is None or df_bin_cooling.empty:
        return go.Figure(layout=go.Layout(title=title + " (No Data)"))

    df_grouped = pd.DataFrame(index=df_bin_cooling.index)
    # Summing, using .get() with default 0 handles potentially missing bin columns
    df_grouped["Wasted"] = df_bin_cooling.get("bin1_IAT<HSP", 0)
    df_grouped["Excess"] = df_bin_cooling.get("bin2_0-25%", 0) + df_bin_cooling.get(
        "bin3_25-50%", 0
    )
    df_grouped["Useful"] = (
        df_bin_cooling.get("bin4_50-75%", 0)
        + df_bin_cooling.get("bin5_75-100%", 0)
        + df_bin_cooling.get("bin6_IAT>CSP", 0)
    )

    if normalize:
        df_grouped = df_grouped.div(df_grouped.sum(axis=1), axis=0).fillna(0)
        yaxis_title = "Fraction of Total Cooling"

    fig = go.Figure()
    colors = {"Wasted": "lightcoral", "Excess": "gold", "Useful": "forestgreen"}
    category_order = ["Wasted", "Excess", "Useful"]  # Control stacking order

    for category in category_order:
        fig.add_trace(
            go.Scatter(
                x=df_grouped.index,
                y=df_grouped[category],
                name=category,
                mode="lines",
                line=dict(width=0.5, color=colors[category]),
                stackgroup="one",
                hoverinfo="x+y+name",
            )
        )

    fig.update_layout(
        title=title,
        xaxis_title="Time",
        yaxis_title=yaxis_title,
        hovermode="x unified",
        legend_title="Cooling Category",
        margin=dict(l=40, r=40, t=60, b=40),
    )
    return fig


# Add bar plot creation functions for the zone analysis
def create_wasteful_zones_bar_plot(top_wasteful_df):
    """Creates a horizontal bar plot of the most wasteful zones."""
    if top_wasteful_df is None or top_wasteful_df.empty:
        return go.Figure().update_layout(
            title="No data available for wasteful zones", height=400
        )

    # Sort by cooling value (ascending for horizontal bar chart)
    df = top_wasteful_df.sort_values("Wasteful Cooling (Bin 1)")

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=df["Zone"],
            x=df["Wasteful Cooling (Bin 1)"],
            orientation="h",
            marker_color="#e74c3c",  # Red
            text=df["% of Total Waste"].apply(lambda x: f"{x:.1f}%"),
            textposition="auto",
            hovertemplate="<b>%{y}</b><br>Wasted Cooling: %{x:.1f}<br>% of Total Waste: %{text}<extra></extra>",
        )
    )

    fig.update_layout(
        title="Top Wasteful Zones",
        xaxis_title="Cooling Energy",
        yaxis=dict(
            autorange="reversed"
        ),  # Reverse to match table order (highest at top)
        height=400,
        margin=dict(l=20, r=20, t=40, b=20),
        template="plotly_white",
    )

    return fig


def create_demanding_zones_bar_plot(top_demanding_df):
    """Creates a horizontal bar plot of the most demanding zones."""
    if top_demanding_df is None or top_demanding_df.empty:
        return go.Figure().update_layout(
            title="No data available for demanding zones", height=400
        )

    # Sort by cooling value (ascending for horizontal bar chart)
    df = top_demanding_df.sort_values("Total Cooling")

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=df["Zone"],
            x=df["Total Cooling"],
            orientation="h",
            marker_color="#3498db",  # Blue
            text=df["% of Building Total"].apply(lambda x: f"{x:.1f}%"),
            textposition="auto",
            hovertemplate="<b>%{y}</b><br>Total Cooling: %{x:.1f}<br>% of Building Total: %{text}<extra></extra>",
        )
    )

    fig.update_layout(
        title="Top Demanding Zones",
        xaxis_title="Cooling Energy",
        yaxis=dict(
            autorange="reversed"
        ),  # Reverse to match table order (highest at top)
        height=400,
        margin=dict(l=20, r=20, t=40, b=20),
        template="plotly_white",
    )

    return fig


# ---------------------------------------------------------------------------- #
#                              Dash App Layout                                 #
# ---------------------------------------------------------------------------- #

app = dash.Dash(
    __name__,
    suppress_callback_exceptions=True,
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)
server = app.server
app.title = "Building Cooling Analysis"

# Custom CSS for better styling
colors = {
    "background": "#f9f9f9",
    "text": "#2c3e50",
    "primary": "#3498db",
    "secondary": "#2ecc71",
    "accent": "#e74c3c",
    "light": "#ecf0f1",
    "dark": "#34495e",
    "border": "#bdc3c7",
}

# Sample format descriptions
file_descriptions = {
    "iat": """
    Expected format for zone_temps.csv:
    timestamp,Zone1,Zone2,Zone3,...
    2023-01-01 00:00:00,72.5,73.0,71.8,...
    2023-01-01 01:00:00,72.8,73.2,71.9,...
    """,
    "hsp": """
    Expected format for zone_heating_setpoints.csv:
    timestamp,Zone1,Zone2,Zone3,...
    2023-01-01 00:00:00,68.0,68.0,68.0,...
    2023-01-01 01:00:00,68.0,68.0,68.0,...
    """,
    "csp": """
    Expected format for zone_cooling_setpoints.csv:
    timestamp,Zone1,Zone2,Zone3,...
    2023-01-01 00:00:00,74.0,74.0,74.0,...
    2023-01-01 01:00:00,74.0,74.0,74.0,...
    """,
    "airflow": """
    Expected format for zone_airflow.csv:
    timestamp,Zone1,Zone2,Zone3,...
    2023-01-01 00:00:00,100.5,95.0,110.8,...
    2023-01-01 01:00:00,102.8,96.2,109.9,...
    """,
    "ahu_dat": """
    Expected format for ahu_discharge_temps.csv:
    timestamp,AHU1,AHU2,AHU3,...
    2023-01-01 00:00:00,55.5,56.0,55.8,...
    2023-01-01 01:00:00,55.8,56.2,55.9,...
    """,
    "map": """
    Expected format for zone_to_ahu_map.csv:
    ZoneID,AHUID
    Zone1,AHU1
    Zone2,AHU1
    Zone3,AHU2
    ...
    """,
    "cooling": """
    Expected format for building_total_cooling.csv:
    timestamp,cooling_value
    2023-01-01 00:00:00,150.5
    2023-01-01 01:00:00,155.8
    ...
    """,
}


# File upload component with consistent styling
def create_upload_component(id_name, label, description):
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
                                    "backgroundColor": colors["light"],
                                    "cursor": "pointer",
                                },
                                multiple=False,
                            ),
                            html.Span(
                                id=f"status-{component_id}",
                                style={
                                    "marginLeft": "10px",
                                    "color": colors["primary"],
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
                        style={"cursor": "pointer", "color": colors["primary"]},
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


app.layout = html.Div(
    [
        # Header
        html.Div(
            [
                html.H1(
                    "Building Cooling Distribution Analysis",
                    style={"color": colors["dark"]},
                ),
                html.P(
                    "Upload building data files to analyze cooling distribution across temperature zones. "
                    "This dashboard visualizes how cooling is distributed relative to temperature setpoints.",
                    style={
                        "fontSize": "1.1em",
                        "color": colors["text"],
                        "maxWidth": "800px",
                        "margin": "0 auto 20px auto",
                    },
                ),
            ],
            style={
                "textAlign": "center",
                "padding": "20px 0",
                "backgroundColor": colors["light"],
                "borderBottom": f"3px solid {colors['primary']}",
            },
        ),
        # Main content
        html.Div(
            [
                # File upload section
                html.Div(
                    [
                        html.H2(
                            "Data Upload",
                            style={
                                "borderBottom": f"2px solid {colors['primary']}",
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
                                    file_descriptions["iat"],
                                ),
                                create_upload_component(
                                    "upload-hsp",
                                    "Zone Heating Setpoints",
                                    file_descriptions["hsp"],
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
                                    file_descriptions["csp"],
                                ),
                                create_upload_component(
                                    "upload-airflow",
                                    "Zone Airflow",
                                    file_descriptions["airflow"],
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
                                    file_descriptions["ahu_dat"],
                                ),
                                create_upload_component(
                                    "upload-map",
                                    "Zone to AHU Map",
                                    file_descriptions["map"],
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
                                    file_descriptions["cooling"],
                                ),
                            ],
                            style={"marginBottom": "20px"},
                        ),
                        # Analysis controls
                        html.Div(
                            [
                                html.Label(
                                    "Resample Frequency: ",
                                    style={"fontWeight": "bold", "marginRight": "10px"},
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
                                    style={"width": "200px", "display": "inline-block"},
                                ),
                                html.Button(
                                    "Run Analysis",
                                    id="run-button",
                                    n_clicks=0,
                                    style={
                                        "marginLeft": "20px",
                                        "backgroundColor": colors["primary"],
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
                                "backgroundColor": colors["light"],
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
                                "backgroundColor": colors["light"],
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
                    color=colors["primary"],
                    children=[
                        html.Div(
                            [
                                html.H2(
                                    "Analysis Results",
                                    style={
                                        "borderBottom": f"2px solid {colors['primary']}",
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
                                        # NEW: Placeholder for Zone Ranking Tables
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
                                            # Grid layout for the two new tables side-by-side
                                            style={
                                                "display": "grid",
                                                "gridTemplateColumns": "1fr 1fr",  # Two equal columns
                                                "gap": "20px",
                                                "marginBottom": "20px",
                                            },
                                        ),
                                    ]
                                ),
                                # Summary table (Original)
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
                html.Div(
                    [
                        html.Hr(style={"margin": "40px 0 20px 0"}),
                        html.H3(
                            "About This Dashboard", style={"color": colors["dark"]}
                        ),
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
                                html.A(
                                    "Dash",
                                    href="https://dash.plotly.com/",
                                    target="_blank",
                                ),
                                " and ",
                                html.A(
                                    "Plotly",
                                    href="https://plotly.com/",
                                    target="_blank",
                                ),
                            ],
                            style={
                                "fontSize": "0.9em",
                                "textAlign": "center",
                                "marginTop": "30px",
                                "color": colors["dark"],
                            },
                        ),
                    ],
                    style={
                        "marginTop": "40px",
                        "backgroundColor": colors["light"],
                        "padding": "20px",
                        "borderRadius": "8px",
                    },
                ),
            ],
            style={"maxWidth": "1200px", "margin": "0 auto", "padding": "20px"},
        ),
    ],
    style={
        "backgroundColor": colors["background"],
        "minHeight": "100vh",
        "fontFamily": "Arial, sans-serif",
    },
)

# ---------------------------------------------------------------------------- #
#                              Dash App Callbacks                              #
# ---------------------------------------------------------------------------- #


def parse_content(contents, filename):
    """Helper function to parse uploaded CSV."""
    if contents is None:
        return None, html.Div(
            ["❌ No file uploaded."],
            style={"color": colors["accent"], "fontWeight": "bold"},
        )

    content_type, content_string = contents.split(",")
    decoded = base64.b64decode(content_string)
    try:
        # Assume CSV for now
        if "csv" in filename:
            # Use StringIO to simulate a file
            df = pd.read_csv(io.StringIO(decoded.decode("utf-8")))
            # Attempt to set datetime index (assuming first column is datetime)
            try:
                # Special case for map file which might not have datetime
                if "map" not in filename:
                    df[df.columns[0]] = pd.to_datetime(df[df.columns[0]])
                    df = df.set_index(df.columns[0])
                    df.index.name = "Timestamp"  # Standardize index name

                # Return success message with styled div for green indicator
                success_message = html.Div(
                    [
                        html.Span(
                            "✅", style={"marginRight": "8px", "fontSize": "16px"}
                        ),
                        f"Successfully loaded {filename}",
                    ],
                    style={
                        "backgroundColor": colors["secondary"]
                        + "30",  # Light green with transparency
                        "color": colors["secondary"],
                        "fontWeight": "bold",
                        "padding": "8px 12px",
                        "borderRadius": "4px",
                        "border": f"1px solid {colors['secondary']}",
                        "display": "inline-block",
                        "marginTop": "5px",
                        "transition": "all 0.3s ease",
                        "boxShadow": "0 2px 4px rgba(0,0,0,0.1)",
                    },
                )

                return df, success_message
            except Exception as e:
                return (
                    None,
                    html.Div(
                        [
                            html.Span(
                                "❌", style={"marginRight": "8px", "fontSize": "16px"}
                            ),
                            f"Error parsing datetime index: {e}. Check first column.",
                        ],
                        style={
                            "backgroundColor": colors["accent"]
                            + "20",  # Light red with transparency
                            "color": colors["accent"],
                            "fontWeight": "bold",
                            "padding": "8px 12px",
                            "borderRadius": "4px",
                            "border": f"1px solid {colors['accent']}",
                            "display": "inline-block",
                            "marginTop": "5px",
                        },
                    ),
                )
        else:
            return None, html.Div(
                [
                    html.Span("❌", style={"marginRight": "8px", "fontSize": "16px"}),
                    f"File '{filename}' is not a CSV.",
                ],
                style={
                    "backgroundColor": colors["accent"] + "20",
                    "color": colors["accent"],
                    "fontWeight": "bold",
                    "padding": "8px 12px",
                    "borderRadius": "4px",
                    "border": f"1px solid {colors['accent']}",
                    "display": "inline-block",
                    "marginTop": "5px",
                },
            )
    except Exception as e:
        return None, html.Div(
            [
                html.Span("❌", style={"marginRight": "8px", "fontSize": "16px"}),
                f"Error: {e}",
            ],
            style={
                "backgroundColor": colors["accent"] + "20",
                "color": colors["accent"],
                "fontWeight": "bold",
                "padding": "8px 12px",
                "borderRadius": "4px",
                "border": f"1px solid {colors['accent']}",
                "display": "inline-block",
                "marginTop": "5px",
            },
        )


@app.callback(
    Output("status-iat", "children"),
    [Input("upload-iat", "contents")],
    [State("upload-iat", "filename")],
)
def update_iat_status(contents, filename):
    if contents is None:
        return ""
    df, status = parse_content(contents, filename)
    return status


@app.callback(
    Output("status-hsp", "children"),
    [Input("upload-hsp", "contents")],
    [State("upload-hsp", "filename")],
)
def update_hsp_status(contents, filename):
    if contents is None:
        return ""
    df, status = parse_content(contents, filename)
    return status


@app.callback(
    Output("status-csp", "children"),
    [Input("upload-csp", "contents")],
    [State("upload-csp", "filename")],
)
def update_csp_status(contents, filename):
    if contents is None:
        return ""
    df, status = parse_content(contents, filename)
    return status


@app.callback(
    Output("status-airflow", "children"),
    [Input("upload-airflow", "contents")],
    [State("upload-airflow", "filename")],
)
def update_airflow_status(contents, filename):
    if contents is None:
        return ""
    df, status = parse_content(contents, filename)
    return status


@app.callback(
    Output("status-ahu-dat", "children"),
    [Input("upload-ahu-dat", "contents")],
    [State("upload-ahu-dat", "filename")],
)
def update_ahu_dat_status(contents, filename):
    if contents is None:
        return ""
    df, status = parse_content(contents, filename)
    return status


@app.callback(
    Output("status-map", "children"),
    [Input("upload-map", "contents")],
    [State("upload-map", "filename")],
)
def update_map_status(contents, filename):
    if contents is None:
        return ""
    df, status = parse_content(contents, filename)
    return status


@app.callback(
    Output("status-cooling", "children"),
    [Input("upload-cooling", "contents")],
    [State("upload-cooling", "filename")],
)
def update_cooling_status(contents, filename):
    if contents is None:
        return ""
    df, status = parse_content(contents, filename)
    return status


@app.callback(
    [
        Output("status-output", "children"),
        Output("graph-bins-absolute", "figure"),
        Output("graph-bins-fractional", "figure"),
        Output("graph-regrouped-absolute", "figure"),
        Output("graph-regrouped-fractional", "figure"),
        Output("summary-table-div", "children"),
        Output("wasteful-zones-table-div", "children"),
        Output("demanding-zones-table-div", "children"),
        Output("wasteful-zones-plot-div", "children"),
        Output("demanding-zones-plot-div", "children"),
    ],
    [Input("run-button", "n_clicks")],
    [
        State("upload-iat", "contents"),
        State("upload-iat", "filename"),
        State("upload-hsp", "contents"),
        State("upload-hsp", "filename"),
        State("upload-csp", "contents"),
        State("upload-csp", "filename"),
        State("upload-airflow", "contents"),
        State("upload-airflow", "filename"),
        State("upload-ahu-dat", "contents"),
        State("upload-ahu-dat", "filename"),
        State("upload-map", "contents"),
        State("upload-map", "filename"),
        State("upload-cooling", "contents"),
        State("upload-cooling", "filename"),
        State("resample-freq-dropdown", "value"),
    ],
)
def update_dashboard(
    n_clicks,
    iat_contents,
    iat_filename,
    hsp_contents,
    hsp_filename,
    csp_contents,
    csp_filename,
    airflow_contents,
    airflow_filename,
    ahu_dat_contents,
    ahu_dat_filename,
    map_contents,
    map_filename,
    cooling_contents,
    cooling_filename,
    resample_freq,
):

    if n_clicks == 0:
        # Initial load, return empty figures and default messages
        empty_fig = go.Figure()
        empty_fig.update_layout(
            plot_bgcolor=colors["light"],
            paper_bgcolor=colors["light"],
            xaxis=dict(
                showgrid=False,
                showticklabels=False,
            ),
            yaxis=dict(
                showgrid=False,
                showticklabels=False,
            ),
            annotations=[
                dict(
                    text="Upload data and click 'Run Analysis'",
                    showarrow=False,
                    font=dict(size=16, color=colors["dark"]),
                    xref="paper",
                    yref="paper",
                    x=0.5,
                    y=0.5,
                )
            ],
        )
        return (
            ["Waiting for data upload..."] + [empty_fig] * 4 + [None] * 5
        )  # 5 None values now

    ctx = dash.callback_context
    if not ctx.triggered or ctx.triggered[0]["prop_id"] != "run-button.n_clicks":
        # Don't update if callback was triggered by something else initially
        raise dash.exceptions.PreventUpdate

    # --- 1. Parse all uploads ---
    data_dict = {}
    uploads = [
        ("iat", iat_contents, iat_filename),
        ("hsp", hsp_contents, hsp_filename),
        ("csp", csp_contents, csp_filename),
        ("airflow", airflow_contents, airflow_filename),
        ("ahu_dat", ahu_dat_contents, ahu_dat_filename),
        ("map", map_contents, map_filename),
        ("cooling", cooling_contents, cooling_filename),
    ]

    valid_uploads = True

    for key, contents, filename in uploads:
        df, status = parse_content(
            contents, filename if filename else f"Required File {key}"
        )
        if df is None:
            valid_uploads = False
            data_dict[key] = None
        else:
            data_dict[key] = df

    if not valid_uploads:
        error_fig = go.Figure()
        error_fig.update_layout(
            plot_bgcolor=colors["light"],
            paper_bgcolor=colors["light"],
            annotations=[
                dict(
                    text="Error in uploaded files. Check formats and try again.",
                    showarrow=False,
                    font=dict(size=16, color=colors["accent"]),
                    xref="paper",
                    yref="paper",
                    x=0.5,
                    y=0.5,
                )
            ],
        )
        return (
            [
                html.Div(
                    "⚠️ Error: Please check uploaded files and formats.",
                    style={"color": colors["accent"]},
                ),
            ]
            + [error_fig] * 4
            + [None] * 5  # None for all tables and plots
        )

    # --- 2. Run Analysis ---
    try:
        status_output = html.Div(
            "⏳ Processing... Calculating zone cooling allocation.",
            style={"color": colors["primary"]},
        )
        # Assume project name from a filename or set default
        project_name = "UploadedBuilding"

        # Extract the single column Series for total cooling
        cooling_series = data_dict["cooling"].iloc[:, 0]

        df_cooling_zonal = get_cooling_zonal_from_data(
            project_name,
            data_dict["ahu_dat"],
            data_dict["iat"],
            data_dict["airflow"],
            data_dict["map"],
            cooling_series,
        )

        if df_cooling_zonal is None or df_cooling_zonal.empty:
            error_msg = "Error during zone cooling calculation. Check data consistency."
            error_fig = go.Figure()
            error_fig.update_layout(
                plot_bgcolor=colors["light"],
                paper_bgcolor=colors["light"],
                annotations=[
                    dict(
                        text=error_msg,
                        showarrow=False,
                        font=dict(size=16, color=colors["accent"]),
                        xref="paper",
                        yref="paper",
                        x=0.5,
                        y=0.5,
                    )
                ],
            )
            return (
                [
                    html.Div(f"⚠️ {error_msg}", style={"color": colors["accent"]}),
                ]
                + [error_fig] * 4
                + [None] * 5  # None for all tables and plots
            )

        # Get aligned IAT and HSP needed for wasteful calculation
        # Align indices and columns - reusing logic from binning function
        common_index = df_cooling_zonal.index
        common_cols = df_cooling_zonal.columns
        aligned_iat = (
            data_dict["iat"]
            .reindex(index=common_index, columns=common_cols)
            .ffill()
            .bfill()
        )
        aligned_hsp = (
            data_dict["hsp"]
            .reindex(index=common_index, columns=common_cols)
            .ffill()
            .bfill()
        )

        status_output = html.Div(
            "⏳ Processing... Categorizing cooling by IAT bins.",
            style={"color": colors["primary"]},
        )
        df_bin_cooling = categorize_cooling_by_iat_bins_from_data(
            project_name,
            data_dict["iat"],
            data_dict["hsp"],
            data_dict["csp"],
            df_cooling_zonal,
        )

        if df_bin_cooling is None or df_bin_cooling.empty:
            error_msg = "Error during IAT bin categorization. Check data consistency."
            error_fig = go.Figure()
            error_fig.update_layout(
                plot_bgcolor=colors["light"],
                paper_bgcolor=colors["light"],
                annotations=[
                    dict(
                        text=error_msg,
                        showarrow=False,
                        font=dict(size=16, color=colors["accent"]),
                        xref="paper",
                        yref="paper",
                        x=0.5,
                        y=0.5,
                    )
                ],
            )
            return (
                [
                    html.Div(f"⚠️ {error_msg}", style={"color": colors["accent"]}),
                ]
                + [error_fig] * 4
                + [None] * 5  # None for all tables and plots
            )

        status_output = html.Div(
            "⏳ Processing... Generating plots.", style={"color": colors["primary"]}
        )

        # --- 3. Resample Data for Plotting ---
        # Use .sum() for resampling energy values
        try:
            # Ensure index is datetime before resampling
            df_bin_cooling.index = pd.to_datetime(df_bin_cooling.index)
            df_bin_resampled = df_bin_cooling.resample(resample_freq).sum()
        except Exception as e:
            status_output = html.Div(
                f"⚠️ Error resampling data to frequency '{resample_freq}': {e}. Using original frequency.",
                style={"color": colors["accent"]},
            )
            df_bin_resampled = (
                df_bin_cooling  # Fallback to original if resampling fails
            )

        # --- 4. Generate Plots with improved styling ---
        freq_name = {"H": "Hourly", "D": "Daily", "W": "Weekly", "M": "Monthly"}.get(
            resample_freq, resample_freq
        )

        plot_template = "plotly_white"  # Use a clean template

        # Create better looking plots with consistent styling
        fig_bins_abs = create_stacked_area_plot(
            df_bin_resampled,
            f"Cooling by IAT Bins ({freq_name})",
            "Cooling Energy",
            normalize=False,
        )
        fig_bins_abs.update_layout(
            template=plot_template,
            height=500,
            legend=dict(
                orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5
            ),
        )

        fig_bins_frac = create_stacked_area_plot(
            df_bin_resampled,
            f"Cooling by IAT Bins ({freq_name})",
            "Fraction of Cooling",
            normalize=True,
        )
        fig_bins_frac.update_layout(
            template=plot_template,
            height=500,
            legend=dict(
                orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5
            ),
        )

        fig_regr_abs = create_regrouped_stacked_area_plot(
            df_bin_resampled,
            f"Cooling by Category ({freq_name})",
            "Cooling Energy",
            normalize=False,
        )
        fig_regr_abs.update_layout(
            template=plot_template,
            height=500,
            legend=dict(
                orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5
            ),
        )

        fig_regr_frac = create_regrouped_stacked_area_plot(
            df_bin_resampled,
            f"Cooling by Category ({freq_name})",
            "Fraction of Cooling",
            normalize=True,
        )
        fig_regr_frac.update_layout(
            template=plot_template,
            height=500,
            legend=dict(
                orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5
            ),
        )

        # --- 5. Create an enhanced Summary Table ---
        summary_data = df_bin_resampled.sum().reset_index()
        summary_data.columns = ["Bin", "Total Cooling"]
        summary_data["Percentage"] = (
            summary_data["Total Cooling"] / summary_data["Total Cooling"].sum() * 100
        ).round(1)

        # Add a color column for visual indication
        colors_dict = {
            "bin1_IAT<HSP": "#e74c3c",  # Red
            "bin2_0-25%": "#f39c12",  # Orange
            "bin3_25-50%": "#f1c40f",  # Yellow
            "bin4_50-75%": "#2ecc71",  # Light green
            "bin5_75-100%": "#27ae60",  # Green
            "bin6_IAT>CSP": "#16a085",  # Teal
        }

        summary_data["Color"] = summary_data["Bin"].map(
            lambda x: colors_dict.get(x, "#bdc3c7")
        )

        summary_table = dash_table.DataTable(
            data=summary_data.to_dict("records"),
            columns=[
                {"name": "Bin", "id": "Bin"},
                {
                    "name": "Total Cooling",
                    "id": "Total Cooling",
                    "type": "numeric",
                    "format": {"specifier": ",.1f"},
                },
                {
                    "name": "Percentage",
                    "id": "Percentage",
                    "type": "numeric",
                    "format": {"specifier": ".1f", "locale": {"symbol": ["%", ""]}},
                },
            ],
            style_cell={
                "textAlign": "left",
                "padding": "15px 5px",
                "backgroundColor": "white",
                "fontFamily": "Arial, sans-serif",
            },
            style_header={
                "backgroundColor": colors["light"],
                "fontWeight": "bold",
                "textAlign": "left",
                "border": f'1px solid {colors["border"]}',
            },
            style_data_conditional=[
                {
                    "if": {"row_index": i},
                    "backgroundColor": summary_data.iloc[i]["Color"]
                    + "20",  # Add transparency
                    "borderLeft": f'4px solid {summary_data.iloc[i]["Color"]}',
                }
                for i in range(len(summary_data))
            ]
            + [
                {
                    "if": {"column_id": "Percentage", "row_index": i},
                    "background": f"""
                        linear-gradient(90deg, 
                        {summary_data.iloc[i]['Color'] + '40'} 0%, 
                        {summary_data.iloc[i]['Color'] + '40'} {summary_data.iloc[i]['Percentage']}%, 
                        transparent {summary_data.iloc[i]['Percentage']}%, 
                        transparent 100%)
                    """,
                }
                for i in range(len(summary_data))
            ],
            style_as_list_view=False,
        )

        # Add category explanations
        category_explanations = html.Div(
            [
                html.H4(
                    "Summary Totals",
                    style={"marginBottom": "15px", "color": colors["dark"]},
                ),
                summary_table,
                html.Div(
                    [
                        html.P(
                            "Cooling Categories Explained:",
                            style={"fontWeight": "bold", "marginTop": "20px"},
                        ),
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.Div(
                                            style={
                                                "backgroundColor": "#e74c3c",
                                                "width": "20px",
                                                "height": "20px",
                                                "display": "inline-block",
                                                "marginRight": "10px",
                                            }
                                        ),
                                        html.Span(
                                            "Wasted: Temperature below heating setpoint (IAT < HSP)"
                                        ),
                                    ],
                                    style={"marginBottom": "5px"},
                                ),
                                html.Div(
                                    [
                                        html.Div(
                                            style={
                                                "backgroundColor": "#f39c12",
                                                "width": "20px",
                                                "height": "20px",
                                                "display": "inline-block",
                                                "marginRight": "10px",
                                            }
                                        ),
                                        html.Span(
                                            "Excess: Temperature in lower half of deadband (HSP to HSP+50%)"
                                        ),
                                    ],
                                    style={"marginBottom": "5px"},
                                ),
                                html.Div(
                                    [
                                        html.Div(
                                            style={
                                                "backgroundColor": "#27ae60",
                                                "width": "20px",
                                                "height": "20px",
                                                "display": "inline-block",
                                                "marginRight": "10px",
                                            }
                                        ),
                                        html.Span(
                                            "Useful: Temperature in upper half of deadband or higher (HSP+50% to CSP+)"
                                        ),
                                    ]
                                ),
                            ]
                        ),
                    ],
                    style={"marginTop": "15px"},
                ),
            ]
        )

        # NEW: Calculate Top Zones
        top_n = 10
        wasteful_zones_table_div = html.Div(
            "Could not calculate wasteful zones (missing IAT/HSP data?)"
        )
        demanding_zones_table_div = html.Div("Could not calculate demanding zones.")

        # Most Wasteful Zones (Bin 1 Cooling)
        try:
            # Check if needed aligned data exists
            if not aligned_iat.empty and not aligned_hsp.empty:
                bin1_mask = aligned_iat < aligned_hsp
                wasteful_cooling_ts = df_cooling_zonal.where(bin1_mask, 0)
                total_wasteful_per_zone = wasteful_cooling_ts.sum(
                    axis=0
                )  # Sum over time
                top_wasteful = total_wasteful_per_zone.nlargest(top_n).reset_index()
                top_wasteful.columns = ["Zone", "Wasteful Cooling (Bin 1)"]

                # Add percentage column relative to total Bin 1 cooling
                total_bin1_cooling = (
                    df_bin_cooling["bin1_IAT<HSP"].sum()
                    if "bin1_IAT<HSP" in df_bin_cooling.columns
                    else 0
                )
                if total_bin1_cooling > 0:
                    top_wasteful["% of Total Waste"] = (
                        top_wasteful["Wasteful Cooling (Bin 1)"]
                        / total_bin1_cooling
                        * 100
                    ).round(1)
                else:
                    top_wasteful["% of Total Waste"] = 0.0

                # Create table as before
                wasteful_table = dash_table.DataTable(
                    data=top_wasteful.to_dict("records"),
                    columns=[
                        {"name": "Zone", "id": "Zone"},
                        {
                            "name": "Wasteful Cooling",
                            "id": "Wasteful Cooling (Bin 1)",
                            "type": "numeric",
                            "format": {"specifier": ",.1f"},
                        },
                        {
                            "name": "% of Total Wasted",
                            "id": "% of Total Waste",
                            "type": "numeric",
                            "format": {
                                "specifier": ".1f",
                                "locale": {"symbol": ["%", ""]},
                            },
                        },
                    ],
                    style_cell={
                        "textAlign": "left",
                        "padding": "10px",
                        "fontFamily": "Arial, sans-serif",
                    },
                    style_header={
                        "backgroundColor": colors["light"],
                        "fontWeight": "bold",
                        "textAlign": "left",
                        "border": f'1px solid {colors["border"]}',
                    },
                    style_data_conditional=[
                        {
                            "if": {"row_index": i},
                            "backgroundColor": "#e74c3c20",  # Light red with transparency
                            "borderLeft": "4px solid #e74c3c",
                        }
                        for i in range(len(top_wasteful))
                    ],
                    page_size=top_n,
                )

                # Create table div
                wasteful_zones_table_div = html.Div(
                    [
                        html.H4(
                            f"Top {top_n} Most Wasteful Zones (Bin 1: IAT < HSP)",
                            style={"color": colors["dark"], "marginBottom": "15px"},
                        ),
                        wasteful_table,
                    ]
                )

                # Create plot
                wasteful_zones_plot = create_wasteful_zones_bar_plot(top_wasteful)
                wasteful_zones_plot_div = dcc.Graph(figure=wasteful_zones_plot)

            else:
                wasteful_zones_table_div = html.Div(
                    [
                        html.H4(
                            f"Top {top_n} Most Wasteful Zones",
                            style={"color": colors["dark"], "marginBottom": "15px"},
                        ),
                        html.P("Missing required IAT or HSP data for calculation."),
                    ]
                )
                wasteful_zones_plot_div = html.Div("No data available for plot")

        except Exception as e_waste:
            print(f"Error calculating wasteful zones: {e_waste}")
            wasteful_zones_table_div = html.Div(
                [
                    html.H4(
                        f"Top {top_n} Most Wasteful Zones",
                        style={"color": colors["dark"], "marginBottom": "15px"},
                    ),
                    html.P(f"Error during calculation: {e_waste}"),
                ]
            )
            wasteful_zones_plot_div = html.Div(f"Error generating plot: {e_waste}")

        # Most Demanding Zones (Total Cooling)
        try:
            total_cooling_per_zone = df_cooling_zonal.sum(axis=0)  # Sum over time
            top_demanding = total_cooling_per_zone.nlargest(top_n).reset_index()
            top_demanding.columns = ["Zone", "Total Cooling"]

            # Add percentage column relative to overall total cooling
            overall_total_cooling = total_cooling_per_zone.sum()
            if overall_total_cooling > 0:
                top_demanding["% of Building Total"] = (
                    top_demanding["Total Cooling"] / overall_total_cooling * 100
                ).round(1)
            else:
                top_demanding["% of Building Total"] = 0.0

            # Create table as before
            demanding_table = dash_table.DataTable(
                data=top_demanding.to_dict("records"),
                columns=[
                    {"name": "Zone", "id": "Zone"},
                    {
                        "name": "Total Cooling",
                        "id": "Total Cooling",
                        "type": "numeric",
                        "format": {"specifier": ",.1f"},
                    },
                    {
                        "name": "% of Building Total",
                        "id": "% of Building Total",
                        "type": "numeric",
                        "format": {"specifier": ".1f", "locale": {"symbol": ["%", ""]}},
                    },
                ],
                style_cell={
                    "textAlign": "left",
                    "padding": "10px",
                    "fontFamily": "Arial, sans-serif",
                },
                style_header={
                    "backgroundColor": colors["light"],
                    "fontWeight": "bold",
                    "textAlign": "left",
                    "border": f'1px solid {colors["border"]}',
                },
                style_data_conditional=[
                    {
                        "if": {"row_index": i},
                        "backgroundColor": "#3498db20",  # Light blue with transparency
                        "borderLeft": "4px solid #3498db",
                    }
                    for i in range(len(top_demanding))
                ],
                page_size=top_n,
            )

            # Create table div
            demanding_zones_table_div = html.Div(
                [
                    html.H4(
                        f"Top {top_n} Most Demanding Zones (Total Cooling)",
                        style={"color": colors["dark"], "marginBottom": "15px"},
                    ),
                    demanding_table,
                ]
            )

            # Create plot
            demanding_zones_plot = create_demanding_zones_bar_plot(top_demanding)
            demanding_zones_plot_div = dcc.Graph(figure=demanding_zones_plot)

        except Exception as e_demand:
            print(f"Error calculating demanding zones: {e_demand}")
            demanding_zones_table_div = html.Div(
                [
                    html.H4(
                        f"Top {top_n} Most Demanding Zones",
                        style={"color": colors["dark"], "marginBottom": "15px"},
                    ),
                    html.P(f"Error during calculation: {e_demand}"),
                ]
            )
            demanding_zones_plot_div = html.Div(f"Error generating plot: {e_demand}")

        # Update the final return statement to include the new plot components
        return [
            html.Div("✅ Analysis complete!", style={"color": colors["secondary"]}),
            fig_bins_abs,
            fig_bins_frac,
            fig_regr_abs,
            fig_regr_frac,
            category_explanations,
            wasteful_zones_table_div,
            demanding_zones_table_div,
            wasteful_zones_plot_div,
            demanding_zones_plot_div,
        ]

    except Exception as e:
        # Catch-all for unexpected errors during analysis
        print(f"An unexpected error occurred: {e}")  # Log to console
        import traceback

        traceback.print_exc()  # Print full traceback for debugging

        error_fig = go.Figure()
        error_fig.update_layout(
            plot_bgcolor=colors["light"],
            paper_bgcolor=colors["light"],
            annotations=[
                dict(
                    text=f"Analysis Error: {e}",
                    showarrow=False,
                    font=dict(size=16, color=colors["accent"]),
                    xref="paper",
                    yref="paper",
                    x=0.5,
                    y=0.5,
                )
            ],
        )
        return (
            [
                html.Div(f"⚠️ Analysis Error: {e}", style={"color": colors["accent"]}),
            ]
            + [error_fig] * 4
            + [None] * 5  # None for all tables and plots
        )


# Add extra CSS styling to improve appearance
app.index_string = """
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css">
        <style>
            /* Additional custom CSS */
            body {
                margin: 0;
                padding: 0;
                font-family: Arial, sans-serif;
            }
            
            .upload-container {
                margin-bottom: 15px;
                padding: 15px;
                border-radius: 5px;
                background-color: white;
                transition: all 0.3s ease;
            }
            
            .upload-container:hover {
                box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            }
            
            .upload-label {
                font-weight: bold;
                display: block;
                margin-bottom: 8px;
                color: #2c3e50;
            }
            
            /* Make dropdowns more attractive */
            .Select-control {
                border-radius: 4px !important;
                border: 1px solid #bdc3c7 !important;
            }
            
            .Select-control:hover {
                border-color: #3498db !important;
            }
            
            /* Button hover effects */
            button:hover {
                opacity: 0.9;
                transform: translateY(-1px);
                box-shadow: 0 4px 8px rgba(0,0,0,0.15);
            }
            
            /* Animated loading indicator */
            ._dash-loading {
                margin: auto;
                color: #3498db;
                font-size: 30px;
            }
            
            /* Responsive adjustments */
            @media (max-width: 768px) {
                .upload-container {
                    padding: 10px;
                }
                
                [style*="display: grid"] {
                    grid-template-columns: 1fr !important;
                }
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
"""

# ---------------------------------------------------------------------------- #
#                                Run the App                                   #
# ---------------------------------------------------------------------------- #
if __name__ == "__main__":
    app.run_server(debug=True)  # Turn off debug=True for production
