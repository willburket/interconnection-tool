# config.py — CAISO-only configuration

# ── CAISO data sources ──────────────────────────────────────────────────────
# Direct Excel download — check caiso.com/generation if this link goes stale
CAISO_QUEUE_URL = (
    "https://www.caiso.com/Documents/GeneratorInterconnectionQueueReport.xlsx"
)

# HIFLD substations REST API (public, no key needed)
HIFLD_SUBSTATIONS_URL = (
    "https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services/"
    "Electric_Substations/FeatureServer/0/query"
)
HIFLD_STATE = "CA"

# ── File paths ──────────────────────────────────────────────────────────────
RAW_DATA_DIR       = "data/raw"
PROCESSED_DATA_DIR = "data/processed"
GEO_DATA_DIR       = "data/geo"

QUEUE_RAW_FILE     = "data/raw/caiso_queue_raw.xlsx"
QUEUE_CLEAN_FILE   = "data/processed/caiso_queue_clean.parquet"
SUBSTATIONS_FILE   = "data/geo/caiso_substations.geojson"
NETWORK_GRAPH_FILE = "data/processed/caiso_network_graph.gpickle"

# ── Column mapping — CAISO queue headers → internal names ───────────────────
COLUMN_MAP = {
    "queue number":                 "project_id",
    "project name":                 "project_name",
    "fuel type":                    "fuel_type",
    "resource type":                "fuel_type",
    "capacity (mw)":                "capacity_mw",
    "county":                       "county",
    "point of interconnection":     "substation_name",
    "interconnection voltage (kv)": "voltage_kv",
    "application status":           "status",
    "application date":             "application_date",
    "study process":                "study_phase",
}
WITHDRAWN_LABEL = "withdrawn"

# ── Fuel type normalization ─────────────────────────────────────────────────
FUEL_TYPE_MAP = {
    "Photovoltaic":  "Solar",
    "Pv":            "Solar",
    "Storage":       "Battery",
    "Wind Turbine":  "Wind",
    "Combined Cycle": "Gas",
    "Simple Cycle":  "Gas",
    "Steam Turbine": "Gas",
}

# ── Screening thresholds ────────────────────────────────────────────────────
THERMAL_WARNING_PCT    = 0.70
THERMAL_HIGH_PCT       = 0.90
MIN_TRANSMISSION_PATHS = 3

# ── Clustering ──────────────────────────────────────────────────────────────
CLUSTER_RADIUS_MILES = 15
CLUSTER_MIN_PROJECTS = 3

# ── Map ─────────────────────────────────────────────────────────────────────
MAP_CENTER = [37.5, -119.5]
MAP_ZOOM   = 6

# ── Fuel type colors ────────────────────────────────────────────────────────
FUEL_COLORS = {
    "Solar":         "#F59E0B",
    "Wind":          "#3B82F6",
    "Offshore Wind": "#0EA5E9",
    "Battery":       "#10B981",
    "Gas":           "#EF4444",
    "Nuclear":       "#8B5CF6",
    "Geothermal":    "#D97706",
    "Hydro":         "#06B6D4",
    "Other":         "#6B7280",
}
