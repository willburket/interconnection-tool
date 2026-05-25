# Interconnection Queue Analyzer — Multi-ISO

Preliminary interconnection screening and queue analysis tool supporting
ERCOT (Texas), CAISO (California), and PJM (Mid-Atlantic/Midwest).

## What it does

- **Queue parsing** — pulls and cleans live interconnection queue reports for any supported ISO
- **Geographic clustering** — groups co-located projects using DBSCAN, mirroring ISO cluster study batching
- **Network screening** — flags thermal overload, radial exposure, and ISO-specific concerns
- **ISO-specific intelligence** — CAISO offshore wind flags, ERCOT West Texas congestion alerts, PJM capacity market reminders
- **Interactive dashboard** — Streamlit UI with ISO selector in the sidebar

## Setup

```bash
pip install -r requirements.txt

# Download substations for your target ISO (one-time per ISO)
python -c "from src.ingest import download_substations; from config import ISO; download_substations(ISO.CAISO)"
python -c "from src.ingest import download_substations; from config import ISO; download_substations(ISO.ERCOT)"

# Pull queue data
python src/ingest.py --iso CAISO
python src/ingest.py --iso ERCOT

# Launch
streamlit run app/main.py
```

## Switching ISOs

Select from the sidebar dropdown — ERCOT, CAISO, or PJM. All data is
cached per ISO so switching is instant after the first load.

## What changed from the ERCOT-only version

| File | Change |
|------|--------|
| `config.py` | ISO registry with per-ISO URLs, column maps, map centers, voltage classes |
| `src/ingest.py` | ISO parameter on all functions; CAISO fuel type normalization |
| `src/network.py` | 500kV voltage tier; CAISO offshore wind node detection |
| `src/screening.py` | ISO-specific flag logic: CAISO offshore wind, ERCOT West TX congestion, PJM capacity market |
| `app/main.py` | ISO selector in sidebar; CAISO offshore wind spotlight sections |

`cluster.py` and `visualize.py` are unchanged — the core math
doesn't care which ISO you're looking at.

## CAISO-specific notes

- CAISO queue exceeds 100 GW as of 2025 — offshore wind and storage are the biggest categories
- CAISO uses Full Capacity Deliverability Status (FCDS) vs. Energy Only (EO) — the screening tool flags this
- Offshore wind POIs are flagged with California's preferred landing zones (Humboldt Bay, Morro Bay)
- 500kV infrastructure is available at major CAISO substations — the tool flags when it's relevant

## Resume description

> Built a multi-ISO interconnection queue analysis and screening tool
> supporting ERCOT, CAISO, and PJM. Automated queue ingestion and normalization
> across ISO-specific data formats, geographic clustering of co-located projects
> (mirroring cluster study batching methodology), and preliminary thermal/radial
> screening with ISO-specific intelligence including CAISO offshore wind flagging
> and ERCOT congestion zone alerts. Deployed as an interactive Streamlit dashboard.
