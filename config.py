# config.py — central config for all modules
# Multi-ISO version: supports ERCOT, CAISO, and PJM

from enum import Enum


class ISO(str, Enum):
    ERCOT = "ERCOT"
    CAISO = "CAISO"
    PJM   = "PJM"


# ── ERCOT ───────────────────────────────────────────────────────────────────
ERCOT_QUEUE_URL = (
    "https://www.ercot.com/misapp/GetReports.do?reportTypeId=15933"
)
ERCOT_COLUMN_MAP = {
    "ins #":                "project_id",
    "project name":         "project_name",
    "fuel":                 "fuel_type",
    "ins capacity (mw)":    "capacity_mw",
    "county":               "county",
    "poi name":             "substation_name",
    "poi voltage (kv)":     "voltage_kv",
    "status":               "status",
    "application date":     "application_date",
    "study phase":          "study_phase",
}
ERCOT_WITHDRAWN_LABEL = "withdrawn"
ERCOT_MAP_CENTER      = [31.0, -99.0]
ERCOT_HIFLD_STATE     = "TX"


# ── CAISO ───────────────────────────────────────────────────────────────────
# CAISO publishes their queue at:
# https://www.caiso.com/generation/Pages/GeneratingFacilities/Default.aspx
# The direct Excel download URL changes periodically — check the page above
# if the link below is stale.
CAISO_QUEUE_URL = (
    "https://www.caiso.com/Documents/GeneratorInterconnectionQueueReport.xlsx"
)
CAISO_COLUMN_MAP = {
    "queue number":                  "project_id",
    "project name":                  "project_name",
    "fuel type":                     "fuel_type",
    "capacity (mw)":                 "capacity_mw",
    "county":                        "county",
    "point of interconnection":      "substation_name",
    "interconnection voltage (kv)":  "voltage_kv",
    "application status":            "status",
    "application date":              "application_date",
    "study process":                 "study_phase",
    "resource type":                 "fuel_type",   # CAISO sometimes uses this header
}
CAISO_WITHDRAWN_LABEL = "withdrawn"
CAISO_MAP_CENTER      = [37.5, -119.5]
CAISO_HIFLD_STATE     = "CA"


# ── PJM ─────────────────────────────────────────────────────────────────────
# PJM queue data: https://www.pjm.com/planning/interconnection-projects.aspx
PJM_QUEUE_URL = (
    "https://www.pjm.com/-/media/planning/rtep-task-force/"
    "pjm-generator-queue.ashx"
)
PJM_COLUMN_MAP = {
    "queue id":              "project_id",
    "project name":          "project_name",
    "fuel":                  "fuel_type",
    "mw in service":         "capacity_mw",
    "county":                "county",
    "substation":            "substation_name",
    "voltage (kv)":          "voltage_kv",
    "queue status":          "status",
    "submission date":       "application_date",
    "study phase":           "study_phase",
}
PJM_WITHDRAWN_LABEL = "withdrawn"
PJM_MAP_CENTER      = [40.0, -77.5]
PJM_HIFLD_STATE     = None   # PJM spans multiple states — filter by region instead


# ── ISO registry — single source of truth ───────────────────────────────────
ISO_CONFIG = {
    ISO.ERCOT: {
        "queue_url":       ERCOT_QUEUE_URL,
        "column_map":      ERCOT_COLUMN_MAP,
        "withdrawn_label": ERCOT_WITHDRAWN_LABEL,
        "map_center":      ERCOT_MAP_CENTER,
        "hifld_state":     ERCOT_HIFLD_STATE,
        "max_voltage_kv":  345,
        "label":           "ERCOT (Texas)",
    },
    ISO.CAISO: {
        "queue_url":       CAISO_QUEUE_URL,
        "column_map":      CAISO_COLUMN_MAP,
        "withdrawn_label": CAISO_WITHDRAWN_LABEL,
        "map_center":      CAISO_MAP_CENTER,
        "hifld_state":     CAISO_HIFLD_STATE,
        "max_voltage_kv":  500,
        "label":           "CAISO (California)",
    },
    ISO.PJM: {
        "queue_url":       PJM_QUEUE_URL,
        "column_map":      PJM_COLUMN_MAP,
        "withdrawn_label": PJM_WITHDRAWN_LABEL,
        "map_center":      PJM_MAP_CENTER,
        "hifld_state":     PJM_HIFLD_STATE,
        "max_voltage_kv":  500,
        "label":           "PJM (Mid-Atlantic/Midwest)",
    },
}


# ── HIFLD (shared) ──────────────────────────────────────────────────────────
HIFLD_SUBSTATIONS_URL = (
    "https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services/"
    "Electric_Substations/FeatureServer/0/query"
)

# ── File paths ───────────────────────────────────────────────────────────────
RAW_DATA_DIR       = "data/raw"
PROCESSED_DATA_DIR = "data/processed"
GEO_DATA_DIR       = "data/geo"

# Per-ISO file paths — {iso} is replaced at runtime
QUEUE_RAW_FILE     = "{iso}_queue_raw.xlsx"
QUEUE_CLEAN_FILE   = "{iso}_queue_clean.parquet"
SUBSTATIONS_FILE   = "{iso}_substations.geojson"
NETWORK_GRAPH_FILE = "{iso}_network_graph.gpickle"

# ── Screening thresholds (shared) ────────────────────────────────────────────
THERMAL_WARNING_PCT    = 0.70
THERMAL_HIGH_PCT       = 0.90
MIN_TRANSMISSION_PATHS = 3

# ── Clustering params (shared) ───────────────────────────────────────────────
CLUSTER_RADIUS_MILES = 15
CLUSTER_MIN_PROJECTS = 3

# ── Map ──────────────────────────────────────────────────────────────────────
MAP_ZOOM = 6

# ── Fuel type colors (shared) ────────────────────────────────────────────────
FUEL_COLORS = {
    "Solar":          "#F59E0B",
    "Wind":           "#3B82F6",
    "Offshore Wind":  "#0EA5E9",
    "Battery":        "#10B981",
    "Gas":            "#EF4444",
    "Nuclear":        "#8B5CF6",
    "Geothermal":     "#D97706",
    "Hydro":          "#06B6D4",
    "Other":          "#6B7280",
}
