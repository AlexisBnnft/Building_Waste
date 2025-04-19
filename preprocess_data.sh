#!/bin/bash

echo "Installing required Python packages..."
pip install dash dash-table plotly pandas numpy

echo "Running pre-processing script..."
python process_preloaded_data.py

echo "Done. You can now run the app with: python app.py" 