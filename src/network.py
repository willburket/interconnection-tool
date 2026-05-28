# src/network.py — build and query a NetworkX graph of the CAISO network

import json
import pickle
from pathlib import Path
import networkx as nx
import pandas as pd
import logging

import sys
sys.path.append(str(Path(__file__).parent.parent))
from config import SUBSTATIONS_FILE, NETWORK_GRAPH_FILE, PROCESSED_DATA_DIR

log = logging.getLogger(__name__)


def build_graph() -> nx.Graph:
    """
    Build a NetworkX graph from HIFLD substation GeoJSON.
    Nodes = substations. Edges = inferred from shared voltage levels and proximity.
    """
    if not Path(SUBSTATIONS_FILE).exists():
        log.error("Substation file not found: %s — run download_substations() first", SUBSTATIONS_FILE)
        return nx.Graph()

    with open(SUBSTATIONS_FILE) as f:
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
            lat=coords[1],
            lon=coords[0],
            min_volt=props.get("MIN_VOLT", 0),
            max_volt=max_volt,
            lines=props.get("LINES", 0) or 0,
            queued_capacity_mw=0.0,
            thermal_limit_mw=_estimate_thermal_limit(max_volt),
        )

    log.info("Built graph with %d substation nodes", G.number_of_nodes())
    return G


def _estimate_thermal_limit(voltage_kv: float) -> float:
    """
    Estimate thermal limit by voltage class.
    CAISO has significant 500 kV and 230 kV infrastructure.
    Replace with actual line ratings for production use.
    """
    if voltage_kv >= 500:
        return 3000.0
    elif voltage_kv >= 345:
        return 2000.0
    elif voltage_kv >= 230:
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
    """Sum queued MW per substation from the queue and write onto graph nodes."""
    if "substation_name" not in queue_df.columns:
        log.warning("Queue data has no substation_name column — skipping annotation")
        return G

    queue_by_sub = (
        queue_df.groupby("substation_name")["capacity_mw"]
        .sum()
        .to_dict()
    )
    queue_by_sub = {k.upper().strip(): v for k, v in queue_by_sub.items()}

    matched = 0
    for node in G.nodes():
        queued = queue_by_sub.get(node, 0.0)
        G.nodes[node]["queued_capacity_mw"] = queued
        if queued > 0:
            matched += 1

    log.info("Annotated %d/%d nodes with queue capacity", matched, G.number_of_nodes())
    return G


def offshore_wind_candidates(G: nx.Graph) -> list[str]:
    """
    Return coastal substations suitable for offshore wind interconnection.
    California's preferred landing zones are Humboldt Bay and Morro Bay areas.
    """
    COASTAL_CITIES = {
        "EUREKA", "ARCATA", "CRESCENT CITY", "FORT BRAGG",
        "SANTA ROSA", "SAN FRANCISCO", "OAKLAND", "SAN JOSE",
        "SANTA CRUZ", "MONTEREY", "MORRO BAY", "SAN LUIS OBISPO",
        "SANTA BARBARA", "VENTURA", "LOS ANGELES", "LONG BEACH",
        "SAN DIEGO", "OXNARD", "HUMBOLDT",
    }
    return [
        node for node, data in G.nodes(data=True)
        if any(c in str(data.get("city", "")).upper() for c in COASTAL_CITIES)
        and data.get("max_volt", 0) >= 115
    ]


def save_graph(G: nx.Graph) -> None:
    Path(PROCESSED_DATA_DIR).mkdir(parents=True, exist_ok=True)
    with open(NETWORK_GRAPH_FILE, "wb") as f:
        pickle.dump(G, f)
    log.info("Saved graph to %s", NETWORK_GRAPH_FILE)


def load_graph() -> nx.Graph:
    with open(NETWORK_GRAPH_FILE, "rb") as f:
        return pickle.load(f)


def graph_exists() -> bool:
    return Path(NETWORK_GRAPH_FILE).exists()


def get_substation_info(G: nx.Graph, name: str) -> dict | None:
    name_upper = name.upper().strip()
    if name_upper in G.nodes:
        return dict(G.nodes[name_upper])
    matches = [n for n in G.nodes if name_upper in n]
    return dict(G.nodes[matches[0]]) if matches else None
