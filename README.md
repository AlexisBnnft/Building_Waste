# Building Cooling Analysis Dashboard

A web application for visualizing and analyzing building cooling energy data.

## Setup

1. Install the required packages:
   ```
   pip install -r requirements.txt
   ```

2. Process the pre-loaded analysis data (one-time setup):
   ```
   bash preprocess_data.sh
   ```
   Or manually run:
   ```
   python process_preloaded_data.py
   ```
   This processes the data from the `test_app_data` folder and creates cached analysis results for faster loading.

## Running the Application

Start the application with:
```
python app.py
```

Open your browser and go to http://127.0.0.1:8050/ to access the dashboard.

## Features

The application has two main tabs:

1. **Pre-loaded Analysis**: Shows pre-processed analysis from test data, loading instantly without any processing delay.

2. **Custom Analysis**: Allows uploading your own data files for custom analysis.

## Data Format

The application accepts the following CSV file formats:

- Zone Temperatures
- Zone Heating Setpoints
- Zone Cooling Setpoints
- Zone Airflow
- AHU Discharge Temperatures
- Zone to AHU Map
- Building Total Cooling

Sample data files are provided in the `test_app_data` folder for reference. 