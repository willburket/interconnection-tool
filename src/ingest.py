# src/ingest.py — download and clean interconnection queue data
# Supports ERCOT, CAISO, and PJM via ISO config registry

import requests
import pandas as pd
from io import BytesIO
from pathlib import Path
import logging

import sys
sys.path.append(str(Path(__file__).parent.parent))
from config import (
    ISO, ISO_CONFIG, HIFLD_SUBSTATIONS_URL,
    RAW_DATA_DIR, PROCESSED_DATA_DIR, GEO_DATA_DIR,
    QUEUE_RAW_FILE, QUEUE_CLEAN_FILE, SUBSTATIONS_FILE,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def _paths(iso: ISO) -> dict:
    """Return resolved file paths for a given ISO."""
    key = iso.value
    return {
        "raw":         f"{RAW_DATA_DIR}/{QUEUE_RAW_FILE.format(iso=key)}",
        "clean":       f"{PROCESSED_DATA_DIR}/{QUEUE_CLEAN_FILE.format(iso=key)}",
        "substations": f"{GEO_DATA_DIR}/{SUBSTATIONS_FILE.format(iso=key)}",
    }


# ── Queue download ───────────────────────────────────────────────────────────

def download_queue(iso: ISO) -> pd.DataFrame:
    """
    Pull the interconnection queue Excel file for the given ISO.
    Saves raw file to data/raw/ and returns a raw DataFrame.
    """
    cfg      = ISO_CONFIG[iso]
    paths    = _paths(iso)
    url      = cfg["queue_url"]

    log.info("[%s] Downloading queue from %s", iso.value, url)
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    Path(RAW_DATA_DIR).mkdir(parents=True, exist_ok=True)
    with open(paths["raw"], "wb") as f:
        f.write(response.content)

    # Most ISO reports have 1-3 header rows — try skipping 2, fall back to 0
    for skip in (2, 1, 0):
        try:
            df = pd.read_excel(BytesIO(response.content), skiprows=skip)
            # Sanity check: if any expected column keywords appear, we're good
            cols_lower = [str(c).lower() for c in df.columns]
            if any(k in " ".join(cols_lower) for k in ["capacity", "fuel", "project"]):
                log.info("[%s] Parsed with skiprows=%d (%d rows)", iso.value, skip, len(df))
                return df
        except Exception:
            continue

    # Last resort — return as-is
    return pd.read_excel(BytesIO(response.content))


def clean_queue(df: pd.DataFrame, iso: ISO) -> pd.DataFrame:
    """
    Normalize, cast, filter, and save the queue DataFrame for the given ISO.
    Applies the ISO-specific column map from config.
    """
    cfg              = ISO_CONFIG[iso]
    column_map       = cfg["column_map"]
    withdrawn_label  = cfg["withdrawn_label"]
    paths            = _paths(iso)

    # Normalize headers
    df.columns = df.columns.str.strip().str.lower()

    # Rename to internal names
    rename = {k: v for k, v in column_map.items() if k in df.columns}
    df = df.rename(columns=rename)

    # Ensure required columns exist even if missing in source
    for col in ["project_id", "project_name", "fuel_type", "capacity_mw",
                "substation_name", "status", "study_phase"]:
        if col not in df.columns:
            df[col] = None

    # Drop rows missing both ID and capacity
    df = df.dropna(subset=["capacity_mw"])

    # Remove withdrawn / cancelled
    if "status" in df.columns:
        df = df[~df["status"].str.strip().str.lower().eq(withdrawn_label)]

    # Cast types
    df["capacity_mw"] = pd.to_numeric(df["capacity_mw"], errors="coerce")
    df = df.dropna(subset=["capacity_mw"])

    if "application_date" in df.columns:
        df["application_date"] = pd.to_datetime(df["application_date"], errors="coerce")
    if "voltage_kv" in df.columns:
        df["voltage_kv"] = pd.to_numeric(df["voltage_kv"], errors="coerce")

    # Normalize fuel type labels
    df["fuel_type"] = df["fuel_type"].astype(str).str.strip().str.title()

    # CAISO-specific: normalize fuel type labels to common names
    if iso == ISO.CAISO:
        df["fuel_type"] = df["fuel_type"].replace({
            "Photovoltaic":        "Solar",
            "Pv":                  "Solar",
            "Storage":             "Battery",
            "Wind Turbine":        "Wind",
            "Offshore Wind":       "Offshore Wind",
            "Combined Cycle":      "Gas",
            "Simple Cycle":        "Gas",
            "Steam Turbine":       "Gas",
        })

    # Days in queue
    if "application_date" in df.columns:
        df["days_in_queue"] = (pd.Timestamp.today() - df["application_date"]).dt.days

    # Tag the ISO so downstream modules know the source
    df["iso"] = iso.value

    Path(PROCESSED_DATA_DIR).mkdir(parents=True, exist_ok=True)
    df.to_parquet(paths["clean"], index=False)
    log.info("[%s] Saved cleaned queue (%d rows) to %s", iso.value, len(df), paths["clean"])

    return df


def load_queue(iso: ISO, force_refresh: bool = False) -> pd.DataFrame:
    """
    Load cleaned queue from cache or re-download if needed.
    Main entry point for other modules.
    """
    clean_path = Path(_paths(iso)["clean"])
    if not force_refresh and clean_path.exists():
        log.info("[%s] Loading queue from cache", iso.value)
        return pd.read_parquet(clean_path)

    raw = download_queue(iso)
    return clean_queue(raw, iso)


# ── Substation download ──────────────────────────────────────────────────────

def download_substations(iso: ISO) -> dict:
    """
    Pull substation GeoJSON from HIFLD for the ISO's state(s).
    For PJM (multi-state), fetches all states in the footprint.
    """
    cfg   = ISO_CONFIG[iso]
    state = cfg["hifld_state"]
    paths = _paths(iso)

    PJM_STATES = "'PA','NJ','MD','DE','OH','IN','IL','MI','WI','VA','WV','KY','NC','DC'"

    if state:
        where = f"STATE='{state}'"
    elif iso == ISO.PJM:
        where = f"STATE IN ({PJM_STATES})"
    else:
        where = "1=1"

    log.info("[%s] Fetching HIFLD substations (%s)", iso.value, where)
    params = {
        "where":              where,
        "outFields":          "NAME,CITY,STATE,LATITUDE,LONGITUDE,MIN_VOLT,MAX_VOLT,LINES",
        "f":                  "geojson",
        "resultRecordCount":  5000,
    }
    response = requests.get(HIFLD_SUBSTATIONS_URL, params=params, timeout=30)
    response.raise_for_status()

    Path(GEO_DATA_DIR).mkdir(parents=True, exist_ok=True)
    with open(paths["substations"], "w") as f:
        f.write(response.text)

    feature_count = response.text.count('"type":"Feature"')
    log.info("[%s] Saved %d substations to %s", iso.value, feature_count, paths["substations"])

    return response.json()


# ── Summary ──────────────────────────────────────────────────────────────────

def queue_summary(df: pd.DataFrame, iso: ISO) -> None:
    iso_label = ISO_CONFIG[iso]["label"]
    print(f"\n{'='*55}")
    print(f"  {iso_label} Interconnection Queue Summary")
    print(f"{'='*55}")
    print(f"  Total active projects : {len(df):,}")
    print(f"  Total capacity (MW)   : {df['capacity_mw'].sum():,.0f}")
    print(f"\n  Capacity by fuel type:")
    by_fuel = (
        df.groupby("fuel_type")["capacity_mw"]
        .sum()
        .sort_values(ascending=False)
    )
    for fuel, mw in by_fuel.items():
        print(f"    {fuel:<25} {mw:>10,.0f} MW")
    if "study_phase" in df.columns:
        print(f"\n  Projects by study phase:")
        for phase, count in df["study_phase"].value_counts().items():
            print(f"    {str(phase):<35} {count:>5}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--iso", choices=["ERCOT", "CAISO", "PJM"], default="ERCOT")
    args = parser.parse_args()

    selected_iso = ISO[args.iso]
    df = load_queue(selected_iso, force_refresh=True)
    queue_summary(df, selected_iso)
