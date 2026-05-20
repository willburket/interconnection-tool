# ERCOT Interconnection Queue Analyzer

Preliminary interconnection screening and queue analysis tool built on
real ERCOT public data. Mirrors the first-pass workflow used by
interconnection engineers when evaluating new project applications.

## What it does

- **Queue parsing** — pulls and cleans the live ERCOT Generator Interconnection
  Status Report (updated weekly)
- **Geographic clustering** — groups co-located projects using DBSCAN,
  matching how ERCOT batches projects into cluster studies
- **Network screening** — flags thermal overload risk and radial exposure
  at candidate points of interconnection
- **Interactive dashboard** — Streamlit UI with queue stats, cluster map,
  and POI screening form

## Setup

```bash
# 1. Clone and install
git clone <your-repo>
cd interconnection-tool
pip install -r requirements.txt

# 2. Download HIFLD substation data (one-time)
python -c "from src.ingest import download_substations; download_substations('TX')"

# 3. Pull the ERCOT queue
python src/ingest.py

# 4. Launch the dashboard
streamlit run app/main.py
```

## Data sources

| Source | What it provides | URL |
|--------|-----------------|-----|
| ERCOT Interconnection Queue | Active project list, capacity, POI, study status | https://www.ercot.com/gridinfo/resource |
| HIFLD Electric Substations | Substation locations, voltage, line count | https://hifld-geoplatform.opendata.arcgis.com |

Both are public and require no API key.

## Project structure

```
interconnection-tool/
├── config.py              # all constants and thresholds
├── requirements.txt
├── data/
│   ├── raw/               # downloaded ERCOT xlsx files
│   ├── processed/         # cleaned parquet + cached graph
│   └── geo/               # HIFLD GeoJSON files
├── src/
│   ├── ingest.py          # download + clean ERCOT queue
│   ├── network.py         # NetworkX graph from HIFLD substations
│   ├── cluster.py         # DBSCAN geographic clustering
│   ├── screening.py       # thermal + radial screening logic
│   └── visualize.py       # Folium map output
├── app/
│   ├── main.py            # Streamlit entry point
│   └── pages/             # additional Streamlit pages
└── tests/
    ├── test_ingest.py
    └── test_screening.py
```

## Limitations

ERCOT's public queue file does not include lat/lon coordinates for projects —
it gives the substation (POI) name. To enable the geographic clustering page,
you need to geocode those substation names against the HIFLD substation dataset.
A fuzzy-match script for this is in `src/network.py::get_substation_info`.

The thermal limits used in screening are estimated from voltage class, not
actual line ratings. For production use, replace `_estimate_thermal_limit()`
in `src/network.py` with real ratings from your network model or ERCOT's
published facility data.

## Resume description

> Built an interconnection queue analysis and preliminary screening tool using
> live ERCOT public data. Automated queue ingestion and normalization,
> geographic clustering of co-located projects using DBSCAN (mirroring ERCOT's
> cluster study batching methodology), and first-pass thermal/radial screening
> for candidate points of interconnection. Deployed as an interactive Streamlit
> dashboard.
