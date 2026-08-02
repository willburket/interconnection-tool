# src/ingest.py — download and clean the CAISO interconnection queue

import json
import requests
import pandas as pd
from io import BytesIO
from pathlib import Path
import logging
import geopandas as gpd
import json
import re

import sys
sys.path.append(str(Path(__file__).parent.parent))
from config import (
    CAISO_QUEUE_URL, HIFLD_SUBSTATIONS_URL, HIFLD_STATE,
    QUEUE_RAW_FILE, QUEUE_CLEAN_FILE, SUBSTATIONS_FILE,
    RAW_DATA_DIR, PROCESSED_DATA_DIR, GEO_DATA_DIR,
    COLUMN_MAP, WITHDRAWN_LABEL, FUEL_TYPE_MAP,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


# ── Queue download ───────────────────────────────────────────────────────────

def clean_queue(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize columns, cast types, remove withdrawn projects, and cache to parquet.
    """
    # Normalize headers
    df.columns = df.columns.str.strip().str.lower()

    # Rename to internal names
    rename = {k: v for k, v in COLUMN_MAP.items() if k in df.columns}
    df = df.rename(columns=rename)
    df.columns = df.columns.str.replace("\n", " ", regex=False).str.replace("  ", " ", regex=False).str.strip()


    # Ensure required columns exist
    for col in ["project_name", "fuel-1", "net mws to grid",
                "station or transmission line", "application status", "study_phase"]:
        if col not in df.columns:
            df[col] = None
            print(f'"{col}" is not in columns')    #test 

    # Remove withdrawn / cancelled
    # df = df[~df["application status"].astype(str).str.strip().str.lower().eq(WITHDRAWN_LABEL)]

    # Cast capacity
    df["net mws to grid"] = pd.to_numeric(df["net mws to grid"], errors="coerce")
    df = df.dropna(subset=["net mws to grid"])

    if "interconnection request receive date" in df.columns:
        df["interconnection request receive date"] = pd.to_datetime(df["interconnection request receive date"], errors="coerce")
    if "voltage_kv" in df.columns:
        df["voltage_kv"] = pd.to_numeric(df["voltage_kv"], errors="coerce")

    # Normalize and remap fuel type labels
    df["fuel-1"] = df["fuel-1"].astype(str).str.strip().str.title()
    df["fuel-1"] = df["fuel-1"].replace(FUEL_TYPE_MAP)

    # Days in queue
    if "interconnection request receive date" in df.columns:
        df["days_in_queue"] = (pd.Timestamp.today() - df["interconnection request receive date"]).dt.days    

    df = geocode_substations(df, "data/geo/caiso_substations.geojson")  # update path as needed


    Path(PROCESSED_DATA_DIR).mkdir(parents=True, exist_ok=True)

    for col in df.columns:
        try:
            df[[col]].to_parquet(f"/tmp/test_{col}.parquet")
        except Exception as e:
            print(f"Problem column: {col} — {e}")
    # df.to_parquet(QUEUE_CLEAN_FILE, index=False)


    log.info("Saved cleaned queue (%d rows) to %s", len(df), QUEUE_CLEAN_FILE)
    return df

def load_queue(force_refresh: bool = False) -> pd.DataFrame:
    """Load queue from local Excel file."""
    excel_path = Path("publicqueuereport.xlsx")
    if not excel_path.exists():
        raise FileNotFoundError(
            "publicqueuereport.xlsx not found — place it in the project root directory."
        )
    
    try:
        df = pd.read_excel(excel_path, skiprows=3)
        return clean_queue(df)
    except Exception:
        print("error loading queue")
    return


# ── Substation download ──────────────────────────────────────────────────────

def load_substations() -> dict:
    """
    Load substation data from a local GeoPackage file.
    Saves as GeoJSON to data/geo/ for use by network.py.
    """

    gdf = gpd.read_file("src/electric_substation_hifld_v4.gpkg")
    
    # delete non-cali substations and unneeded columns
    gdf = gdf[gdf['state'] == 'CA']
    columns = ['id', 'name', 'city', 'state', 'zip', 'type', 'status', 'county', 'latitude', 'longitude', 'lines', 'max_volt', 'min_volt',]
    gdf = gdf.loc[:, columns]


    # 1. Convert standard DataFrame to a GeoDataFrame
    gdf = gpd.GeoDataFrame(
        gdf, 
        geometry=gpd.points_from_xy(gdf['longitude'], gdf['latitude']),
        crs="EPSG:4326"  # Standard WGS84 coordinate system used by GeoJSON
    )

    # Save as GeoJSON so network.py can read it as before
    Path(GEO_DATA_DIR).mkdir(parents=True, exist_ok=True)
    gdf.to_file(SUBSTATIONS_FILE, driver="GeoJSON")

    log.info("Saved %d substations from %s to %s", len(gdf),"src/electric_substation_hifld_v4.gpkg", SUBSTATIONS_FILE)
    return json.loads(gdf.to_json())

def geocode_substations(df: pd.DataFrame, gpkg_path: str, layer: str = None) -> pd.DataFrame:
    """
    Match queue projects to substation coordinates from the GeoPackage.
    Adds latitude and longitude columns to the queue DataFrame.
    """

    if layer:
        gdf = gpd.read_file(gpkg_path, layer=layer)
    else:
        gdf = gpd.read_file(gpkg_path)

    if gdf.crs and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)



    # Build name -> (lat, lon) lookup from your substation dataset
    # Update "NAME" to whatever your GeoPackage calls the substation name column
    sub_coords = {
        re.sub(r'\d+', '', row["name"].upper().strip()) : (row.geometry.y, row.geometry.x)
        for _, row in gdf.iterrows()
        if row.geometry is not None
    }    

    def get_coords(substation_name):
        name = str(substation_name).upper().strip()
        
        # Try exact match first
        if name in sub_coords:
            return sub_coords[name]
        
        # Try partial match — check if any known substation name is contained in the queue name
        for key, coords in sub_coords.items():
            if key in name or name in key:
                return coords
        
        return (None, None)

    df[["latitude", "longitude"]] = df["station or transmission line"].apply(
        lambda x: pd.Series(get_coords(x))
    )

    matched = df["latitude"].notna().sum()
    # print(f"Rows with coords: {len(matched):,}")
    log.info("Geocoded %d of %d projects (%.0f%%)", matched, len(df), matched / len(df) * 100)

    return df

# ── Summary ──────────────────────────────────────────────────────────────────

def queue_summary(df: pd.DataFrame) -> None:
    print(f"\n{'='*55}")
    print(f"  CAISO Interconnection Queue Summary")
    print(f"{'='*55}")
    print(f"  Total active projects : {len(df):,}")
    print(f"  Total capacity (MW)   : {df['net mws to grid'].sum():,.0f}")
    print(f"\n  Capacity by fuel type:")
    for fuel, mw in df.groupby("fuel-1")["net mws to grid"].sum().sort_values(ascending=False).items():
        print(f"    {fuel:<25} {mw:>10,.0f} MW")
    if "study_phase" in df.columns:
        print(f"\n  Projects by study phase:")
        for phase, count in df["study_phase"].value_counts().items():
            print(f"    {str(phase):<35} {count:>5}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    df = load_queue(force_refresh=True)
    queue_summary(df)
