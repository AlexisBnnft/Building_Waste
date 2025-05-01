# Application color scheme
COLORS = {
    "background": "#f9f9f9",
    "text": "#2c3e50",
    "primary": "#3498db",
    "secondary": "#2ecc71",
    "accent": "#e74c3c",
    "light": "#ecf0f1",
    "dark": "#34495e",
    "border": "#bdc3c7",
    # Add color categories for zone types
    "wasteful": "#e74c3c",  # Red - for wasteful cooling (bin1)
    "excess": "#f39c12",  # Orange - for excess cooling (bin2-3)
    "useful": "#27ae60",  # Green - for useful cooling (bin4-6)
    "demanding": "#3498db",  # Blue - for demanding zones
}

# File descriptions for upload instructions
FILE_DESCRIPTIONS = {
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

# Bin labels and descriptions
BIN_INFO = {
    "bin1_IAT<HSP": {
        "label": "Wasted",
        "description": "Temperature below heating setpoint (IAT < HSP)",
        "color": "#e74c3c",  # Red
    },
    "bin2_0-25%": {
        "label": "Excess",
        "description": "Temperature in lower half of deadband (part 1)",
        "color": "#f39c12",  # Orange
    },
    "bin3_25-50%": {
        "label": "Excess",
        "description": "Temperature in lower half of deadband (part 2)",
        "color": "#f1c40f",  # Yellow
    },
    "bin4_50-75%": {
        "label": "Useful",
        "description": "Temperature in upper half of deadband (part 1)",
        "color": "#2ecc71",  # Light green
    },
    "bin5_75-100%": {
        "label": "Useful",
        "description": "Temperature in upper half of deadband (part 2)",
        "color": "#27ae60",  # Green
    },
    "bin6_IAT>CSP": {
        "label": "Useful",
        "description": "Temperature above cooling setpoint (IAT > CSP)",
        "color": "#16a085",  # Teal
    },
}
