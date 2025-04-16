import base64
import io
import pandas as pd
from dash import html

from utils.constants import COLORS


def parse_content(contents, filename):
    """Helper function to parse uploaded CSV."""
    if contents is None:
        return None, html.Div(
            ["❌ No file uploaded."],
            style={"color": COLORS["accent"], "fontWeight": "bold"},
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
                        "backgroundColor": COLORS["secondary"]
                        + "30",  # Light green with transparency
                        "color": COLORS["secondary"],
                        "fontWeight": "bold",
                        "padding": "8px 12px",
                        "borderRadius": "4px",
                        "border": f"1px solid {COLORS['secondary']}",
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
                            "backgroundColor": COLORS["accent"]
                            + "20",  # Light red with transparency
                            "color": COLORS["accent"],
                            "fontWeight": "bold",
                            "padding": "8px 12px",
                            "borderRadius": "4px",
                            "border": f"1px solid {COLORS['accent']}",
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
                    "backgroundColor": COLORS["accent"] + "20",
                    "color": COLORS["accent"],
                    "fontWeight": "bold",
                    "padding": "8px 12px",
                    "borderRadius": "4px",
                    "border": f"1px solid {COLORS['accent']}",
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
                "backgroundColor": COLORS["accent"] + "20",
                "color": COLORS["accent"],
                "fontWeight": "bold",
                "padding": "8px 12px",
                "borderRadius": "4px",
                "border": f"1px solid {COLORS['accent']}",
                "display": "inline-block",
                "marginTop": "5px",
            },
        )
