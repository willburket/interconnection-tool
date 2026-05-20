# src/visualize.py — map output using Folium

import folium
from folium.plugins import MarkerCluster, HeatMap
import pandas as pd
import networkx as nx
import logging

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from config import MAP_CENTER, MAP_ZOOM, FUEL_COLORS
from src.screening import ScreeningResult, RiskLevel

log = logging.getLogger(__name__)

RISK_COLORS = {
    RiskLevel.LOW:     "#10B981",   # green
    RiskLevel.MEDIUM:  "#F59E0B",   # amber
    RiskLevel.HIGH:    "#EF4444",   # red
    RiskLevel.UNKNOWN: "#6B7280",   # gray
}


def queue_map(
    df: pd.DataFrame,
    cluster_df: pd.DataFrame = None,
    lat_col: str = "latitude",
    lon_col: str = "longitude",
    save_path: str = "data/processed/queue_map.html",
) -> folium.Map:
    """
    Plot all active queue projects on a map, color-coded by fuel type.
    Optionally overlay cluster boundaries.
    """
    m = folium.Map(location=MAP_CENTER, zoom_start=MAP_ZOOM, tiles="CartoDB positron")

    # Cluster marker layer to keep the map readable
    mc = MarkerCluster(name="Queue projects").add_to(m)

    plot_df = df.dropna(subset=[lat_col, lon_col])
    for _, row in plot_df.iterrows():
        fuel   = str(row.get("fuel_type", "Other"))
        color  = FUEL_COLORS.get(fuel, FUEL_COLORS["Other"])
        cap    = row.get("capacity_mw", 0)
        name   = row.get("project_name", "Unknown")
        phase  = row.get("study_phase", "")
        sub    = row.get("substation_name", "")

        popup_html = f"""
        <b>{name}</b><br>
        Fuel: {fuel}<br>
        Capacity: {cap:,.0f} MW<br>
        POI: {sub}<br>
        Study phase: {phase}
        """

        folium.CircleMarker(
            location=[row[lat_col], row[lon_col]],
            radius=max(4, min(12, cap / 100)),   # scale by MW
            color=color,
            fill=True,
            fill_opacity=0.7,
            popup=folium.Popup(popup_html, max_width=250),
            tooltip=f"{name} ({cap:.0f} MW)",
        ).add_to(mc)

    # Add heatmap layer showing capacity density
    heat_data = [
        [row[lat_col], row[lon_col], row.get("capacity_mw", 1)]
        for _, row in plot_df.iterrows()
    ]
    HeatMap(heat_data, name="Capacity density", show=False).add_to(m)

    # Cluster centroids
    if cluster_df is not None and not cluster_df.empty:
        cg = folium.FeatureGroup(name="Cluster centroids").add_to(m)
        for _, c in cluster_df.iterrows():
            folium.Marker(
                location=[c["center_lat"], c["center_lon"]],
                icon=folium.DivIcon(
                    html=f'<div style="font-size:11px;font-weight:bold;'
                         f'background:#1e293b;color:#fff;padding:2px 6px;'
                         f'border-radius:4px;white-space:nowrap;">'
                         f'{c["project_count"]} projects<br>'
                         f'{c["total_capacity_mw"]:,.0f} MW</div>'
                ),
                tooltip=f"Cluster {c['cluster']}: {c['total_capacity_mw']:,.0f} MW",
            ).add_to(cg)

    _add_legend(m)
    folium.LayerControl().add_to(m)

    m.save(save_path)
    log.info("Saved queue map to %s", save_path)
    return m


def screening_map(
    results: list[ScreeningResult],
    G: nx.Graph,
    save_path: str = "data/processed/screening_map.html",
) -> folium.Map:
    """
    Plot screening results on a map — substations colored by risk level.
    """
    m = folium.Map(location=MAP_CENTER, zoom_start=MAP_ZOOM, tiles="CartoDB positron")

    for result in results:
        node = G.nodes.get(result.substation.upper())
        if not node:
            continue

        lat, lon = node.get("lat"), node.get("lon")
        if not lat or not lon:
            continue

        color = RISK_COLORS.get(result.risk_level, "#6B7280")

        popup_html = f"""
        <b>{result.substation}</b><br>
        Risk: <b>{result.risk_level.value}</b><br>
        Proposed: {result.project_mw:,.0f} MW<br>
        Utilization: {result.utilization_pct:.1f}%<br>
        Existing queue: {result.existing_queue_mw:,.0f} MW<br>
        <hr>
        {'<br>'.join(result.flags) if result.flags else 'No flags.'}
        """

        folium.CircleMarker(
            location=[lat, lon],
            radius=14,
            color=color,
            fill=True,
            fill_opacity=0.8,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"{result.substation} — {result.risk_level.value}",
        ).add_to(m)

    m.save(save_path)
    log.info("Saved screening map to %s", save_path)
    return m


def _add_legend(m: folium.Map) -> None:
    legend_html = """
    <div style="position:fixed;bottom:30px;left:30px;z-index:1000;
                background:white;padding:10px 14px;border-radius:8px;
                border:1px solid #ccc;font-size:12px;line-height:1.8">
    <b>Fuel type</b><br>
    """ + "".join(
        f'<span style="color:{c}">&#9679;</span> {f}<br>'
        for f, c in FUEL_COLORS.items()
    ) + "</div>"
    m.get_root().html.add_child(folium.Element(legend_html))
