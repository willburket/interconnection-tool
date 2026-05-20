# src/cluster.py — geographic clustering of interconnection queue projects

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN
import logging

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from config import CLUSTER_RADIUS_MILES, CLUSTER_MIN_PROJECTS

log = logging.getLogger(__name__)

EARTH_RADIUS_MILES = 3956.0


def cluster_projects(
    df: pd.DataFrame,
    radius_miles: float = CLUSTER_RADIUS_MILES,
    min_projects: int = CLUSTER_MIN_PROJECTS,
    lat_col: str = "latitude",
    lon_col: str = "longitude",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Group queue projects by geographic proximity using DBSCAN.
    Mirrors how ERCOT groups projects into cluster study batches.

    Returns:
        df_labeled  — original df with 'cluster' column added (-1 = noise)
        cluster_summary — one row per cluster with aggregate stats
    """
    coords_df = df.dropna(subset=[lat_col, lon_col]).copy()

    if len(coords_df) == 0:
        log.warning("No rows with valid coordinates — returning empty clusters")
        return df.assign(cluster=-1), pd.DataFrame()

    coords_rad = np.radians(coords_df[[lat_col, lon_col]].values)
    eps_rad    = radius_miles / EARTH_RADIUS_MILES

    clustering = DBSCAN(
        eps=eps_rad,
        min_samples=min_projects,
        algorithm="ball_tree",
        metric="haversine",
        n_jobs=-1,
    ).fit(coords_rad)

    coords_df = coords_df.copy()
    coords_df["cluster"] = clustering.labels_

    # Merge cluster labels back onto original df
    df = df.copy()
    df["cluster"] = -1
    df.loc[coords_df.index, "cluster"] = coords_df["cluster"]

    # Build cluster summary
    clustered = coords_df[coords_df["cluster"] >= 0]
    if clustered.empty:
        log.info("No clusters found with radius=%.0f mi, min_projects=%d", radius_miles, min_projects)
        return df, pd.DataFrame()

    agg = {
        "project_count":      ("project_name", "count"),
        "total_capacity_mw":  ("capacity_mw",  "sum"),
        "avg_capacity_mw":    ("capacity_mw",  "mean"),
        "center_lat":         (lat_col,         "mean"),
        "center_lon":         (lon_col,         "mean"),
    }
    if "fuel_type" in clustered.columns:
        agg["fuel_types"] = ("fuel_type", lambda x: ", ".join(sorted(x.unique())))
    if "days_in_queue" in clustered.columns:
        agg["avg_days_in_queue"] = ("days_in_queue", "mean")

    cluster_summary = (
        clustered.groupby("cluster")
        .agg(**agg)
        .sort_values("total_capacity_mw", ascending=False)
        .reset_index()
    )

    noise_count = (df["cluster"] == -1).sum()
    log.info(
        "Found %d clusters covering %d projects (%.0f MW total). "
        "%d noise points.",
        len(cluster_summary),
        clustered["project_id"].nunique() if "project_id" in clustered.columns else len(clustered),
        clustered["capacity_mw"].sum(),
        noise_count,
    )

    return df, cluster_summary


def top_congestion_clusters(cluster_summary: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """
    Return the N clusters with the most total queued capacity.
    These are the areas most likely to trigger expensive network upgrades.
    """
    return cluster_summary.nlargest(n, "total_capacity_mw")


def projects_in_cluster(df: pd.DataFrame, cluster_id: int) -> pd.DataFrame:
    """Return all projects belonging to a given cluster."""
    return df[df["cluster"] == cluster_id].copy()
