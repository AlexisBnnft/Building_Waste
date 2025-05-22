import pandas as pd
import os
import pickle
import shutil
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
import io
import glob  # NEW: For finding Excel files
import numpy as np  # NEW: For NaN and other numerical operations
from datetime import time  # NEW: For time-based filtering in airflow calculation
import traceback  # NEW: For detailed error printing

# Load environment variables from .env file if it exists
load_dotenv()

from core.analysis import (
    get_cooling_zonal_from_data,
    categorize_cooling_by_iat_bins_from_data,
)

# --- Additional Configuration for Analysis ---
ZONEMAP_FILE = "zonemap.csv"  # Assumed to be in the root directory
EXCEL_FILES_PATTERN = "*.xlsx"  # Assumed to be in the root directory
EXCEL_HEADER_ROW = 1  # Assumes actual headers are on the *second* row (0-indexed)

# Define column names for clarity (these MUST match your actual file headers)
EXCEL_ROOM_COL = "Room"
EXCEL_SQFT_COL = "Sqr Feet"

ZONEMAP_BUILDING_COL = "Building"
ZONEMAP_VAV_COL = "VAV"
ZONEMAP_ROOM_COL = "Room"

ASHRAE_CFM_PER_SQFT = 0.15  # ASHRAE Guideline


# --- Helper Function to Clean Room Numbers ---
def clean_room_number(room_val):
    """Cleans room number strings."""
    if pd.isna(room_val):
        return np.nan
    room_str = str(room_val).strip()
    if room_str.lower().startswith("room "):
        room_str = room_str[5:].strip()
    if room_str.endswith(","):
        room_str = room_str[:-1].strip()
    return room_str


def get_s3_client():
    """
    Creates and returns an S3 client using environment variables
    """
    # Get S3 credentials from environment variables
    aws_access_key = os.environ.get("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
    s3_region = os.environ.get(
        "S3_REGION", "us-east-1"
    )  # Default to us-east-1 if not specified

    # Create and return S3 client
    s3_client = boto3.client(
        "s3",
        region_name=s3_region,
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
    )
    return s3_client


def upload_to_s3(data, s3_path, bucket_name=None):
    """
    Uploads data to S3 bucket

    Args:
        data: Data to upload (will be pickled)
        s3_path: Path in S3 where the data should be stored
        bucket_name: S3 bucket name, defaults to environment variable

    Returns:
        Boolean indicating success or failure
    """
    try:
        # Get bucket name from environment variables if not provided
        if bucket_name is None:
            bucket_name = os.environ.get("S3_BUCKET_NAME")

        if not bucket_name:
            print("Error: S3_BUCKET_NAME environment variable not set")
            return False

        # Create S3 client
        s3_client = get_s3_client()

        # Pickle the data to a bytes object
        pickle_buffer = io.BytesIO()
        pickle.dump(data, pickle_buffer)
        pickle_buffer.seek(0)  # Go to the start of the BytesIO object

        # Upload to S3
        s3_client.put_object(
            Bucket=bucket_name, Key=s3_path, Body=pickle_buffer.getvalue()
        )

        print(f"Successfully uploaded data to s3://{bucket_name}/{s3_path}")
        return True

    except ClientError as e:
        print(f"Error uploading to S3: {e}")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False


def process_building_data(building_name, data_dir, year):
    """
    Process the data for a single building, including ASHRAE guideline calculation
    and scaled airflow simulation for savings (based on IAT < HSP waste).
    Uses pre-calculated minimal airflow from min_airflow.csv.
    """
    print(f"Processing data for building: {building_name}")

    # Define paths to test data files
    iat_path = os.path.join(data_dir, "zone_temps.csv")
    hsp_path = os.path.join(
        data_dir, "zone_heating_setpoints.csv"
    )  # Required for new waste definition
    csp_path = os.path.join(data_dir, "zone_cooling_setpoints.csv")
    airflow_path = os.path.join(data_dir, "zone_airflow.csv")
    ahu_dat_path = os.path.join(data_dir, "ahu_discharge_temps.csv")
    map_path = os.path.join(data_dir, "zone_to_ahu_map.csv")
    cooling_path = os.path.join(data_dir, "building_total_cooling.csv")
    tloads_path = os.path.join(
        data_dir, "zone_tloads.csv"
    )  # Still required for min airflow period identification
    min_airflow_path = os.path.join(
        data_dir, "min_airflow.csv"
    )  # NEW REQUIRED FILE PATH

    # Check if all files exist
    required_files = [
        iat_path,
        hsp_path,
        csp_path,
        airflow_path,
        ahu_dat_path,
        map_path,
        cooling_path,
        tloads_path,
        min_airflow_path,  # NEW: Include min_airflow_path
    ]
    for file_path in required_files:
        if not os.path.exists(file_path):
            print(
                f"Error: Required file {file_path} not found for building {building_name}. Skipping analysis for this building."
            )
            return None

    # Load dataframes
    data_dict = {}
    data_dict["iat"] = pd.read_csv(iat_path, index_col=0, parse_dates=True)
    data_dict["hsp"] = pd.read_csv(hsp_path, index_col=0, parse_dates=True)  # Load HSP
    data_dict["csp"] = pd.read_csv(csp_path, index_col=0, parse_dates=True)
    data_dict["airflow"] = pd.read_csv(airflow_path, index_col=0, parse_dates=True)
    data_dict["ahu_dat"] = pd.read_csv(ahu_dat_path, index_col=0, parse_dates=True)
    data_dict["map"] = pd.read_csv(map_path)
    data_dict["cooling"] = pd.read_csv(cooling_path, index_col=0, parse_dates=True)
    data_dict["tloads"] = pd.read_csv(tloads_path, index_col=0, parse_dates=True)
    # NEW: Load min_airflow.csv. This file is expected to contain 'VAV' and 'Calculated_Min_Airflow_CFM' columns.
    # It is NOT time-series data, so don't set index_col or parse_dates.
    data_dict["min_airflow_precalculated"] = pd.read_csv(min_airflow_path, index_col=0)

    # Filter out VAVs with median temperatures outside valid range
    iat_medians = data_dict["iat"].median()
    valid_zones = iat_medians[(iat_medians >= 30) & (iat_medians <= 200)].index

    # Apply filtering to all relevant dataframes including newly loaded ones
    for df_name in ["iat", "hsp", "csp", "airflow", "tloads"]:  # Removed rhv, added hsp
        # Filter columns to only include valid zones
        data_dict[df_name] = data_dict[df_name].filter(items=valid_zones, axis=1)

    # NEW: Filter min_airflow_precalculated based on valid_zones
    if "VAV" in data_dict["min_airflow_precalculated"].columns:
        data_dict["min_airflow_precalculated"] = data_dict["min_airflow_precalculated"][
            data_dict["min_airflow_precalculated"]["VAV"]
            .astype(str)
            .str.strip()
            .isin([str(z).strip() for z in valid_zones])
        ].copy()
        # Ensure the pre-calculated min airflow column is numeric
        data_dict["min_airflow_precalculated"]["Calculated_Min_Airflow_CFM"] = (
            pd.to_numeric(
                data_dict["min_airflow_precalculated"].get(
                    "Calculated_Min_Airflow_CFM"
                ),
                errors="coerce",
            )
        )
        data_dict["min_airflow_precalculated"].dropna(
            subset=["Calculated_Min_Airflow_CFM"], inplace=True
        )
    else:
        print(
            f"Warning: 'VAV' column not found in '{min_airflow_path}'. Cannot filter or use pre-calculated min airflow."
        )
        data_dict["min_airflow_precalculated"] = pd.DataFrame(
            columns=["VAV", "Calculated_Min_Airflow_CFM"]
        )  # Ensure empty DF has expected columns

    # Print map dataframe columns to identify the correct column name
    print(f"Map dataframe columns: {data_dict['map'].columns.tolist()}")

    # Get the first column name assuming it contains zone names
    zone_column = data_dict["map"].columns[0]
    print(f"Using column '{zone_column}' for zone filtering")

    # Update the zone mapping to include only valid zones
    data_dict["map"] = data_dict["map"][data_dict["map"][zone_column].isin(valid_zones)]

    # Extract the single column Series for total cooling
    cooling_series = data_dict["cooling"].iloc[:, 0]

    # --- Start of New Analysis Integration ---

    # 1. Load and prepare zonemap and excel data for SqFt
    zone_map_df = pd.DataFrame()
    try:
        # Assumed to be in the root directory where script is run
        zone_map_df = pd.read_csv(ZONEMAP_FILE, delimiter=";", engine="c")

        # Ensure required columns exist after loading
        expected_zonemap_cols = [
            ZONEMAP_BUILDING_COL,
            ZONEMAP_VAV_COL,
            ZONEMAP_ROOM_COL,
        ]
        missing_cols = [
            col for col in expected_zonemap_cols if col not in zone_map_df.columns
        ]
        if missing_cols:
            print(
                f"Warning: Zonemap '{ZONEMAP_FILE}' missing expected columns: {missing_cols}. Please ensure correct headers or update ZONEMAP_COL constants."
            )
            # Attempt to use first available columns as a fallback if structure is consistent but names differ
            if len(zone_map_df.columns) >= 3:
                current_cols_map = {
                    zone_map_df.columns[i]: expected_zonemap_cols[i]
                    for i in range(
                        min(len(zone_map_df.columns), len(expected_zonemap_cols))
                    )
                }
                zone_map_df = zone_map_df.rename(columns=current_cols_map)
            else:
                print(
                    f"Error: Not enough columns in zonemap. Cannot proceed with SqFt analysis for {building_name}."
                )
                zone_map_df = pd.DataFrame()  # Make it empty to skip

        # Clean zonemap (copied from notebook's process_building_data)
        if not zone_map_df.empty:
            zone_map_df["Cleaned_Room_Zonemap"] = zone_map_df[ZONEMAP_ROOM_COL].apply(
                clean_room_number
            )
            zone_map_df[ZONEMAP_BUILDING_COL] = (
                zone_map_df[ZONEMAP_BUILDING_COL].astype(str).str.strip().str.upper()
            )
            zone_map_df[ZONEMAP_VAV_COL] = (
                zone_map_df[ZONEMAP_VAV_COL].astype(str).str.strip()
            )  # Keep VAV original case
            zone_map_df.dropna(
                subset=["Cleaned_Room_Zonemap", ZONEMAP_BUILDING_COL, ZONEMAP_VAV_COL],
                inplace=True,
            )
            zone_map_df = zone_map_df[
                (zone_map_df["Cleaned_Room_Zonemap"] != "")
                & (zone_map_df[ZONEMAP_BUILDING_COL] != "")
                & (zone_map_df[ZONEMAP_VAV_COL] != "")
            ]

    except FileNotFoundError:
        print(
            f"Warning: Zonemap file '{ZONEMAP_FILE}' not found. SqFt data will be missing for all VAVs for {building_name}."
        )
        zone_map_df = pd.DataFrame()
    except Exception as e:
        print(
            f"Error reading zonemap file '{ZONEMAP_FILE}': {e}. SqFt data may be missing for {building_name}."
        )
        zone_map_df = pd.DataFrame()

    project_sqft_data_df = pd.DataFrame()
    if not zone_map_df.empty:
        # Find the relevant Excel file for the current building_name (Assumed in root)
        excel_files = glob.glob(EXCEL_FILES_PATTERN)
        current_excel_file = None
        for f_path in excel_files:
            f_name_no_ext = os.path.splitext(os.path.basename(f_path))[0]
            if (
                f_name_no_ext.upper() == building_name.upper()
            ):  # Match building name (case-insensitive)
                current_excel_file = f_path
                break

        room_sqft_df_for_building = pd.DataFrame()
        if current_excel_file:
            try:
                excel_df = pd.read_excel(current_excel_file, header=EXCEL_HEADER_ROW)
                if (
                    EXCEL_ROOM_COL in excel_df.columns
                    and EXCEL_SQFT_COL in excel_df.columns
                ):
                    room_sqft_df_for_building = excel_df[
                        [EXCEL_ROOM_COL, EXCEL_SQFT_COL]
                    ].copy()
                    room_sqft_df_for_building.rename(
                        columns={EXCEL_SQFT_COL: "Sq_Feet_Room_Excel"}, inplace=True
                    )
                    room_sqft_df_for_building["Cleaned_Room_Excel"] = (
                        room_sqft_df_for_building[EXCEL_ROOM_COL].apply(
                            clean_room_number
                        )
                    )
                    room_sqft_df_for_building["Sq_Feet_Room_Excel"] = pd.to_numeric(
                        room_sqft_df_for_building["Sq_Feet_Room_Excel"], errors="coerce"
                    )
                    room_sqft_df_for_building.dropna(
                        subset=["Cleaned_Room_Excel", "Sq_Feet_Room_Excel"],
                        inplace=True,
                    )
                    room_sqft_df_for_building = room_sqft_df_for_building[
                        room_sqft_df_for_building["Cleaned_Room_Excel"] != ""
                    ]
                    room_sqft_df_for_building.drop_duplicates(
                        subset=["Cleaned_Room_Excel"], keep="first", inplace=True
                    )
                else:
                    print(
                        f"Warning: Excel file {current_excel_file} for {building_name} missing '{EXCEL_ROOM_COL}' or '{EXCEL_SQFT_COL}'. SqFt will be NaN."
                    )
            except Exception as e:
                print(
                    f"Error reading Excel file {current_excel_file} for {building_name}: {e}. SqFt will be NaN."
                )
        else:
            print(
                f"Warning: No matching Excel file found for building '{building_name}'. SqFt data will be missing."
            )

        current_building_vavs_from_zonemap = zone_map_df[
            zone_map_df[ZONEMAP_BUILDING_COL] == building_name.upper()
        ].copy()

        if (
            not room_sqft_df_for_building.empty
            and not current_building_vavs_from_zonemap.empty
        ):
            merged_df = pd.merge(
                current_building_vavs_from_zonemap,
                room_sqft_df_for_building[["Cleaned_Room_Excel", "Sq_Feet_Room_Excel"]],
                left_on="Cleaned_Room_Zonemap",
                right_on="Cleaned_Room_Excel",
                how="left",
            )
        elif not current_building_vavs_from_zonemap.empty:
            merged_df = current_building_vavs_from_zonemap.copy()
            merged_df["Sq_Feet_Room_Excel"] = np.nan
        else:
            merged_df = pd.DataFrame()

        if not merged_df.empty:
            project_sqft_data_df = pd.DataFrame(
                {
                    "Building": merged_df[ZONEMAP_BUILDING_COL],
                    "VAV": merged_df[ZONEMAP_VAV_COL],
                    "Room_in_Zonemap": merged_df[ZONEMAP_ROOM_COL],
                    "Sq_Feet": merged_df["Sq_Feet_Room_Excel"],
                }
            )
            project_sqft_data_df.drop_duplicates(
                subset=["Building", "VAV", "Room_in_Zonemap"],
                keep="first",
                inplace=True,
            )
            project_sqft_data_df["VAV"] = (
                project_sqft_data_df["VAV"].astype(str).str.strip()
            )

    # 2. Perform analyze_vav_airflow with pre-calculated minimal airflow
    analysis_df = analyze_vav_airflow(
        year=year,
        project_name=building_name,
        project_sqft_data_df=project_sqft_data_df,
        precalculated_min_airflow_df=data_dict["min_airflow_precalculated"],
    )
    if "VAV" in analysis_df.columns:
        analysis_df["VAV"] = analysis_df["VAV"].astype(str).str.strip()

    # 3. Calculate Original Wasted Cooling (now using IAT < HSP definition - Bin 1 waste)
    original_bin1_waste_req_data = {
        "ahu_dat": data_dict["ahu_dat"],
        "iat": data_dict["iat"],
        "hsp": data_dict["hsp"],
        "airflow": data_dict["airflow"],
        "map_df": data_dict["map"],
    }
    original_bin1_wasted_per_zone, df_cooling_zonal = (
        calculate_original_bin1_wasted_cooling_per_zone(
            building_name, year, original_bin1_waste_req_data, cooling_series
        )
    )

    # 4. Simulate Airflow Scaling and calculate savings (for IAT < HSP waste)
    sim_bin1_waste_per_zone, savings_bin1_waste_per_zone, total_bldg_savings_bin1 = (
        simulate_airflow_for_bin1_waste_savings(
            building_name,
            year,
            data_dict["airflow"],
            df_cooling_zonal,
            analysis_df,
            data_dict["iat"],
            data_dict["hsp"],
            data_dict["tloads"],
            original_bin1_wasted_per_zone,
        )
    )

    # 5. NEW: Simulate Airflow Scaling and calculate savings for ALL zones
    sim_cooling_all_zones, savings_all_zones, total_bldg_savings_all = (
        simulate_airflow_for_all_zones_savings(
            building_name,
            year,
            data_dict["airflow"],
            df_cooling_zonal,
            analysis_df,
            data_dict["iat"],
            data_dict["hsp"],
            data_dict["tloads"],
            original_bin1_wasted_per_zone,  # Pass but not used for filtering
        )
    )

    # --- End of New Analysis Integration ---

    # Calculate zonal cooling
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

    # Calculate Top 10 Savings Zones (Legacy IAT < HSP waste savings)
    top_savings = pd.DataFrame()
    if (
        savings_bin1_waste_per_zone is not None
        and not savings_bin1_waste_per_zone.empty
    ):
        savings_per_zone_filtered = pd.to_numeric(
            savings_bin1_waste_per_zone, errors="coerce"
        ).dropna()
        savings_per_zone_filtered = savings_per_zone_filtered[
            savings_per_zone_filtered > 0
        ]

        if not savings_per_zone_filtered.empty:
            num_zones_savings = min(10, len(savings_per_zone_filtered))
            top_savings = savings_per_zone_filtered.nlargest(
                num_zones_savings
            ).reset_index()
            top_savings.columns = ["Zone", "Potential Savings (Scaled)"]

            total_project_potential_savings = savings_per_zone_filtered.sum()
            if total_project_potential_savings > 0:
                top_savings["% of Total Building Savings"] = (
                    top_savings["Potential Savings (Scaled)"]
                    / total_project_potential_savings
                    * 100
                ).round(1)
            else:
                top_savings["% of Total Building Savings"] = 0.0
        else:
            print(f"No zones with positive potential savings for {building_name}.")
    else:
        print(f"Savings data is None or empty for {building_name}.")

    # --- NEW: Calculate Top 10 Savings Zones (All Zones) ---
    top_savings_all_zones = pd.DataFrame()
    if savings_all_zones is not None and not savings_all_zones.empty:
        savings_all_zones_filtered = pd.to_numeric(
            savings_all_zones, errors="coerce"
        ).dropna()
        savings_all_zones_filtered = savings_all_zones_filtered[
            savings_all_zones_filtered > 0
        ]

        if not savings_all_zones_filtered.empty:
            num_zones_savings = min(10, len(savings_all_zones_filtered))
            top_savings_all_zones = savings_all_zones_filtered.nlargest(
                num_zones_savings
            ).reset_index()
            top_savings_all_zones.columns = ["Zone", "Potential Savings (All Zones)"]

            total_project_potential_savings = savings_all_zones_filtered.sum()
            if total_project_potential_savings > 0:
                top_savings_all_zones["% of Total Building Savings"] = (
                    top_savings_all_zones["Potential Savings (All Zones)"]
                    / total_project_potential_savings
                    * 100
                ).round(1)
            else:
                top_savings_all_zones["% of Total Building Savings"] = 0.0
        else:
            print(
                f"No zones with positive potential savings (All Zones) for {building_name}."
            )
    else:
        print(f"Savings data for All Zones is None or empty for {building_name}.")

    # Create processed_data dictionary with all the results (existing and new)
    processed_data = {
        "df_cooling_zonal": df_cooling_zonal,
        "df_iat_binned": df_iat_binned,
        "weekly_df_iat_binned": weekly_df_iat_binned,
        "top_wasteful": top_wasteful,
        "top_demanding": top_demanding,
        "analysis_df": analysis_df,  # Store the full analysis_df if needed later
        "top_savings": top_savings,  # Legacy IAT < HSP waste savings
        "top_savings_all_zones": top_savings_all_zones,  # NEW: All zones savings
    }

    # Include the raw zone data ONLY for clickable zones (top wasteful, top demanding, and ALL top savings)
    clickable_zones = set()
    if not top_wasteful.empty:
        clickable_zones.update(top_wasteful["Zone"].tolist())
    if not top_demanding.empty:
        clickable_zones.update(top_demanding["Zone"].tolist())
    if not top_savings_all_zones.empty:
        clickable_zones.update(
            top_savings_all_zones["Zone"].tolist()
        )  # Include top savings ALL zones
    if not top_savings.empty:
        clickable_zones.update(
            top_savings["Zone"].tolist()
        )  # Also include legacy top savings for backward compatibility

    # Print how many zones we're storing data for
    print(
        f"Storing detailed data for {len(clickable_zones)} clickable zones from all three categories"
    )

    # Filter the clickable zones to only include those that actually exist in all dataframes
    available_zones = (
        set(data_dict["iat"].columns)
        & set(data_dict["hsp"].columns)
        & set(data_dict["csp"].columns)
        & set(data_dict["airflow"].columns)
        & set(data_dict["tloads"].columns)
    )

    valid_clickable_zones = clickable_zones & available_zones

    # Only store data for the clickable zones to reduce file size (existing logic)
    print(
        f"Storing detailed data for {len(valid_clickable_zones)} clickable zones instead of all {len(data_dict['iat'].columns)} zones"
    )

    # Filter each dataframe to only include clickable zones
    if valid_clickable_zones:
        processed_data["iat"] = data_dict["iat"][list(valid_clickable_zones)]
        processed_data["hsp"] = data_dict["hsp"][list(valid_clickable_zones)]
        processed_data["csp"] = data_dict["csp"][list(valid_clickable_zones)]
        processed_data["airflow"] = data_dict["airflow"][list(valid_clickable_zones)]
        processed_data["tloads"] = data_dict["tloads"][list(valid_clickable_zones)]

        # Filter the analysis_df to only include the VAVs for which we have details.
        # This reduces the data stored in the pickle for analysis_df,
        # making it faster to load into the callback.
        if "VAV" in analysis_df.columns:
            analysis_df_filtered_for_detail = analysis_df[
                analysis_df["VAV"].isin([str(z) for z in list(valid_clickable_zones)])
            ].copy()
            processed_data["analysis_df_for_details"] = analysis_df_filtered_for_detail
        else:
            processed_data["analysis_df_for_details"] = pd.DataFrame()

    else:
        print(
            "Warning: No valid clickable zones found. Not storing detailed zone data."
        )
        # Store empty dataframes to maintain structure
        processed_data["iat"] = pd.DataFrame()
        processed_data["hsp"] = pd.DataFrame()
        processed_data["csp"] = pd.DataFrame()
        processed_data["airflow"] = pd.DataFrame()
        processed_data["tloads"] = pd.DataFrame()
        processed_data["analysis_df_for_details"] = pd.DataFrame()

    return processed_data


def process_and_save_test_data():
    """
    Process the test data files for all buildings and save the results for quick loading.
    Will save data locally and upload to S3 if environment variables are configured.
    Each building's data will be stored in a separate file.
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

    # NEW: Define the analysis year. Adjust this as needed for your data.
    ANALYSIS_YEAR = "2024"
    print(f"Using analysis year: {ANALYSIS_YEAR}")

    # Process each building and store results
    output_dir = "processed_data"
    os.makedirs(output_dir, exist_ok=True)

    building_names = []
    successful_buildings = 0

    # Process and save each building individually
    for building_name, building_dir in buildings:
        print(f"\n=== Processing building: {building_name} ===")
        # Pass the analysis year to process_building_data
        building_data = process_building_data(
            building_name, building_dir, ANALYSIS_YEAR
        )  # NEW

        if building_data:
            # Create a safe filename version of the building name
            safe_name = (
                building_name.replace(" ", "_").replace("/", "_").replace("\\", "_")
            )

            # Save locally as a backup
            local_path = os.path.join(output_dir, f"building_{safe_name}.pkl")
            with open(local_path, "wb") as f:
                pickle.dump(building_data, f)
            print(f"Saved building data locally to {local_path}")

            # Upload to S3 if configured
            if os.environ.get("S3_BUCKET_NAME"):
                s3_building_path = f"buildings/{safe_name}.pkl"
                if upload_to_s3(building_data, s3_building_path):
                    print(
                        f"Successfully uploaded building data to S3 at {s3_building_path}"
                    )
                    building_names.append(building_name)
                    successful_buildings += 1
                else:
                    print(f"Failed to upload building data to S3")
            else:
                # Even if not uploading to S3, add to the building names list for local usage
                building_names.append(building_name)
                successful_buildings += 1

            print(f"Successfully processed data for {building_name}")
        else:
            print(f"Failed to process data for {building_name}")

    if successful_buildings == 0:
        print("No building data was successfully processed.")
        return

    # Create buildings info dictionary
    buildings_info = {"names": building_names}

    # Save buildings info locally
    buildings_info_path = os.path.join(output_dir, "buildings_info.pkl")
    with open(buildings_info_path, "wb") as f:
        pickle.dump(buildings_info, f)

    print(f"\nSuccessfully processed {successful_buildings} buildings.")
    print(f"Building list saved locally to {buildings_info_path}")

    # Upload buildings info to S3 if configured
    if os.environ.get("S3_BUCKET_NAME"):
        s3_buildings_info_path = os.environ.get(
            "S3_BUILDINGS_INFO_PATH", "buildings/buildings_info.pkl"
        )
        if upload_to_s3(buildings_info, s3_buildings_info_path):
            print(
                f"Successfully uploaded building list to S3 at {s3_buildings_info_path}"
            )
        else:
            print(f"Failed to upload building list to S3")
    else:
        print("\nS3 upload skipped - S3_BUCKET_NAME environment variable not set")

    print("Processing completed successfully.")


def create_sample_building_structure():
    """
    Create a sample multi-building structure for demonstration purposes
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


def analyze_vav_airflow(
    year, project_name, project_sqft_data_df, precalculated_min_airflow_df
):
    """
    Orchestrates airflow analysis for a given project.
    1. Uses pre-provided minimal airflow data.
    2. Merges it with VAV square footage data.
    3. Calculates ASHRAE guideline airflow.
    4. Returns a comprehensive analysis DataFrame.
    """
    print(f"--- Starting analyze_vav_airflow for: {project_name}, {year} ---")

    if project_sqft_data_df.empty:
        print(
            f"Warning: Square footage data for {project_name} is empty. ASHRAE guidelines cannot be calculated accurately."
        )
        # If no sqft data, but we have precalculated min airflow, we can still create a basic analysis_df
        if (
            precalculated_min_airflow_df is not None
            and not precalculated_min_airflow_df.empty
            and "VAV" in precalculated_min_airflow_df.columns
            and "Calculated_Min_Airflow_CFM" in precalculated_min_airflow_df.columns
        ):
            analysis_df = precalculated_min_airflow_df[
                ["VAV", "Calculated_Min_Airflow_CFM"]
            ].copy()
            analysis_df["Building"] = project_name
            analysis_df["Room_in_Zonemap"] = np.nan
            analysis_df["Sq_Feet"] = np.nan
            # Ensure the min airflow is numeric
            analysis_df["Calculated_Min_Airflow_CFM"] = pd.to_numeric(
                analysis_df["Calculated_Min_Airflow_CFM"], errors="coerce"
            )
        else:
            print(
                f"Error: Both project_sqft_data_df and precalculated_min_airflow_df are empty or missing required columns for {project_name}. Cannot proceed."
            )
            # Return a DataFrame with the expected columns but no data
            return pd.DataFrame(
                columns=[
                    "Building",
                    "VAV",
                    "Room_in_Zonemap",
                    "Sq_Feet",
                    "Calculated_Min_Airflow_CFM",
                    "ASHRAE_Guideline_CFM",
                    "Difference_CFM",
                    "Status",
                ]
            )
    else:
        analysis_df = project_sqft_data_df.copy()

    # Ensure 'VAV' column exists for merging. It should be in project_sqft_data_df or created above.
    if "VAV" not in analysis_df.columns:
        print(
            f"CRITICAL Error: 'VAV' column not found in analysis_df (or project_sqft_data_df for {project_name}). Cannot merge airflow calculations."
        )
        # Fallback if VAV column is missing, try to return basic min airflow data
        if (
            precalculated_min_airflow_df is not None
            and "VAV" in precalculated_min_airflow_df.columns
            and "Calculated_Min_Airflow_CFM" in precalculated_min_airflow_df.columns
        ):
            return precalculated_min_airflow_df[
                ["VAV", "Calculated_Min_Airflow_CFM"]
            ].copy()
        return pd.DataFrame(
            columns=[
                "Building",
                "VAV",
                "Room_in_Zonemap",
                "Sq_Feet",
                "Calculated_Min_Airflow_CFM",
                "ASHRAE_Guideline_CFM",
                "Difference_CFM",
                "Status",
            ]
        )

    # 1. Use pre-calculated minimal airflow data (REQUIRED input now)
    if (
        precalculated_min_airflow_df is None
        or precalculated_min_airflow_df.empty
        or "VAV" not in precalculated_min_airflow_df.columns
        or "Calculated_Min_Airflow_CFM" not in precalculated_min_airflow_df.columns
    ):
        print(
            f"CRITICAL Error: Pre-calculated minimal airflow data is missing or invalid for {project_name}. Cannot proceed with analysis."
        )
        # Make sure to return a DataFrame with the expected columns
        if "VAV" in analysis_df.columns:
            analysis_df["Calculated_Min_Airflow_CFM"] = np.nan
        return pd.DataFrame(
            columns=[
                "Building",
                "VAV",
                "Room_in_Zonemap",
                "Sq_Feet",
                "Calculated_Min_Airflow_CFM",
                "ASHRAE_Guideline_CFM",
                "Difference_CFM",
                "Status",
            ]
        )

    calculated_min_airflow_df = precalculated_min_airflow_df[
        ["VAV", "Calculated_Min_Airflow_CFM"]
    ].copy()

    # Print the column names for debugging
    print(f"Min airflow data columns: {calculated_min_airflow_df.columns.tolist()}")

    # Rename VAV column for consistent merge key
    calculated_min_airflow_df.columns = [
        "VAV_from_min_airflow_file",
        "Calculated_Min_Airflow_CFM",
    ]

    # 2. Merge pre-calculated minimal airflow into the analysis_df
    analysis_df["VAV"] = analysis_df["VAV"].astype(str).str.strip()
    calculated_min_airflow_df["VAV_from_min_airflow_file"] = (
        calculated_min_airflow_df["VAV_from_min_airflow_file"].astype(str).str.strip()
    )

    # Add debug print to see the data before merge
    print(
        f"Analysis df before merge: {len(analysis_df)} rows, columns: {analysis_df.columns.tolist()}"
    )
    print(f"Min airflow data: {len(calculated_min_airflow_df)} rows")

    analysis_df = pd.merge(
        analysis_df,
        calculated_min_airflow_df,
        left_on="VAV",
        right_on="VAV_from_min_airflow_file",
        how="left",  # Keep all VAVs from sqft data, add min airflow if matched
    )

    # Add debug print to see the data after merge
    print(
        f"Analysis df after merge: {len(analysis_df)} rows, columns: {analysis_df.columns.tolist()}"
    )

    # Drop the redundant VAV column from the merge source
    if "VAV_from_min_airflow_file" in analysis_df.columns:
        analysis_df.drop(
            columns=["VAV_from_min_airflow_file"], inplace=True, errors="ignore"
        )

    # Fix column names if merge created _x and _y suffixes
    if "Calculated_Min_Airflow_CFM_y" in analysis_df.columns:
        # If we have both _x and _y versions, prefer the _y (from the min_airflow file)
        if "Calculated_Min_Airflow_CFM_x" in analysis_df.columns:
            analysis_df.drop(
                columns=["Calculated_Min_Airflow_CFM_x"], inplace=True, errors="ignore"
            )
        # Rename _y to the original name
        analysis_df.rename(
            columns={"Calculated_Min_Airflow_CFM_y": "Calculated_Min_Airflow_CFM"},
            inplace=True,
        )
    elif "Calculated_Min_Airflow_CFM_x" in analysis_df.columns:
        # If we only have _x version, rename it
        analysis_df.rename(
            columns={"Calculated_Min_Airflow_CFM_x": "Calculated_Min_Airflow_CFM"},
            inplace=True,
        )

    # Print columns after cleanup for debugging
    print(f"Analysis df after column cleanup: columns: {analysis_df.columns.tolist()}")

    # 3. Calculate ASHRAE Guideline Airflow (UNMODIFIED)
    analysis_df["Sq_Feet"] = pd.to_numeric(analysis_df["Sq_Feet"], errors="coerce")
    analysis_df["ASHRAE_Guideline_CFM"] = analysis_df["Sq_Feet"] * ASHRAE_CFM_PER_SQFT

    # Ensure the min airflow is numeric
    analysis_df["Calculated_Min_Airflow_CFM"] = pd.to_numeric(
        analysis_df["Calculated_Min_Airflow_CFM"], errors="coerce"
    )

    # 4. Calculate Difference and Status (UNMODIFIED)
    if (
        "Calculated_Min_Airflow_CFM" in analysis_df.columns
        and "ASHRAE_Guideline_CFM" in analysis_df.columns
    ):
        analysis_df["Difference_CFM"] = (
            analysis_df["Calculated_Min_Airflow_CFM"]
            - analysis_df["ASHRAE_Guideline_CFM"]
        )
    else:
        print(f"Warning: Missing columns for difference calculation in {project_name}")
        missing_cols = []
        if "Calculated_Min_Airflow_CFM" not in analysis_df.columns:
            missing_cols.append("Calculated_Min_Airflow_CFM")
        if "ASHRAE_Guideline_CFM" not in analysis_df.columns:
            missing_cols.append("ASHRAE_Guideline_CFM")
        print(f"Missing columns: {missing_cols}")
        analysis_df["Difference_CFM"] = np.nan

    def determine_status(row):
        if pd.isna(row.get("Calculated_Min_Airflow_CFM", np.nan)) or pd.isna(
            row.get("ASHRAE_Guideline_CFM", np.nan)
        ):
            if pd.isna(row.get("Sq_Feet", np.nan)):
                return "Sq_Feet Missing"
            if pd.isna(row.get("Calculated_Min_Airflow_CFM", np.nan)):
                return "Min_Airflow_Uncalculated"
            return "Insufficient Data"
        if row["Calculated_Min_Airflow_CFM"] < row["ASHRAE_Guideline_CFM"]:
            return "Below Guideline"
        else:
            return "Meets/Exceeds Guideline"

    analysis_df["Status"] = analysis_df.apply(determine_status, axis=1)

    desired_cols_order = [
        "Building",
        "VAV",
        "Room_in_Zonemap",
        "Sq_Feet",
        "Calculated_Min_Airflow_CFM",
        "ASHRAE_Guideline_CFM",
        "Difference_CFM",
        "Status",
    ]
    final_columns = [col for col in desired_cols_order if col in analysis_df.columns]
    analysis_df = analysis_df[final_columns]

    print(f"--- analyze_vav_airflow for {project_name} - Complete ---")
    return analysis_df


def calculate_original_bin1_wasted_cooling_per_zone(
    project_name,
    year,
    required_data_for_project,  # Dict: airflow, iat, hsp, ahu_dat, map_df
    building_total_cooling_series,
):
    """
    Calculates:
    1. Original zonal cooling time series (df_cooling_zonal_original).
    2. Original "Bin 1 Wasted Cooling" (cooling when IAT < HSP) summed per zone.
       This is the cooling energy delivered when the zone is below its heating setpoint.

    Args:
        project_name (str): Project name.
        year (str): Analysis year.
        required_data_for_project (dict): Must contain 'airflow', 'iat', 'hsp',
                                          'ahu_dat', 'map_df'.
        building_total_cooling_series (pd.Series): Total cooling for this project.

    Returns:
        tuple: (
            total_bin1_wasted_cooling_original_per_zone (pd.Series),
            df_cooling_zonal_original (pd.DataFrame)
        )
        Returns (pd.Series(dtype=float), pd.DataFrame()) if errors occur.
    """
    print(
        f"--- Calculating Original Bin 1 Wasted Cooling (IAT < HSP) for {project_name}, Year {year} ---"
    )

    airflow = required_data_for_project.get("airflow")  # Original airflow
    iat = required_data_for_project.get("iat")
    hsp = required_data_for_project.get("hsp")
    ahu_dat = required_data_for_project.get("ahu_dat")
    map_df = required_data_for_project.get("map_df")

    missing_data_keys = []
    all_inputs_for_check = {
        "airflow": airflow,
        "iat": iat,
        "hsp": hsp,
        "ahu_dat": ahu_dat,
        "map_df": map_df,
        "building_total_cooling_series": building_total_cooling_series,
    }
    for k, v_df in all_inputs_for_check.items():
        if v_df is None:
            missing_data_keys.append(k)
    if missing_data_keys:
        print(
            f"  Error: Missing essential data (is None) for {project_name} for Bin 1 Waste. Missing: {missing_data_keys}"
        )
        return (
            pd.Series(dtype=float, name=f"Bin1_Wasted_Cooling_{project_name}"),
            pd.DataFrame(),
        )

    empty_data_keys = []
    if (
        isinstance(building_total_cooling_series, pd.Series)
        and building_total_cooling_series.empty
    ):
        empty_data_keys.append("building_total_cooling_series (empty Series)")
    for k_df, v_df_obj in {
        "airflow": airflow,
        "iat": iat,
        "hsp": hsp,
        "ahu_dat": ahu_dat,
        "map_df": map_df,
    }.items():
        if isinstance(v_df_obj, (pd.DataFrame, pd.Series)) and v_df_obj.empty:
            empty_data_keys.append(f"{k_df} (empty DataFrame/Series)")
    if empty_data_keys:
        print(
            f"  Warning: Inputs empty for {project_name} for Bin 1 Waste. Empty: {empty_data_keys}"
        )
        if any(
            key_check in str(empty_data_keys)
            for key_check in [
                "airflow",
                "iat",
                "hsp",
                "ahu_dat",
                "map_df",
                "building_total_cooling_series",
            ]
        ):
            print(
                f"     Critical input empty. Aborting Bin 1 waste calculation for {project_name}."
            )
            return (
                pd.Series(dtype=float, name=f"Bin1_Wasted_Cooling_{project_name}"),
                pd.DataFrame(),
            )

    if isinstance(building_total_cooling_series, pd.DataFrame):
        if len(building_total_cooling_series.columns) == 1:
            building_total_cooling_series = building_total_cooling_series.iloc[:, 0]
        else:
            print(
                f"  Error: building_total_cooling_series for {project_name} is multi-column DataFrame for Bin 1 Waste."
            )
            return (
                pd.Series(dtype=float, name=f"Bin1_Wasted_Cooling_{project_name}"),
                pd.DataFrame(),
            )

    df_cooling_zonal_original = pd.DataFrame()
    try:
        df_cooling_zonal_original = get_cooling_zonal_from_data(
            project_name, ahu_dat, iat, airflow, map_df, building_total_cooling_series
        )
    except Exception as e_gcz_b1:
        print(
            f"  Error during original get_cooling_zonal_from_data for Bin 1 Waste in {project_name}: {e_gcz_b1}"
        )
        return (
            pd.Series(dtype=float, name=f"Bin1_Wasted_Cooling_{project_name}"),
            pd.DataFrame(),
        )

    if df_cooling_zonal_original is None or df_cooling_zonal_original.empty:
        print(
            f"  Original zonal cooling calculation returned None or empty for {project_name} (Bin 1 Waste)."
        )
        return (
            pd.Series(dtype=float, name=f"Bin1_Wasted_Cooling_{project_name}"),
            pd.DataFrame(),
        )

    common_index_b1 = df_cooling_zonal_original.index
    common_cols_b1 = df_cooling_zonal_original.columns.intersection(
        iat.columns
    ).intersection(hsp.columns)

    if not common_cols_b1.tolist():
        print(
            f"  No common VAVs between original zonal cooling, IAT, and HSP for {project_name} (Bin 1 Waste)."
        )
        return (
            pd.Series(dtype=float, name=f"Bin1_Wasted_Cooling_{project_name}"),
            df_cooling_zonal_original,
        )

    iat_aligned = iat.reindex(index=common_index_b1, columns=common_cols_b1).fillna(
        method="ffill"
    )
    hsp_aligned = hsp.reindex(index=common_index_b1, columns=common_cols_b1).fillna(
        method="ffill"
    )
    cooling_zonal_common_b1 = df_cooling_zonal_original[common_cols_b1]

    iat_lt_hsp_mask = iat_aligned < hsp_aligned

    df_bin1_wasted_cooling_zonal = cooling_zonal_common_b1.where(
        iat_lt_hsp_mask, 0
    ).fillna(0)

    total_bin1_wasted_cooling_original_per_zone = df_bin1_wasted_cooling_zonal.sum(
        axis=0
    )
    total_bin1_wasted_cooling_original_per_zone.name = (
        "Original_Bin1_Wasted_Cooling_per_Zone"
    )

    print(
        f"  Original Bin 1 Wasted Cooling (IAT < HSP) per zone calculated for {len(total_bin1_wasted_cooling_original_per_zone)} zones in {project_name}."
    )

    return total_bin1_wasted_cooling_original_per_zone, df_cooling_zonal_original


def simulate_airflow_for_bin1_waste_savings(
    project_name,
    year,
    original_airflow_df,
    original_cooling_zonal_df,
    analysis_df_for_project,
    iat_df,
    hsp_df,
    tload_df,
    original_total_bin1_wasted_per_zone,  # Series from calculate_original_bin1_wasted_cooling_per_zone
):
    """
    Simulates adjusting min airflow to ASHRAE guidelines when tload is zero.
    Recalculates zonal cooling by scaling.
    Then calculates the change in "Bin 1 Wasted Cooling" (cooling when IAT < HSP).

    Returns:
        tuple: (
            simulated_total_bin1_wasted_per_zone (pd.Series),
            savings_in_bin1_waste_per_zone (pd.Series),
            total_building_savings_in_bin1_waste (float)
        )
    """
    print(
        f"--- Simulating Airflow for Bin 1 Waste Savings: {project_name}, Year {year} ---"
    )

    if any(
        df is None or df.empty
        for df in [
            original_airflow_df,
            original_cooling_zonal_df,
            iat_df,
            hsp_df,
            tload_df,
        ]
    ):  # Added tload_df validation
        print(
            f"  One or more critical input DataFrames (airflow, cooling_zonal, iat, hsp, tload) missing/empty for {project_name}. Cannot simulate Bin 1 waste savings."
        )
        return None, None, None
    if (
        analysis_df_for_project.empty
        or "ASHRAE_Guideline_CFM" not in analysis_df_for_project.columns
    ):
        print(
            f"  Analysis data with ASHRAE guidelines missing for {project_name}. Cannot simulate."
        )
        return None, None, None

    simulated_airflow_df = original_airflow_df.copy()
    common_index_sim = original_airflow_df.index.intersection(tload_df.index)
    common_cols_sim = original_airflow_df.columns.intersection(tload_df.columns)
    if not common_index_sim.tolist() or not common_cols_sim.tolist():
        print(
            f"  No common timestamps/VAVs between airflow and tload for {project_name} (Bin 1 sim)."
        )
        return None, None, None
    tload_df_aligned = tload_df.reindex(index=common_index_sim, columns=common_cols_sim)
    tload_zero_deadband = 50
    min_airflow_period_mask_df = (tload_df_aligned >= -tload_zero_deadband) & (
        tload_df_aligned <= tload_zero_deadband
    )

    zones_airflow_changed_count_b1 = 0
    for vav_name in common_cols_sim:
        if (
            vav_name
            not in analysis_df_for_project["VAV"].astype(str).str.strip().values
        ):
            continue
        ashrae_guideline_cfm_series = analysis_df_for_project.loc[
            analysis_df_for_project["VAV"].astype(str).str.strip() == vav_name,
            "ASHRAE_Guideline_CFM",
        ]
        if ashrae_guideline_cfm_series.empty or pd.isna(
            ashrae_guideline_cfm_series.iloc[0]
        ):
            continue
        ashrae_guideline_cfm = ashrae_guideline_cfm_series.iloc[0]
        vav_min_load_timestamps = min_airflow_period_mask_df[vav_name][
            min_airflow_period_mask_df[vav_name]
        ].index
        if not vav_min_load_timestamps.tolist():
            continue
        original_airflow_at_min_load = simulated_airflow_df.loc[
            vav_min_load_timestamps, vav_name
        ]
        target_airflow_at_min_load = original_airflow_at_min_load.copy()
        reduction_mask = original_airflow_at_min_load > ashrae_guideline_cfm
        target_airflow_at_min_load[reduction_mask] = ashrae_guideline_cfm
        simulated_airflow_df.loc[vav_min_load_timestamps, vav_name] = (
            target_airflow_at_min_load
        )
        if reduction_mask.any():
            zones_airflow_changed_count_b1 += 1
    print(
        f"  Bin 1 Sim: Airflow potentially reduced for {zones_airflow_changed_count_b1} VAVs during tload~0 periods."
    )

    final_common_index_b1_sim = original_cooling_zonal_df.index
    final_common_cols_b1_sim = original_cooling_zonal_df.columns
    orig_airflow_aligned_for_scaling_b1 = original_airflow_df.reindex(
        index=final_common_index_b1_sim, columns=final_common_cols_b1_sim
    ).fillna(0)
    sim_airflow_aligned_for_scaling_b1 = simulated_airflow_df.reindex(
        index=final_common_index_b1_sim, columns=final_common_cols_b1_sim
    ).fillna(0)

    airflow_ratio_b1 = sim_airflow_aligned_for_scaling_b1.divide(
        orig_airflow_aligned_for_scaling_b1
    ).fillna(1.0)
    airflow_ratio_b1[orig_airflow_aligned_for_scaling_b1 == 0] = 0

    df_cooling_zonal_simulated_b1 = original_cooling_zonal_df * airflow_ratio_b1
    df_cooling_zonal_simulated_b1[orig_airflow_aligned_for_scaling_b1 == 0] = 0

    common_cols_b1_sim_final = df_cooling_zonal_simulated_b1.columns.intersection(
        iat_df.columns
    ).intersection(hsp_df.columns)
    if not common_cols_b1_sim_final.tolist():
        print(
            f"  No common VAVs for simulated Bin 1 waste calculation in {project_name}."
        )
        return None, None, None

    iat_aligned_sim = iat_df.reindex(
        index=df_cooling_zonal_simulated_b1.index, columns=common_cols_b1_sim_final
    ).fillna(method="ffill")
    hsp_aligned_sim = hsp_df.reindex(
        index=df_cooling_zonal_simulated_b1.index, columns=common_cols_b1_sim_final
    ).fillna(method="ffill")
    cooling_zonal_for_bin1_sim = df_cooling_zonal_simulated_b1[common_cols_b1_sim_final]

    iat_lt_hsp_mask_sim = iat_aligned_sim < hsp_aligned_sim
    df_bin1_wasted_cooling_zonal_simulated = cooling_zonal_for_bin1_sim.where(
        iat_lt_hsp_mask_sim, 0
    ).fillna(0)

    simulated_total_bin1_wasted_per_zone = df_bin1_wasted_cooling_zonal_simulated.sum(
        axis=0
    )
    simulated_total_bin1_wasted_per_zone.name = "Simulated_Bin1_Wasted_Cooling_per_Zone"

    original_bin1_aligned = original_total_bin1_wasted_per_zone.reindex(
        simulated_total_bin1_wasted_per_zone.index
    ).fillna(0)

    savings_in_bin1_waste_per_zone = (
        original_bin1_aligned - simulated_total_bin1_wasted_per_zone
    )
    savings_in_bin1_waste_per_zone.name = "Bin1_Wasted_Cooling_Savings_per_Zone"
    total_building_savings_in_bin1_waste = savings_in_bin1_waste_per_zone.sum()

    print(
        f"  Bin 1 Waste Simulation (scaling) for {project_name} complete. Total potential Bin 1 waste savings: {total_building_savings_in_bin1_waste:.2f}"
    )

    return (
        simulated_total_bin1_wasted_per_zone,
        savings_in_bin1_waste_per_zone,
        total_building_savings_in_bin1_waste,
    )


def simulate_airflow_for_all_zones_savings(
    project_name,
    year,
    original_airflow_df,
    original_cooling_zonal_df,
    analysis_df_for_project,
    iat_df,
    hsp_df,
    tload_df,
    original_total_bin1_wasted_per_zone,  # Still needed for comparison, but not used for filtering
):
    """
    Simulates adjusting min airflow to ASHRAE guidelines when tload is zero for ALL zones.
    Recalculates zonal cooling by scaling airflow.
    Then calculates the total energy savings from this adjustment.

    Returns:
        tuple: (
            simulated_total_cooling_per_zone (pd.Series),
            savings_per_zone (pd.Series),
            total_building_savings (float)
        )
    """
    print(
        f"--- Simulating Airflow for ALL Zones Savings: {project_name}, Year {year} ---"
    )

    if any(
        df is None or df.empty
        for df in [
            original_airflow_df,
            original_cooling_zonal_df,
            iat_df,
            hsp_df,
            tload_df,
        ]
    ):
        print(
            f"  One or more critical input DataFrames missing/empty for {project_name}. Cannot simulate ALL zones savings."
        )
        return None, None, None
    if (
        analysis_df_for_project.empty
        or "ASHRAE_Guideline_CFM" not in analysis_df_for_project.columns
    ):
        print(
            f"  Analysis data with ASHRAE guidelines missing for {project_name}. Cannot simulate."
        )
        return None, None, None

    simulated_airflow_df = original_airflow_df.copy()
    common_index_sim = original_airflow_df.index.intersection(tload_df.index)
    common_cols_sim = original_airflow_df.columns.intersection(tload_df.columns)
    if not common_index_sim.tolist() or not common_cols_sim.tolist():
        print(
            f"  No common timestamps/VAVs between airflow and tload for {project_name} (ALL zones sim)."
        )
        return None, None, None
    tload_df_aligned = tload_df.reindex(index=common_index_sim, columns=common_cols_sim)
    tload_zero_deadband = 50
    min_airflow_period_mask_df = (tload_df_aligned >= -tload_zero_deadband) & (
        tload_df_aligned <= tload_zero_deadband
    )

    zones_airflow_changed_count = 0
    # Apply to ALL zones, not just those with IAT < HSP waste
    for vav_name in common_cols_sim:
        if (
            vav_name
            not in analysis_df_for_project["VAV"].astype(str).str.strip().values
        ):
            continue
        ashrae_guideline_cfm_series = analysis_df_for_project.loc[
            analysis_df_for_project["VAV"].astype(str).str.strip() == vav_name,
            "ASHRAE_Guideline_CFM",
        ]
        if ashrae_guideline_cfm_series.empty or pd.isna(
            ashrae_guideline_cfm_series.iloc[0]
        ):
            continue
        ashrae_guideline_cfm = ashrae_guideline_cfm_series.iloc[0]
        vav_min_load_timestamps = min_airflow_period_mask_df[vav_name][
            min_airflow_period_mask_df[vav_name]
        ].index
        if not vav_min_load_timestamps.tolist():
            continue
        original_airflow_at_min_load = simulated_airflow_df.loc[
            vav_min_load_timestamps, vav_name
        ]
        target_airflow_at_min_load = original_airflow_at_min_load.copy()
        reduction_mask = original_airflow_at_min_load > ashrae_guideline_cfm
        target_airflow_at_min_load[reduction_mask] = ashrae_guideline_cfm
        simulated_airflow_df.loc[vav_min_load_timestamps, vav_name] = (
            target_airflow_at_min_load
        )
        if reduction_mask.any():
            zones_airflow_changed_count += 1
    print(
        f"  ALL Zones Sim: Airflow potentially reduced for {zones_airflow_changed_count} VAVs during tload~0 periods."
    )

    final_common_index_sim = original_cooling_zonal_df.index
    final_common_cols_sim = original_cooling_zonal_df.columns
    orig_airflow_aligned_for_scaling = original_airflow_df.reindex(
        index=final_common_index_sim, columns=final_common_cols_sim
    ).fillna(0)
    sim_airflow_aligned_for_scaling = simulated_airflow_df.reindex(
        index=final_common_index_sim, columns=final_common_cols_sim
    ).fillna(0)

    airflow_ratio = sim_airflow_aligned_for_scaling.divide(
        orig_airflow_aligned_for_scaling
    ).fillna(1.0)
    airflow_ratio[orig_airflow_aligned_for_scaling == 0] = 0

    # Calculate simulated cooling for ALL zones based on airflow scaling
    df_cooling_zonal_simulated = original_cooling_zonal_df * airflow_ratio
    df_cooling_zonal_simulated[orig_airflow_aligned_for_scaling == 0] = 0

    # Calculate total cooling before and after simulation for ALL zones
    original_total_cooling_per_zone = original_cooling_zonal_df.sum(axis=0)
    simulated_total_cooling_per_zone = df_cooling_zonal_simulated.sum(axis=0)

    # Calculate savings for ALL zones (original - simulated)
    savings_per_zone = (
        original_total_cooling_per_zone - simulated_total_cooling_per_zone
    )
    savings_per_zone.name = "All_Zones_Cooling_Savings"
    total_building_savings = savings_per_zone.sum()

    print(
        f"  ALL Zones Simulation for {project_name} complete. Total potential savings: {total_building_savings:.2f}"
    )

    return (
        simulated_total_cooling_per_zone,
        savings_per_zone,
        total_building_savings,
    )


# Run the preprocessing when script is executed directly
if __name__ == "__main__":
    # --- Sample File Creation Notes ---
    # The original notebook created dummy zonemap.csv and Excel files in the root.
    # The AI agent needs to be aware that for a full test, these files
    # (zonemap.csv, Alumni.xlsx, Gates.xlsx, etc.) should be in the ROOT directory.
    # Also, ensure that zone_rhv.csv and zone_tloads.csv are present in each
    # building's test_app_data subfolder.
    # The provided `create_sample_building_structure` function copies existing files.
    # You might need to manually ensure zone_rhv.csv and zone_tloads.csv are in
    # the initial 'test_app_data' folder for the sample structure creation to copy them.
    # --- End Sample File Creation Notes ---

    process_and_save_test_data()

    # Optionally ask about creating sample structure
    print("\nWould you like to create a sample multi-building structure? (y/n)")
    choice = input().strip().lower()
    if choice == "y":
        create_sample_building_structure()
