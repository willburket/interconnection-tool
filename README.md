# CAISO Interconnection Queue Analyzer

A preliminary interconnection screening and queue analysis tool for the California ISO (CAISO), built on publicly available data. Mirrors the first-pass evaluation workflow used by interconnection engineers when assessing new generator applications.

---

## What it does

**Queue Analysis**
Pulls and cleans the live CAISO Generator Interconnection Queue report, normalizes fuel type labels across CAISO's inconsistent naming conventions, and surfaces summary stats by fuel type, study phase, and days in queue.

**Geographic Clustering**
Groups co-located projects using DBSCAN — mirroring how CAISO batches nearby projects into cluster studies with shared network upgrade cost responsibility. Identifies high-congestion zones where cumulative queued capacity exceeds local thermal headroom.

**Network Screening**
Evaluates candidate points of interconnection (POIs) against:
- Thermal utilization (flags at 70% and 90% of estimated line ratings)
- Transmission path radialness (flags weak or radial connections)
- Voltage class suitability for the proposed project size
- CAISO-specific considerations: offshore wind infrastructure gaps, FCDS vs. Energy Only deliverability status, 500 kV POI guidance, queue backlog timeline

**Interactive Dashboard**
Streamlit UI with queue stats, offshore wind spotlight, geographic cluster drill-down, and multi-POI screening with side-by-side risk comparison.

---

## Setup

```bash
# 1. Clone the repo and install dependencies
git clone https://github.com/[your-handle]/interconnection-tool.git
cd interconnection-tool
pip install -r requirements.txt

# 2. Download California substation data (one-time)
python3 -c "from src.ingest import download_substations; download_substations()"

# 3. Pull the CAISO queue
python3 src/ingest.py

# 4. Launch the dashboard
streamlit run app/main.py
```

---

## Data sources

| Source | What it provides | Access |
|--------|-----------------|--------|
| CAISO Generator Interconnection Queue | Active projects, capacity, POI, study phase | [caiso.com/generation](https://www.caiso.com/generation/Pages/GeneratingFacilities/Default.aspx) |
| HIFLD Electric Substations | Substation locations, voltage class, line count | [HIFLD Open Data](https://hifld-geoplatform.opendata.arcgis.com) |

Both are public and require no API key.

---

## Project structure

```
interconnection-tool/
├── config.py              # all constants, thresholds, and file paths
├── requirements.txt
├── .gitignore
├── data/
│   ├── raw/               # downloaded CAISO xlsx (gitignored)
│   ├── processed/         # cleaned parquet + cached graph (gitignored)
│   └── geo/               # HIFLD GeoJSON (gitignored)
├── src/
│   ├── ingest.py          # download + clean CAISO queue and HIFLD substations
│   ├── network.py         # NetworkX graph from substation data
│   ├── cluster.py         # DBSCAN geographic clustering
│   ├── screening.py       # thermal, radial, and CAISO-specific screening logic
│   └── visualize.py       # Folium map output
├── app/
│   └── main.py            # Streamlit dashboard
└── tests/
    ├── test_ingest.py
    └── test_screening.py
```

---

## CAISO-specific notes

**Queue backlog**
CAISO's interconnection queue exceeds 100 GW as of 2025 — more than double California's existing generating capacity. Solar, battery storage, and offshore wind account for the majority. Cluster study timelines have stretched to 3–5 years in recent cycles.

**Deliverability**
CAISO distinguishes between Full Capacity Deliverability Status (FCDS) and Energy Only (EO) interconnection. FCDS projects can count toward resource adequacy requirements but face higher network upgrade cost allocation. The screening tool flags this for every project.

**Offshore wind**
California has no existing offshore wind transmission infrastructure. CAISO and CPUC are actively planning coordinated transmission for offshore wind, with Humboldt Bay and Morro Bay identified as preferred landing zones. The screening tool flags offshore wind projects with current planning context.

**500 kV infrastructure**
Unlike ERCOT (which tops out at 345 kV), CAISO has significant 500 kV transmission infrastructure. Large projects (500 MW+) often benefit from 500 kV interconnection to reduce losses and avoid lower-voltage upgrade costs.

---

## Known limitations

- CAISO's public queue file does not include lat/lon coordinates. The geographic clustering page requires geocoding substation names against the HIFLD dataset. A fuzzy-match utility is available in `src/network.py::get_substation_info()`.
- Thermal limits are estimated from voltage class, not actual line ratings. Replace `_estimate_thermal_limit()` in `src/network.py` with real ratings from CAISO's published facility data for production use.
- The CAISO queue Excel URL changes periodically. If `download_queue()` fails with a 404, check [caiso.com/generation](https://www.caiso.com/generation/Pages/GeneratingFacilities/Default.aspx) for the current link and update `CAISO_QUEUE_URL` in `config.py`.

---

## Running tests

```bash
pytest tests/
```

---

## Resume description

> Built a CAISO interconnection queue analysis and preliminary screening tool using live public data. Automated queue ingestion and normalization across CAISO's inconsistent fuel type and column naming conventions, geographic clustering of co-located projects using DBSCAN (mirroring CAISO's cluster study batching methodology), and first-pass thermal and radial screening for candidate points of interconnection with CAISO-specific intelligence including offshore wind infrastructure flagging, FCDS/Energy Only deliverability callouts, and 500 kV POI guidance. Deployed as an interactive Streamlit dashboard.
