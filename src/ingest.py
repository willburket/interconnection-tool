# src/ingest.py — download and clean the ERCOT interconnection queue

import requests
import pandas as pd
from io import BytesIO
from pathlib import Path
import logging

import sys
sys.path.append(str(Path(__file__).parent.parent))
from config import (
    ERCOT_QUEUE_URL, HIFLD_SUBSTATIONS_URL,
    QUEUE_RAW_FILE, QUEUE_CLEAN_FILE, SUBSTATIONS_FILE,
    COLUMN_MAP, PROCESSED_DATA_DIR, RAW_DATA_DIR, GEO_DATA_DIR
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


# ── Queue download ──────────────────────────────────────────────────────────

def download_queue(url: str = ERCOT_QUEUE_URL, save_path: str = QUEUE_RAW_FILE) -> pd.DataFrame:
    """
    Pull the ERCOT Generator Interconnection Status Report Excel file.
    Saves raw file to data/raw/ and returns a raw DataFrame.
    """
    log.info("Downloading ERCOT queue from %s", url)
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    Path(RAW_DATA_DIR).mkdir(parents=True, exist_ok=True)
    with open(save_path, "wb") as f:
        f.write(response.content)
    log.info("Saved raw file to %s", save_path)

    # ERCOT reports often have a few header rows to skip — adjust if needed
    df = pd.read_excel(BytesIO(response.content), skiprows=2)
    return df


def clean_queue(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize columns, cast types, drop withdrawn projects,
    and save cleaned data to parquet.
    """
    # Normalize column headers
    df.columns = df.columns.str.strip().str.lower()

    # Rename to internal names using COLUMN_MAP
    rename = {k: v for k, v in COLUMN_MAP.items() if k in df.columns}
    df = df.rename(columns=rename)

    # Drop rows with no project ID or capacity
    df = df.dropna(subset=["project_id", "capacity_mw"])

    # Remove withdrawn projects
    if "status" in df.columns:
        df = df[~df["status"].str.strip().str.lower().eq("withdrawn")]

    # Cast types
    df["capacity_mw"] = pd.to_numeric(df["capacity_mw"], errors="coerce")
    if "application_date" in df.columns:
        df["application_date"] = pd.to_datetime(df["application_date"], errors="coerce")
    if "voltage_kv" in df.columns:
        df["voltage_kv"] = pd.to_numeric(df["voltage_kv"], errors="coerce")

    # Normalize fuel type labels
    if "fuel_type" in df.columns:
        df["fuel_type"] = df["fuel_type"].str.strip().str.title()

    # Days in queue (useful for analysis)
    if "application_date" in df.columns:
        df["days_in_queue"] = (pd.Timestamp.today() - df["application_date"]).dt.days

    Path(PROCESSED_DATA_DIR).mkdir(parents=True, exist_ok=True)
    df.to_parquet(QUEUE_CLEAN_FILE, index=False)
    log.info("Saved cleaned queue (%d rows) to %s", len(df), QUEUE_CLEAN_FILE)

    return df


def load_queue(force_refresh: bool = False) -> pd.DataFrame:
    """
    Load cleaned queue from cache or re-download if needed.
    Main entry point for other modules.
    """
    clean_path = Path(QUEUE_CLEAN_FILE)
    if not force_refresh and clean_path.exists():
        log.info("Loading queue from cache: %s", QUEUE_CLEAN_FILE)
        return pd.read_parquet(QUEUE_CLEAN_FILE)

    raw = download_queue()
    return clean_queue(raw)


# ── Substation download ─────────────────────────────────────────────────────

def download_substations(state: str = "TX") -> dict:
    """
    Pull substation locations from HIFLD public API.
    Returns GeoJSON dict and saves to data/geo/.
    """
    log.info("Fetching HIFLD substations for state=%s", state)
    params = {
        "where":       f"STATE='{state}'",
        "outFields":   "NAME,CITY,STATE,LATITUDE,LONGITUDE,MIN_VOLT,MAX_VOLT,LINES",
        "f":           "geojson",
        "resultRecordCount": 5000,
    }
    response = requests.get(HIFLD_SUBSTATIONS_URL, params=params, timeout=30)
    response.raise_for_status()

    Path(GEO_DATA_DIR).mkdir(parents=True, exist_ok=True)
    with open(SUBSTATIONS_FILE, "w") as f:
        f.write(response.text)
    log.info("Saved %s substations to %s", state, SUBSTATIONS_FILE)

    return response.json()


# ── Quick summary ───────────────────────────────────────────────────────────

def queue_summary(df: pd.DataFrame) -> None:
    """Print a quick sanity-check summary of the loaded queue."""
    print(f"\n{'='*50}")
    print(f"  ERCOT Interconnection Queue Summary")
    print(f"{'='*50}")
    print(f"  Total active projects : {len(df):,}")
    print(f"  Total capacity (MW)   : {df['capacity_mw'].sum():,.0f}")
    print(f"\n  Capacity by fuel type:")
    by_fuel = (
        df.groupby("fuel_type")["capacity_mw"]
        .sum()
        .sort_values(ascending=False)
    )
    for fuel, mw in by_fuel.items():
        print(f"    {fuel:<20} {mw:>10,.0f} MW")
    if "study_phase" in df.columns:
        print(f"\n  Projects by study phase:")
        for phase, count in df["study_phase"].value_counts().items():
            print(f"    {str(phase):<30} {count:>5}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    df = load_queue(force_refresh=True)
    queue_summary(df)
