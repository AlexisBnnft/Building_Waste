from dash import Input, Output, State, callback, html, dash_table, dcc
import pandas as pd
import plotly.graph_objects as go
import dash
import sys
import traceback

from core.analysis import (
    get_cooling_zonal_from_data,
    categorize_cooling_by_iat_bins_from_data,
)
from core.visualization import (
    create_stacked_area_plot,
    create_regrouped_stacked_area_plot,
    create_wasteful_zones_bar_plot,
    create_demanding_zones_bar_plot,
)
from utils.constants import COLORS
from utils.file_utils import parse_content
from layouts.main_layout import create_results_layout


@callback(
    [
        Output("status-output", "children"),
        Output("upload-analysis-results", "children"),
        Output("upload-analysis-results", "style"),
        Output("upload-form-container", "style"),
    ],
    [Input("process-data-button", "n_clicks")],
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

    default_results_style = {
        "width": "60%",
        "display": "inline-block",
        "verticalAlign": "top",
        "padding": "20px",
    }

    default_form_style = {
        "width": "40%",
        "display": "inline-block",
        "verticalAlign": "top",
        "padding": "20px",
    }

    if n_clicks == 0:
        # Initial load, return empty figures and default messages
        return (
            html.Div("Waiting for data upload...", style={"color": COLORS["primary"]}),
            html.Div(),
            default_results_style,
            default_form_style,
        )

    ctx = dash.callback_context
    if (
        not ctx.triggered
        or ctx.triggered[0]["prop_id"] != "process-data-button.n_clicks"
    ):
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
        return (
            html.Div(
                "⚠️ Error: Please check uploaded files and formats.",
                style={"color": COLORS["accent"]},
            ),
            html.Div(),
            default_results_style,
            default_form_style,
        )

    # --- 2. Run Analysis ---
    try:
        status_output = html.Div(
            "✅ Analysis completed successfully!",
            style={"color": COLORS["primary"]},
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
            return (
                html.Div(f"⚠️ {error_msg}", style={"color": COLORS["accent"]}),
                html.Div(),
                default_results_style,
                default_form_style,
            )

        # Categorize by IAT bins
        df_iat_binned = categorize_cooling_by_iat_bins_from_data(
            project_name,
            data_dict["iat"],
            data_dict["hsp"],
            data_dict["csp"],
            df_cooling_zonal,
        )

        if df_iat_binned is None or df_iat_binned.empty:
            error_msg = "Error during IAT binning analysis. Check data consistency."
            return (
                html.Div(f"⚠️ {error_msg}", style={"color": COLORS["accent"]}),
                html.Div(),
                default_results_style,
                default_form_style,
            )

        # Apply resampling based on user selection or default to weekly
        if not resample_freq:
            resample_freq = "W"  # Default to weekly if no selection

        # Get a human-readable frequency name for plot titles
        freq_name = {"H": "Hourly", "D": "Daily", "W": "Weekly", "M": "Monthly"}.get(
            resample_freq, resample_freq
        )

        try:
            # Apply resampling
            df_iat_binned = df_iat_binned.resample(resample_freq).sum()
        except Exception as e:
            print(f"Warning: Resampling error: {e}. Using original frequency.")

        # --- 3. Create Visualizations ---
        # Create a results layout with our charts
        results_layout = create_results_layout()

        # Look for wasteful column
        wasteful_col = None
        for col in df_iat_binned.columns:
            if "bin1" in col.lower() or "iat<hsp" in col.lower():
                wasteful_col = col
                break

        # 1. Stacked area plot - absolute values
        fig_bins_absolute = create_stacked_area_plot(
            df_iat_binned,
            f"Cooling Energy by {freq_name} (Absolute)",
            "MMBtu",
            normalize=False,
        )

        # 2. Stacked area plot - normalized values
        fig_bins_fractional = create_stacked_area_plot(
            df_iat_binned,
            f"Cooling Energy by {freq_name} (Fractional)",
            "%",
            normalize=True,
        )

        # 3. Regrouped stacked area - absolute values
        fig_regrouped_absolute = create_regrouped_stacked_area_plot(
            df_iat_binned,
            f"Regrouped Cooling Energy by {freq_name} (Absolute)",
            "MMBtu",
            normalize=False,
        )

        # 4. Regrouped stacked area - normalized values
        fig_regrouped_fractional = create_regrouped_stacked_area_plot(
            df_iat_binned,
            f"Regrouped Cooling Energy by {freq_name} (Fractional)",
            "%",
            normalize=True,
        )

        # --- 4. Create Analysis Summary ---

        # Calculate total cooling and breakdown by category
        cooling_total = df_iat_binned.sum().sum()

        # Make sure we can access the columns
        useful_cols = []
        for col in df_iat_binned.columns:
            if (
                "bin4" in col.lower()
                or "bin5" in col.lower()
                or "bin6" in col.lower()
                or "iat>csp" in col.lower()
            ):
                useful_cols.append(col)

        excess_cols = []
        for col in df_iat_binned.columns:
            if (
                "bin2" in col.lower()
                or "bin3" in col.lower()
                or "0-25" in col.lower()
                or "25-50" in col.lower()
            ):
                excess_cols.append(col)

        # Calculate sums based on available columns
        demand = df_iat_binned[useful_cols].sum().sum() if useful_cols else 0
        excess = df_iat_binned[excess_cols].sum().sum() if excess_cols else 0
        wasteful = df_iat_binned[wasteful_col].sum() if wasteful_col else 0

        # Create a summary table
        summary_table = html.Div(
            [
                html.H3(
                    "Analysis Summary",
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
            ]
        )

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

        # Update the tables
        results_layout.children[1].children[2].children[0].children = summary_table

        # Prepare data for wasteful zones plot
        # Align IAT and HSP dataframes with cooling_zonal
        common_index = df_cooling_zonal.index
        common_cols = df_cooling_zonal.columns

        aligned_iat = data_dict["iat"].reindex(index=common_index, columns=common_cols)
        aligned_hsp = data_dict["hsp"].reindex(index=common_index, columns=common_cols)

        # Now compare aligned dataframes
        bin1_mask = aligned_iat < aligned_hsp
        wasteful_cooling = df_cooling_zonal.where(bin1_mask, 0)
        total_wasteful_per_zone = wasteful_cooling.sum(axis=0)  # Sum over time

        # Get top 10 wasteful zones or less if fewer exist
        num_zones = min(10, len(total_wasteful_per_zone))
        top_wasteful = total_wasteful_per_zone.nlargest(num_zones).reset_index()

        if not top_wasteful.empty:
            top_wasteful.columns = ["Zone", "Wasteful Cooling (Bin 1)"]

            # Add percentage column if we have bin1 data
            total_bin1_cooling = (
                df_iat_binned[wasteful_col].sum() if wasteful_col else 0
            )
            if total_bin1_cooling > 0:
                top_wasteful["% of Total Waste"] = (
                    top_wasteful["Wasteful Cooling (Bin 1)"] / total_bin1_cooling * 100
                ).round(1)
            else:
                top_wasteful["% of Total Waste"] = 0.0

            # Wasteful zones plot
            wasteful_zones_plot = create_wasteful_zones_bar_plot(top_wasteful)
        else:
            # Create an empty plot if no data
            wasteful_zones_plot = go.Figure()
            wasteful_zones_plot.update_layout(title="No wasteful zones found")

        # Prepare data for demanding zones plot
        total_cooling_per_zone = df_cooling_zonal.sum(axis=0)  # Sum over time

        # Get top 10 demanding zones or less if fewer exist
        num_zones = min(10, len(total_cooling_per_zone))
        top_demanding = total_cooling_per_zone.nlargest(num_zones).reset_index()

        if not top_demanding.empty:
            top_demanding.columns = ["Zone", "Total Cooling"]

            # Add percentage column
            total_cooling = total_cooling_per_zone.sum()
            if total_cooling > 0:
                top_demanding["% of Building Total"] = (
                    top_demanding["Total Cooling"] / total_cooling * 100
                ).round(1)
            else:
                top_demanding["% of Building Total"] = 0.0

            # Demanding zones plot
            demanding_zones_plot = create_demanding_zones_bar_plot(top_demanding)
        else:
            # Create an empty plot if no data
            demanding_zones_plot = go.Figure()
            demanding_zones_plot.update_layout(title="No demanding zones found")

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

        # After analysis is complete, use more width for results and less for inputs
        expanded_results_style = {
            "width": "100%",
            "display": "block",
            "verticalAlign": "top",
            "padding": "20px",
            "marginTop": "20px",
        }

        collapsed_form_style = {
            "width": "100%",
            "display": "block",
            "verticalAlign": "top",
            "padding": "20px",
            "maxHeight": "250px",
            "overflowY": "scroll",
            "border": f"1px solid {COLORS['border']}",
            "borderRadius": "5px",
            "backgroundColor": COLORS["light"],
        }

        return (
            status_output,
            results_layout,
            expanded_results_style,
            collapsed_form_style,
        )

    except Exception as e:
        error_msg = f"Error during analysis: {str(e)}"
        return (
            html.Div(f"⚠️ {error_msg}", style={"color": COLORS["accent"]}),
            html.Div(),
            default_results_style,
            default_form_style,
        )
