import pandas as pd
import numpy as np


def get_cooling_zonal_from_data(
    project_name, ahu_dat_df, iat_df, airflow_df, map_df, cooling_project_series
):
    """
    Computes zone-level cooling from DataFrames.
    Args:
        project_name (str): Name for logging/errors.
        ahu_dat_df (pd.DataFrame): AHU discharge temps (time x AHU).
        iat_df (pd.DataFrame): Zone temps (time x Zone).
        airflow_df (pd.DataFrame): Zone airflow (time x Zone).
        map_df (pd.DataFrame): Mapping with 'ZoneID' and 'AHUID' columns.
        cooling_project_series (pd.Series): Total building cooling (time index).
    Returns:
        pd.DataFrame or None: Zone-level cooling (time x Zone).
    """
    if ahu_dat_df is None or ahu_dat_df.empty:
        print(f"Skipping {project_name}: AHU data is missing or empty.")
        return None
    if iat_df is None or iat_df.empty:
        print(f"Skipping {project_name}: IAT data is missing or empty.")
        return None
    if airflow_df is None or airflow_df.empty:
        print(f"Skipping {project_name}: Airflow data is missing or empty.")
        return None
    if map_df is None or map_df.empty:
        print(f"Skipping {project_name}: Zone->AHU map is missing or empty.")
        return None
    if cooling_project_series is None or cooling_project_series.empty:
        print(f"Skipping {project_name}: Building cooling data is missing or empty.")
        return None

    # Ensure map_df has the right columns and set index
    if not {"ZoneID", "AHUID"}.issubset(map_df.columns):
        raise ValueError("Map DataFrame must contain 'ZoneID' and 'AHUID' columns.")
    map_df = map_df.set_index("ZoneID")

    # Align indices (assuming they are already datetime) - Use outer join initially
    all_indices = (
        ahu_dat_df.index.union(iat_df.index)
        .union(airflow_df.index)
        .union(cooling_project_series.index)
    )
    common_index = pd.date_range(
        start=all_indices.min(), end=all_indices.max(), freq="H"
    )  # Or choose appropriate freq

    # Reindex and forward fill (or choose another strategy)
    # Important: Ensure columns match VAV/Zone names expected
    ahu_dat_df = ahu_dat_df.reindex(common_index).ffill().bfill()
    iat_df = iat_df.reindex(common_index).ffill().bfill()
    airflow_df = airflow_df.reindex(common_index).ffill().bfill()
    cooling_project_series = (
        cooling_project_series.reindex(common_index).ffill().bfill()
    )

    # Filter IAT and Airflow columns to only those in the map
    valid_zones = map_df.index.intersection(iat_df.columns).intersection(
        airflow_df.columns
    )
    iat = iat_df[valid_zones]
    airflow = airflow_df[valid_zones]
    map_df = map_df.loc[valid_zones]  # Filter map too

    # Filter AHU columns to only those in the map
    valid_ahus = map_df["AHUID"].unique()
    dat_ahu = ahu_dat_df[[ahu for ahu in valid_ahus if ahu in ahu_dat_df.columns]]

    # --- Rest of the get_cooling_zonal logic ---
    dat_vav = pd.DataFrame(index=dat_ahu.index, columns=valid_zones)

    for ahu in map_df["AHUID"].unique():
        if ahu not in dat_ahu.columns:
            print(
                f"Warning: AHU {ahu} found in map but not in AHU data columns. Skipping."
            )
            continue
        # Get zones served by this AHU
        ahu_vavs = map_df[map_df["AHUID"] == ahu].index.tolist()

        # Assign AHU temp to these zones
        for vav in ahu_vavs:
            if vav in dat_vav.columns:
                dat_vav[vav] = dat_ahu[ahu]

    # Proportional factor
    prop = (iat - dat_vav) * airflow
    prop = prop.clip(lower=0)  # Equivalent to applymap(lambda x: max(x, 0))

    # Sum prop only over valid zones
    tot_prop = prop.sum(axis=1)

    cooling_zonal = pd.DataFrame(index=prop.index, columns=prop.columns)

    # Avoid division by zero
    safe_tot_prop = tot_prop.replace(
        0, np.nan
    )  # Replace 0 with NaN to avoid division errors

    for col in cooling_zonal.columns:
        # Check if cooling_project_series has values for the index
        cooling_values = cooling_project_series.reindex(prop.index).values
        # Element-wise multiplication and division
        cooling_zonal[col] = cooling_values * prop[col] / safe_tot_prop

    # Fill NaNs that resulted from division by zero or initial alignment
    cooling_zonal.fillna(0, inplace=True)
    # Drop rows where all zones are 0 (optional, might happen due to reindexing)
    cooling_zonal = cooling_zonal.loc[(cooling_zonal != 0).any(axis=1)]

    return cooling_zonal


def categorize_cooling_by_iat_bins_from_data(
    project_name, iat_df, hsp_df, csp_df, df_cooling_zonal
):
    """
    Categorizes zone-level cooling into 6 bins based on IAT relative to setpoints.
    Args:
        project_name (str): Name for logging.
        iat_df (pd.DataFrame): Zone temps (time x Zone).
        hsp_df (pd.DataFrame): Heating setpoints (time x Zone).
        csp_df (pd.DataFrame): Cooling setpoints (time x Zone).
        df_cooling_zonal (pd.DataFrame): Result from get_cooling_zonal_from_data.
    Returns:
        pd.DataFrame or None: Cooling summed into bins (time x Bin).
    """
    if df_cooling_zonal is None or df_cooling_zonal.empty:
        print(f"Skipping binning for {project_name}: No valid zone cooling data.")
        return None
    if iat_df is None or iat_df.empty:
        print(f"Skipping binning for {project_name}: IAT data is missing or empty.")
        return None
    if hsp_df is None or hsp_df.empty:
        print(f"Skipping binning for {project_name}: HSP data is missing or empty.")
        return None
    if csp_df is None or csp_df.empty:
        print(f"Skipping binning for {project_name}: CSP data is missing or empty.")
        return None

    # Align indices and columns - crucial step
    common_index = df_cooling_zonal.index
    common_cols = df_cooling_zonal.columns

    # Use reindex, allow filling but maybe log if shapes mismatch significantly
    iat = iat_df.reindex(index=common_index, columns=common_cols).ffill().bfill()
    hsp = hsp_df.reindex(index=common_index, columns=common_cols).ffill().bfill()
    csp = csp_df.reindex(index=common_index, columns=common_cols).ffill().bfill()

    # Check if alignment resulted in empty frames
    if iat.empty or hsp.empty or csp.empty:
        print(f"Error during alignment for {project_name}. Check data consistency.")
        return None

    # --- Rest of the categorize_cooling_by_iat_bins logic ---
    temp_range = (csp - hsp).clip(lower=0)
    bin_cut_25 = hsp + 0.25 * temp_range
    bin_cut_50 = hsp + 0.50 * temp_range
    bin_cut_75 = hsp + 0.75 * temp_range
    bin_cut_100 = csp  # Using CSP as the top of the 5th bin

    # Boolean masks (ensure they align with df_cooling_zonal's shape)
    bin1 = iat < hsp
    bin2 = (iat >= hsp) & (iat < bin_cut_25)
    bin3 = (iat >= bin_cut_25) & (iat < bin_cut_50)
    bin4 = (iat >= bin_cut_50) & (iat < bin_cut_75)
    bin5 = (iat >= bin_cut_75) & (iat < bin_cut_100)  # Updated bin5 definition
    bin6 = iat >= bin_cut_100  # New bin6

    # Sum cooling within each bin
    # Important: Use .where() which keeps the shape, then sum
    bin1_cooling = df_cooling_zonal.where(bin1, 0).sum(axis=1)
    bin2_cooling = df_cooling_zonal.where(bin2, 0).sum(axis=1)
    bin3_cooling = df_cooling_zonal.where(bin3, 0).sum(axis=1)
    bin4_cooling = df_cooling_zonal.where(bin4, 0).sum(axis=1)
    bin5_cooling = df_cooling_zonal.where(bin5, 0).sum(axis=1)
    bin6_cooling = df_cooling_zonal.where(bin6, 0).sum(axis=1)

    df_bin_cooling = pd.DataFrame(
        {
            "bin1_IAT<HSP": bin1_cooling,
            "bin2_0-25%": bin2_cooling,
            "bin3_25-50%": bin3_cooling,
            "bin4_50-75%": bin4_cooling,
            "bin5_75-100%": bin5_cooling,
            "bin6_IAT>CSP": bin6_cooling,  # Added bin6
        },
        index=common_index,
    )  # Ensure index is consistent

    return df_bin_cooling
