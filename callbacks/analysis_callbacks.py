from dash import Input, Output, State, callback, html, dash_table, dcc
import plotly.graph_objects as go
import pandas as pd
import dash

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


@callback(
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
            plot_bgcolor=COLORS["light"],
            paper_bgcolor=COLORS["light"],
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
                    font=dict(size=16, color=COLORS["dark"]),
                    xref="paper",
                    yref="paper",
                    x=0.5,
                    y=0.5,
                )
            ],
        )
        return (
            ["Waiting for data upload..."] + [empty_fig] * 4 + [None] * 5
        )  # 5 None values for tables and plots

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
            plot_bgcolor=COLORS["light"],
            paper_bgcolor=COLORS["light"],
            annotations=[
                dict(
                    text="Error in uploaded files. Check formats and try again.",
                    showarrow=False,
                    font=dict(size=16, color=COLORS["accent"]),
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
                    style={"color": COLORS["accent"]},
                ),
            ]
            + [error_fig] * 4
            + [None] * 5  # None for all tables and plots
        )

    # --- 2. Run Analysis ---
    try:
        status_output = html.Div(
            "⏳ Processing... Calculating zone cooling allocation.",
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
            error_fig = go.Figure()
            error_fig.update_layout(
                plot_bgcolor=COLORS["light"],
                paper_bgcolor=COLORS["light"],
                annotations=[
                    dict(
                        text=error_msg,
                        showarrow=False,
                        font=dict(size=16, color=COLORS["accent"]),
                        xref="paper",
                        yref="paper",
                        x=0.5,
                        y=0.5,
                    )
                ],
            )
            return (
                [
                    html.Div(f"⚠️ {error_msg}", style={"color": COLORS["accent"]}),
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
            style={"color": COLORS["primary"]},
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
                plot_bgcolor=COLORS["light"],
                paper_bgcolor=COLORS["light"],
                annotations=[
                    dict(
                        text=error_msg,
                        showarrow=False,
                        font=dict(size=16, color=COLORS["accent"]),
                        xref="paper",
                        yref="paper",
                        x=0.5,
                        y=0.5,
                    )
                ],
            )
            return (
                [
                    html.Div(f"⚠️ {error_msg}", style={"color": COLORS["accent"]}),
                ]
                + [error_fig] * 4
                + [None] * 5  # None for all tables and plots
            )

        status_output = html.Div(
            "⏳ Processing... Generating plots.", style={"color": COLORS["primary"]}
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
                style={"color": COLORS["accent"]},
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
                "backgroundColor": COLORS["light"],
                "fontWeight": "bold",
                "textAlign": "left",
                "border": f'1px solid {COLORS["border"]}',
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
                    style={"marginBottom": "15px", "color": COLORS["dark"]},
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

        # Analyze wasteful and demanding zones
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

                # Create table
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
                        "backgroundColor": COLORS["light"],
                        "fontWeight": "bold",
                        "textAlign": "left",
                        "border": f'1px solid {COLORS["border"]}',
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
                            style={"color": COLORS["dark"], "marginBottom": "15px"},
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
                            style={"color": COLORS["dark"], "marginBottom": "15px"},
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
                        style={"color": COLORS["dark"], "marginBottom": "15px"},
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

            # Create table
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
                    "backgroundColor": COLORS["light"],
                    "fontWeight": "bold",
                    "textAlign": "left",
                    "border": f'1px solid {COLORS["border"]}',
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
                        style={"color": COLORS["dark"], "marginBottom": "15px"},
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
                        style={"color": COLORS["dark"], "marginBottom": "15px"},
                    ),
                    html.P(f"Error during calculation: {e_demand}"),
                ]
            )
            demanding_zones_plot_div = html.Div(f"Error generating plot: {e_demand}")

        return [
            html.Div("✅ Analysis complete!", style={"color": COLORS["secondary"]}),
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
            plot_bgcolor=COLORS["light"],
            paper_bgcolor=COLORS["light"],
            annotations=[
                dict(
                    text=f"Analysis Error: {e}",
                    showarrow=False,
                    font=dict(size=16, color=COLORS["accent"]),
                    xref="paper",
                    yref="paper",
                    x=0.5,
                    y=0.5,
                )
            ],
        )
        return (
            [
                html.Div(f"⚠️ Analysis Error: {e}", style={"color": COLORS["accent"]}),
            ]
            + [error_fig] * 4
            + [None] * 5  # None for all tables and plots
        )
