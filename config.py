# config.py — central config for all modules

# ── ERCOT data sources ──────────────────────────────────────────────────────
ERCOT_QUEUE_URL = (
    "https://www.ercot.com/misapp/GetReports.do?reportTypeId=15933"
)

# HIFLD substations REST API (public, no key needed)
HIFLD_SUBSTATIONS_URL = (
    "https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services/"
    "Electric_Substations/FeatureServer/0/query"
)

# ── File paths ──────────────────────────────────────────────────────────────
RAW_DATA_DIR       = "data/raw"
PROCESSED_DATA_DIR = "data/processed"
GEO_DATA_DIR       = "data/geo"

QUEUE_RAW_FILE       = f"{RAW_DATA_DIR}/ercot_queue_raw.xlsx"
QUEUE_CLEAN_FILE     = f"{PROCESSED_DATA_DIR}/ercot_queue_clean.parquet"
SUBSTATIONS_FILE     = f"{GEO_DATA_DIR}/substations_tx.geojson"
NETWORK_GRAPH_FILE   = f"{PROCESSED_DATA_DIR}/network_graph.gpickle"

# ── Screening thresholds ────────────────────────────────────────────────────
THERMAL_WARNING_PCT  = 0.70   # flag at 70% utilization
THERMAL_HIGH_PCT     = 0.90   # flag as high risk at 90%
MIN_TRANSMISSION_PATHS = 3    # fewer = radial warning

# ── Clustering params ───────────────────────────────────────────────────────
CLUSTER_RADIUS_MILES = 15     # DBSCAN epsilon
CLUSTER_MIN_PROJECTS = 3      # DBSCAN min_samples

# ── Map defaults ────────────────────────────────────────────────────────────
MAP_CENTER = [31.0, -99.0]    # center of Texas
MAP_ZOOM   = 6

# ── Fuel type color mapping (for map markers) ───────────────────────────────
FUEL_COLORS = {
    "Solar":        "#F59E0B",
    "Wind":         "#3B82F6",
    "Battery":      "#10B981",
    "Gas":          "#EF4444",
    "Nuclear":      "#8B5CF6",
    "Other":        "#6B7280",
}

# ── ERCOT queue column name mappings ───────────────────────────────────────
# Map whatever ERCOT calls the column → what we use internally
COLUMN_MAP = {
    "ins #":                    "project_id",
    "project name":             "project_name",
    "fuel":                     "fuel_type",
    "ins capacity (mw)":        "capacity_mw",
    "county":                   "county",
    "poi name":                 "substation_name",
    "poi voltage (kv)":         "voltage_kv",
    "status":                   "status",
    "application date":         "application_date",
    "study phase":              "study_phase",
}
