import plotly.graph_objects as go
import plotly.express as px
import pandas as pd


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
