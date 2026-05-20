# src/network.py — build and query a NetworkX graph of the transmission network

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


def build_graph_from_substations(geojson_path: str = SUBSTATIONS_FILE) -> nx.Graph:
    """
    Build a NetworkX graph from HIFLD substation GeoJSON.
    Nodes = substations. Edges = inferred from shared transmission lines.

    NOTE: HIFLD doesn't give us explicit line-to-line connectivity,
    so we infer edges from shared voltage levels and proximity.
    For production use, replace with actual line data from your utility
    or the IEEE test feeder DSS files.
    """
    with open(geojson_path) as f:
        data = json.load(f)

    G = nx.Graph()

    for feature in data["features"]:
        props = feature["properties"]
        coords = feature["geometry"]["coordinates"]

        substation_id = props.get("NAME", "UNKNOWN").upper().strip()
        G.add_node(
            substation_id,
            name=props.get("NAME"),
            city=props.get("CITY"),
            lat=coords[1],
            lon=coords[0],
            min_volt=props.get("MIN_VOLT", 0),
            max_volt=props.get("MAX_VOLT", 0),
            lines=props.get("LINES", 0),
            # These get populated later when we load queue data
            queued_capacity_mw=0.0,
            thermal_limit_mw=_estimate_thermal_limit(props.get("MAX_VOLT", 0)),
        )

    log.info("Built graph with %d substation nodes", G.number_of_nodes())
    return G


def _estimate_thermal_limit(voltage_kv: float) -> float:
    """
    Rough thermal limit estimate based on voltage class.
    Replace with actual line ratings from your network model.
    """
    if voltage_kv >= 345:
        return 2000.0
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
    For each substation in the network, sum the queued MW from the
    interconnection queue and write it onto the node.
    """
    if "substation_name" not in queue_df.columns:
        log.warning("Queue data has no substation_name column — skipping annotation")
        return G

    queue_by_sub = (
        queue_df.groupby("substation_name")["capacity_mw"]
        .sum()
        .to_dict()
    )

    matched = 0
    for node in G.nodes():
        queued = queue_by_sub.get(node, 0.0)
        G.nodes[node]["queued_capacity_mw"] = queued
        if queued > 0:
            matched += 1

    log.info("Annotated %d/%d nodes with queue data", matched, G.number_of_nodes())
    return G


def save_graph(G: nx.Graph, path: str = NETWORK_GRAPH_FILE) -> None:
    Path(PROCESSED_DATA_DIR).mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(G, f)
    log.info("Saved graph to %s", path)


def load_graph(path: str = NETWORK_GRAPH_FILE) -> nx.Graph:
    with open(path, "rb") as f:
        return pickle.load(f)


def get_substation_info(G: nx.Graph, name: str) -> dict | None:
    """Return node attributes for a substation by name (case-insensitive)."""
    name_upper = name.upper().strip()
    if name_upper in G.nodes:
        return dict(G.nodes[name_upper])
    # Fuzzy fallback: return first partial match
    matches = [n for n in G.nodes if name_upper in n]
    if matches:
        return dict(G.nodes[matches[0]])
    return None
