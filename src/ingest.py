# src/ingest.py — download and clean the CAISO interconnection queue

import json
import requests
import pandas as pd
from io import BytesIO
from pathlib import Path
import logging

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

def download_queue() -> pd.DataFrame:
    """
    Pull the CAISO Generator Interconnection Queue Excel report.
    Saves raw file to data/raw/ and returns a raw DataFrame.
    """
    log.info("Downloading CAISO queue from %s", CAISO_QUEUE_URL)
    response = requests.get(CAISO_QUEUE_URL, timeout=30)
    response.raise_for_status()

    Path(RAW_DATA_DIR).mkdir(parents=True, exist_ok=True)
    with open(QUEUE_RAW_FILE, "wb") as f:
        f.write(response.content)
    log.info("Saved raw file to %s", QUEUE_RAW_FILE)

    # Try skipping 0–2 header rows; stop when we find recognizable columns
    for skip in (2, 1, 0):
        try:
            df = pd.read_excel(BytesIO(response.content), skiprows=skip)
            cols_lower = " ".join(str(c).lower() for c in df.columns)
            if any(k in cols_lower for k in ["capacity", "fuel", "project"]):
                log.info("Parsed with skiprows=%d (%d rows)", skip, len(df))
                return df
        except Exception:
            continue

    return pd.read_excel(BytesIO(response.content))


def clean_queue(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize columns, cast types, remove withdrawn projects, and cache to parquet.
    """
    # Normalize headers
    df.columns = df.columns.str.strip().str.lower()

    # Rename to internal names
    rename = {k: v for k, v in COLUMN_MAP.items() if k in df.columns}
    df = df.rename(columns=rename)

    # Ensure required columns exist
    for col in ["project_id", "project_name", "fuel_type", "capacity_mw",
                "substation_name", "status", "study_phase"]:
        if col not in df.columns:
            df[col] = None

    # Remove withdrawn / cancelled
    df = df[~df["status"].astype(str).str.strip().str.lower().eq(WITHDRAWN_LABEL)]

    # Cast capacity
    df["capacity_mw"] = pd.to_numeric(df["capacity_mw"], errors="coerce")
    df = df.dropna(subset=["capacity_mw"])

    if "application_date" in df.columns:
        df["application_date"] = pd.to_datetime(df["application_date"], errors="coerce")
    if "voltage_kv" in df.columns:
        df["voltage_kv"] = pd.to_numeric(df["voltage_kv"], errors="coerce")

    # Normalize and remap fuel type labels
    df["fuel_type"] = df["fuel_type"].astype(str).str.strip().str.title()
    df["fuel_type"] = df["fuel_type"].replace(FUEL_TYPE_MAP)

    # Days in queue
    if "application_date" in df.columns:
        df["days_in_queue"] = (pd.Timestamp.today() - df["application_date"]).dt.days

    Path(PROCESSED_DATA_DIR).mkdir(parents=True, exist_ok=True)
    df.to_parquet(QUEUE_CLEAN_FILE, index=False)
    log.info("Saved cleaned queue (%d rows) to %s", len(df), QUEUE_CLEAN_FILE)
    return df


def load_queue(force_refresh: bool = False) -> pd.DataFrame:
    """Load cleaned queue from cache, or re-download if needed."""
    if not force_refresh and Path(QUEUE_CLEAN_FILE).exists():
        log.info("Loading queue from cache")
        return pd.read_parquet(QUEUE_CLEAN_FILE)
    return clean_queue(download_queue())

# def load_queue(force_refresh: bool = False) -> pd.DataFrame:
#     """Load queue from local Excel file."""
#     excel_path = Path("publicqueuereport.xlsx")
#     if not excel_path.exists():
#         raise FileNotFoundError(
#             "publicqueuereport.xlsx not found — place it in the project root directory."
#         )
#     for skip in (2, 1, 0):
#         try:
#             df = pd.read_excel(excel_path, skiprows=skip)
#             cols_lower = " ".join(str(c).lower() for c in df.columns)
#             if any(k in cols_lower for k in ["capacity", "fuel", "project"]):
#                 return clean_queue(df)
#         except Exception:
#             continue
#     return clean_queue(pd.read_excel(excel_path))


# ── Substation download ──────────────────────────────────────────────────────

def download_substations() -> dict:
    """
    Pull California substation locations from HIFLD public API.
    Paginates in chunks of 1000 (HIFLD's max page size).
    """
    where     = f"STATE='{HIFLD_STATE}'"
    PAGE_SIZE = 1000
    all_features = []
    offset = 0

    log.info("Fetching HIFLD substations for CA")

    while True:
        params = {
            "where":             where,
            "outFields":         "NAME,CITY,STATE,LATITUDE,LONGITUDE,MIN_VOLT,MAX_VOLT,LINES",
            "f":                 "geojson",
            "resultRecordCount": PAGE_SIZE,
            "resultOffset":      offset,
        }
        response = requests.get(HIFLD_SUBSTATIONS_URL, params=params, timeout=30)
        response.raise_for_status()

        page     = response.json()
        features = page.get("features", [])
        all_features.extend(features)
        log.info("Fetched %d substations (offset %d)", len(features), offset)

        if len(features) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    geojson = {"type": "FeatureCollection", "features": all_features}

    Path(GEO_DATA_DIR).mkdir(parents=True, exist_ok=True)
    with open(SUBSTATIONS_FILE, "w") as f:
        json.dump(geojson, f)

    log.info("Saved %d total substations to %s", len(all_features), SUBSTATIONS_FILE)
    return geojson


# ── Summary ──────────────────────────────────────────────────────────────────

def queue_summary(df: pd.DataFrame) -> None:
    print(f"\n{'='*55}")
    print(f"  CAISO Interconnection Queue Summary")
    print(f"{'='*55}")
    print(f"  Total active projects : {len(df):,}")
    print(f"  Total capacity (MW)   : {df['capacity_mw'].sum():,.0f}")
    print(f"\n  Capacity by fuel type:")
    for fuel, mw in df.groupby("fuel_type")["capacity_mw"].sum().sort_values(ascending=False).items():
        print(f"    {fuel:<25} {mw:>10,.0f} MW")
    if "study_phase" in df.columns:
        print(f"\n  Projects by study phase:")
        for phase, count in df["study_phase"].value_counts().items():
            print(f"    {str(phase):<35} {count:>5}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    df = load_queue(force_refresh=True)
    queue_summary(df)
