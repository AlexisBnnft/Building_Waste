import dash
from dash import dcc, html, dash_table
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

from layouts.main_layout import create_app_layout
from utils.constants import COLORS

# Initialize the Dash app
app = dash.Dash(
    __name__,
    suppress_callback_exceptions=True,
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)
app.title = "Building Cooling Analysis"

# Create the server variable for Gunicorn
server = app.server

# Make app callable for Gunicorn
application = app.server

# Create the app layout
app.layout = create_app_layout()

# Import callbacks - this needs to be done after app is defined
# to avoid circular imports
from callbacks.upload_callbacks import *
from callbacks.analysis_callbacks import *
from callbacks.preloaded_callbacks import *

# Custom CSS for better styling
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
            
            /* Custom styling for tabs */
            .custom-tabs {
                border-bottom: 1px solid #d6d6d6;
            }
            
            .custom-tab {
                padding: 15px 20px;
                color: #586069;
                border-top-left-radius: 3px;
                border-top-right-radius: 3px;
                border-bottom: 0px;
                transition: all 0.3s ease;
            }
            
            .custom-tab--selected {
                color: #2c3e50;
                background-color: white;
                border-left: 1px solid #d6d6d6;
                border-right: 1px solid #d6d6d6;
                border-top: 3px solid #3498db;
                border-bottom: none;
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

# Run the app
if __name__ == "__main__":
    app.run_server(debug=True)  # Turn off debug=True for production
