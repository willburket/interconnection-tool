# src/network.py — build and query a NetworkX graph of the transmission network
# Updated to support ERCOT, CAISO, and PJM voltage classes

import json
import pickle
from pathlib import Path
import networkx as nx
import pandas as pd
import logging

import sys
sys.path.append(str(Path(__file__).parent.parent))
from config import (
    ISO, ISO_CONFIG,
    PROCESSED_DATA_DIR, GEO_DATA_DIR,
    SUBSTATIONS_FILE, NETWORK_GRAPH_FILE,
)

log = logging.getLogger(__name__)


def _paths(iso: ISO) -> dict:
    key = iso.value
    return {
        "substations": f"{GEO_DATA_DIR}/{SUBSTATIONS_FILE.format(iso=key)}",
        "graph":       f"{PROCESSED_DATA_DIR}/{NETWORK_GRAPH_FILE.format(iso=key)}",
    }


def build_graph_from_substations(iso: ISO) -> nx.Graph:
    """
    Build a NetworkX graph from HIFLD substation GeoJSON for the given ISO.
    Nodes = substations with thermal limit estimates per voltage class.
    """
    path = _paths(iso)["substations"]

    if not Path(path).exists():
        log.error("Substation file not found: %s — run download_substations() first", path)
        return nx.Graph()

    with open(path) as f:
        data = json.load(f)

    G = nx.Graph()

    for feature in data["features"]:
        props  = feature["properties"]
        coords = feature["geometry"]["coordinates"]
        name   = props.get("NAME", "UNKNOWN").upper().strip()

        max_volt = props.get("MAX_VOLT", 0) or 0

        G.add_node(
            name,
            name=props.get("NAME"),
            city=props.get("CITY"),
            state=props.get("STATE"),
            lat=coords[1],
            lon=coords[0],
            min_volt=props.get("MIN_VOLT", 0),
            max_volt=max_volt,
            lines=props.get("LINES", 0) or 0,
            queued_capacity_mw=0.0,
            thermal_limit_mw=_estimate_thermal_limit(max_volt, iso),
        )

    log.info("[%s] Built graph with %d substation nodes", iso.value, G.number_of_nodes())
    return G


def _estimate_thermal_limit(voltage_kv: float, iso: ISO) -> float:
    """
    Estimate thermal limit by voltage class.
    CAISO has 500kV infrastructure; ERCOT tops out at 345kV.
    Replace with actual line ratings from your network model for production use.
    """
    if voltage_kv >= 500:
        # CAISO and PJM have significant 500kV infrastructure
        return 3000.0
    elif voltage_kv >= 345:
        return 2000.0
    elif voltage_kv >= 230:
        # More common in CAISO and PJM than ERCOT
        return 1200.0
    elif voltage_kv >= 138:
        return 800.0
    elif voltage_kv >= 69:
        return 300.0
    elif voltage_kv >= 25:
        return 100.0
    else:
        return 50.0


def annotate_queue_capacity(G: nx.Graph, queue_df: pd.DataFrame) -> nx.Graph:
    """
    Sum queued MW per substation from the queue file and write onto graph nodes.
    """
    if "substation_name" not in queue_df.columns:
        log.warning("Queue data has no substation_name column — skipping annotation")
        return G

    queue_by_sub = (
        queue_df.groupby("substation_name")["capacity_mw"]
        .sum()
        .to_dict()
    )

    # Normalize substation names for matching
    queue_by_sub_upper = {k.upper().strip(): v for k, v in queue_by_sub.items()}

    matched = 0
    for node in G.nodes():
        queued = queue_by_sub_upper.get(node, 0.0)
        G.nodes[node]["queued_capacity_mw"] = queued
        if queued > 0:
            matched += 1

    log.info("Annotated %d/%d nodes with queue capacity", matched, G.number_of_nodes())
    return G


def caiso_offshore_wind_nodes(G: nx.Graph) -> list[str]:
    """
    Return substations in CAISO that are candidates for offshore wind
    interconnection (coastal counties, high voltage).
    Offshore wind is a major California policy priority — flagging these
    separately is a useful California-specific feature.
    """
    COASTAL_CITIES = {
        "EUREKA", "ARCATA", "CRESCENT CITY", "FORT BRAGG",
        "SANTA ROSA", "SAN FRANCISCO", "OAKLAND", "SAN JOSE",
        "SANTA CRUZ", "MONTEREY", "MORRO BAY", "SAN LUIS OBISPO",
        "SANTA BARBARA", "VENTURA", "LOS ANGELES", "LONG BEACH",
        "SAN DIEGO", "OXNARD", "HUMBOLDT",
    }
    candidates = []
    for node, data in G.nodes(data=True):
        city  = str(data.get("city", "")).upper()
        volt  = data.get("max_volt", 0)
        if any(c in city for c in COASTAL_CITIES) and volt >= 115:
            candidates.append(node)
    return candidates


def save_graph(G: nx.Graph, iso: ISO) -> None:
    path = _paths(iso)["graph"]
    Path(PROCESSED_DATA_DIR).mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(G, f)
    log.info("[%s] Saved graph to %s", iso.value, path)


def load_graph(iso: ISO) -> nx.Graph:
    path = _paths(iso)["graph"]
    with open(path, "rb") as f:
        return pickle.load(f)


def graph_exists(iso: ISO) -> bool:
    return Path(_paths(iso)["graph"]).exists()


def get_substation_info(G: nx.Graph, name: str) -> dict | None:
    name_upper = name.upper().strip()
    if name_upper in G.nodes:
        return dict(G.nodes[name_upper])
    matches = [n for n in G.nodes if name_upper in n]
    if matches:
        return dict(G.nodes[matches[0]])
    return None
