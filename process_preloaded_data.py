import pandas as pd
import os
import pickle
import shutil

from core.analysis import (
    get_cooling_zonal_from_data,
    categorize_cooling_by_iat_bins_from_data,
)


def process_building_data(building_name, data_dir):
    """
    Process the data for a single building
    """
    print(f"Processing data for building: {building_name}")

    # Define paths to test data files
    iat_path = os.path.join(data_dir, "zone_temps.csv")
    hsp_path = os.path.join(data_dir, "zone_heating_setpoints.csv")
    csp_path = os.path.join(data_dir, "zone_cooling_setpoints.csv")
    airflow_path = os.path.join(data_dir, "zone_airflow.csv")
    ahu_dat_path = os.path.join(data_dir, "ahu_discharge_temps.csv")
    map_path = os.path.join(data_dir, "zone_to_ahu_map.csv")
    cooling_path = os.path.join(data_dir, "building_total_cooling.csv")

    # Check if all files exist
    required_files = [
        iat_path,
        hsp_path,
        csp_path,
        airflow_path,
        ahu_dat_path,
        map_path,
        cooling_path,
    ]
    for file_path in required_files:
        if not os.path.exists(file_path):
            print(
                f"Error: Required file {file_path} not found for building {building_name}"
            )
            return None

    # Load dataframes
    data_dict = {}
    data_dict["iat"] = pd.read_csv(iat_path, index_col=0, parse_dates=True)
    data_dict["hsp"] = pd.read_csv(hsp_path, index_col=0, parse_dates=True)
    data_dict["csp"] = pd.read_csv(csp_path, index_col=0, parse_dates=True)
    data_dict["airflow"] = pd.read_csv(airflow_path, index_col=0, parse_dates=True)
    data_dict["ahu_dat"] = pd.read_csv(ahu_dat_path, index_col=0, parse_dates=True)
    data_dict["map"] = pd.read_csv(map_path)
    data_dict["cooling"] = pd.read_csv(cooling_path, index_col=0, parse_dates=True)

    # Filter out VAVs with median temperatures outside valid range
    iat_medians = data_dict["iat"].median()
    valid_zones = iat_medians[(iat_medians >= 30) & (iat_medians <= 200)].index

    invalid_zones = set(data_dict["iat"].columns) - set(valid_zones)
    if invalid_zones:
        print(
            f"Removing {len(invalid_zones)} zones with invalid median temperatures: {', '.join(invalid_zones)}"
        )

    # Filter all dataframes to include only valid zones
    for df_name in ["iat", "hsp", "csp", "airflow"]:
        # Filter columns to only include valid zones
        data_dict[df_name] = data_dict[df_name].filter(items=valid_zones, axis=1)

    # Print map dataframe columns to identify the correct column name
    print(f"Map dataframe columns: {data_dict['map'].columns.tolist()}")

    # Get the first column name assuming it contains zone names
    zone_column = data_dict["map"].columns[0]
    print(f"Using column '{zone_column}' for zone filtering")

    # Update the zone mapping to include only valid zones
    data_dict["map"] = data_dict["map"][data_dict["map"][zone_column].isin(valid_zones)]

    # Extract the single column Series for total cooling
    cooling_series = data_dict["cooling"].iloc[:, 0]

    # Calculate zonal cooling
    df_cooling_zonal = get_cooling_zonal_from_data(
        building_name,
        data_dict["ahu_dat"],
        data_dict["iat"],
        data_dict["airflow"],
        data_dict["map"],
        cooling_series,
    )

    if df_cooling_zonal is None or df_cooling_zonal.empty:
        print(f"Error: Zonal cooling calculation returned no data for {building_name}.")
        return None

    # Categorize by IAT bins
    df_iat_binned = categorize_cooling_by_iat_bins_from_data(
        building_name,
        data_dict["iat"],
        data_dict["hsp"],
        data_dict["csp"],
        df_cooling_zonal,
    )

    if df_iat_binned is None or df_iat_binned.empty:
        print(f"Error: IAT binning returned no data for {building_name}.")
        return None

    # Resample to weekly frequency for better visualization
    weekly_df_iat_binned = df_iat_binned.resample("W").sum()

    # Calculate top wasteful zones
    common_index = df_cooling_zonal.index
    common_cols = df_cooling_zonal.columns

    aligned_iat = data_dict["iat"].reindex(index=common_index, columns=common_cols)
    aligned_hsp = data_dict["hsp"].reindex(index=common_index, columns=common_cols)

    bin1_mask = aligned_iat < aligned_hsp
    wasteful_cooling = df_cooling_zonal.where(bin1_mask, 0)
    total_wasteful_per_zone = wasteful_cooling.sum(axis=0)  # Sum over time
    num_zones = min(10, len(total_wasteful_per_zone))
    top_wasteful = total_wasteful_per_zone.nlargest(num_zones).reset_index()

    if not top_wasteful.empty:
        top_wasteful.columns = ["Zone", "Wasteful Cooling (Bin 1)"]
        wasteful_col = (
            "bin1_IAT<HSP" if "bin1_IAT<HSP" in weekly_df_iat_binned.columns else None
        )
        total_bin1_cooling = (
            weekly_df_iat_binned[wasteful_col].sum() if wasteful_col else 0
        )

        if total_bin1_cooling > 0:
            top_wasteful["% of Total Waste"] = (
                top_wasteful["Wasteful Cooling (Bin 1)"] / total_bin1_cooling * 100
            ).round(1)
        else:
            top_wasteful["% of Total Waste"] = 0.0

    # Calculate top demanding zones
    total_cooling_per_zone = df_cooling_zonal.sum(axis=0)  # Sum over time
    num_zones = min(10, len(total_cooling_per_zone))
    top_demanding = total_cooling_per_zone.nlargest(num_zones).reset_index()

    if not top_demanding.empty:
        top_demanding.columns = ["Zone", "Total Cooling"]
        total_cooling = total_cooling_per_zone.sum()

        if total_cooling > 0:
            top_demanding["% of Building Total"] = (
                top_demanding["Total Cooling"] / total_cooling * 100
            ).round(1)
        else:
            top_demanding["% of Building Total"] = 0.0

    # Create processed_data dictionary with all the results
    processed_data = {
        "df_cooling_zonal": df_cooling_zonal,
        "df_iat_binned": df_iat_binned,
        "weekly_df_iat_binned": weekly_df_iat_binned,
        "top_wasteful": top_wasteful,
        "top_demanding": top_demanding,
    }

    # Include the raw zone data for detailed zone plots
    # Store the filtered and aligned dataframes
    processed_data["iat"] = data_dict["iat"]
    processed_data["hsp"] = data_dict["hsp"]
    processed_data["csp"] = data_dict["csp"]
    processed_data["airflow"] = data_dict["airflow"]

    return processed_data


def process_and_save_test_data():
    """
    Process the test data files for all buildings and save the results for quick loading
    """
    print("Processing test data for multiple buildings...")

    # Define root data directory
    root_data_dir = "test_app_data"

    # Setup default single building case
    # If there are no subdirectories, treat the main folder as a single building called "Default Building"
    buildings = []

    # Check if test_app_data directory exists
    if not os.path.exists(root_data_dir):
        print(f"Error: {root_data_dir} directory not found.")
        return

    # Look for building subdirectories or use the root directory for a single building
    if all(
        not os.path.isdir(os.path.join(root_data_dir, item))
        for item in os.listdir(root_data_dir)
        if not item.startswith(".")
    ):
        # No subdirectories - single building case
        print("No building subdirectories found. Processing as a single building.")
        buildings = [("Default Building", root_data_dir)]
    else:
        # Multiple building case - look for subdirectories
        for item in os.listdir(root_data_dir):
            building_dir = os.path.join(root_data_dir, item)
            if os.path.isdir(building_dir) and not item.startswith("."):
                buildings.append((item, building_dir))

    if not buildings:
        print("No buildings to process. Please check your data structure.")
        return

    # Process each building and store results
    output_dir = "processed_data"
    os.makedirs(output_dir, exist_ok=True)

    buildings_data = {}

    for building_name, building_dir in buildings:
        print(f"\nProcessing building: {building_name}")
        building_data = process_building_data(building_name, building_dir)

        if building_data:
            buildings_data[building_name] = building_data
            print(f"Successfully processed data for {building_name}")
        else:
            print(f"Failed to process data for {building_name}")

    if not buildings_data:
        print("No building data was successfully processed.")
        return

    # Save the processed data to pickle file
    output_path = os.path.join(output_dir, "preloaded_analysis.pkl")

    print(
        f"\nSaving processed data for {len(buildings_data)} buildings to {output_path}..."
    )
    with open(output_path, "wb") as f:
        pickle.dump(buildings_data, f)

    # Save the list of building names for easy access
    building_names = list(buildings_data.keys())
    buildings_info_path = os.path.join(output_dir, "buildings_info.pkl")
    with open(buildings_info_path, "wb") as f:
        pickle.dump({"names": building_names}, f)

    print("Processing completed successfully.")

    # Generate sample multi-building structure if needed (for demonstration)
    if len(buildings) == 1 and buildings[0][0] == "Default Building":
        print("\nWould you like to create a sample multi-building structure? (y/n)")
        choice = input().strip().lower()
        if choice == "y":
            create_sample_building_structure()


def create_sample_building_structure():
    """
    Creates a sample multi-building structure by duplicating existing data
    for demonstration purposes.
    """
    print("Creating sample building structure...")
    source_dir = "test_app_data"

    # Check if source data exists
    if not os.path.exists(source_dir):
        print(f"Error: {source_dir} directory not found.")
        return

    # Sample building names
    building_names = [
        "Building A",
        "Building B",
        "Building C",
        "Building D",
        "Building E",
        "Building F",
    ]

    # Create a backup of the original data
    backup_dir = "test_app_data_backup"
    if not os.path.exists(backup_dir):
        print(f"Creating backup of original data to {backup_dir}")
        shutil.copytree(source_dir, backup_dir)

    # Create building directories and copy files
    for building_name in building_names:
        building_dir = os.path.join(source_dir, building_name.replace(" ", "_"))
        os.makedirs(building_dir, exist_ok=True)

        # Copy files from source to building directory
        for filename in os.listdir(backup_dir):
            file_path = os.path.join(backup_dir, filename)
            if os.path.isfile(file_path):
                shutil.copy2(file_path, building_dir)

        print(f"Created {building_name} directory with sample data")

    # Remove files from root directory to avoid confusion
    for filename in os.listdir(source_dir):
        file_path = os.path.join(source_dir, filename)
        if os.path.isfile(file_path):
            os.remove(file_path)

    print("Sample building structure created successfully.")
    print("Please run the script again to process the multi-building data.")


if __name__ == "__main__":
    process_and_save_test_data()
