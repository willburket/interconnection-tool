# app/main.py — Streamlit dashboard entry point
# Run with: streamlit run app/main.py

import streamlit as st
import pandas as pd
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from src.ingest import load_queue, queue_summary
from src.cluster import cluster_projects, top_congestion_clusters
from src.network import build_graph_from_substations, annotate_queue_capacity, load_graph
from src.screening import screen_interconnection_point, batch_screen, RiskLevel
from src.visualize import queue_map, screening_map
from config import SUBSTATIONS_FILE, NETWORK_GRAPH_FILE, FUEL_COLORS

st.set_page_config(
    page_title="ERCOT Interconnection Analyzer",
    page_icon="⚡",
    layout="wide",
)

# ── Sidebar ─────────────────────────────────────────────────────────────────
st.sidebar.title("⚡ Interconnection Analyzer")
st.sidebar.caption("ERCOT Queue + Network Screening Tool")

page = st.sidebar.radio(
    "Navigate",
    ["Queue Overview", "Geographic Clusters", "Screening Tool"],
)

refresh = st.sidebar.button("🔄 Refresh Queue Data")

# ── Data loading (cached) ────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner="Loading ERCOT queue...")
def get_queue(force: bool = False):
    return load_queue(force_refresh=force)

@st.cache_resource(show_spinner="Building network graph...")
def get_graph():
    graph_path = Path(NETWORK_GRAPH_FILE)
    if graph_path.exists():
        return load_graph()
    G = build_graph_from_substations(SUBSTATIONS_FILE)
    return G

df = get_queue(force=refresh)
G  = get_graph()
G  = annotate_queue_capacity(G, df)


# ═══════════════════════════════════════════════════════════════════════════
# PAGE 1 — Queue Overview
# ═══════════════════════════════════════════════════════════════════════════
if page == "Queue Overview":
    st.title("ERCOT Interconnection Queue")
    st.caption(f"Source: ERCOT Generator Interconnection Status Report | {len(df):,} active projects")

    # KPI row
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Projects",        f"{len(df):,}")
    col2.metric("Total Capacity (MW)",   f"{df['capacity_mw'].sum():,.0f}")
    col3.metric("Solar + Storage (MW)",  f"{df[df['fuel_type'].isin(['Solar','Battery'])]['capacity_mw'].sum():,.0f}")
    col4.metric("Avg Days in Queue",
                f"{df['days_in_queue'].mean():.0f}" if "days_in_queue" in df.columns else "N/A")

    st.divider()

    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.subheader("Capacity by fuel type")
        fuel_summary = (
            df.groupby("fuel_type")["capacity_mw"]
            .sum()
            .sort_values(ascending=False)
            .reset_index()
            .rename(columns={"capacity_mw": "Total MW"})
        )
        st.bar_chart(fuel_summary.set_index("fuel_type"))

    with col_right:
        st.subheader("Projects by study phase")
        if "study_phase" in df.columns:
            phase_counts = df["study_phase"].value_counts().reset_index()
            phase_counts.columns = ["Study Phase", "Count"]
            st.dataframe(phase_counts, use_container_width=True, hide_index=True)

    st.subheader("Raw queue data")
    st.dataframe(
        df.sort_values("capacity_mw", ascending=False),
        use_container_width=True,
        hide_index=True,
    )


# ═══════════════════════════════════════════════════════════════════════════
# PAGE 2 — Geographic Clusters
# ═══════════════════════════════════════════════════════════════════════════
elif page == "Geographic Clusters":
    st.title("Geographic Cluster Analysis")
    st.caption("Projects within 15 miles of each other are grouped — mirroring ERCOT's cluster study batches.")

    if "latitude" not in df.columns or "longitude" not in df.columns:
        st.warning(
            "No latitude/longitude columns found in queue data. "
            "ERCOT's public queue file doesn't include coordinates — "
            "you'll need to geocode substations using the HIFLD substation file. "
            "See README for instructions."
        )
    else:
        df_clustered, cluster_summary = cluster_projects(df)

        if not cluster_summary.empty:
            st.subheader(f"Top congestion clusters ({len(cluster_summary)} total)")
            top = top_congestion_clusters(cluster_summary, n=10)
            st.dataframe(top, use_container_width=True, hide_index=True)

            # Show projects in a selected cluster
            selected = st.selectbox(
                "Drill into cluster",
                options=cluster_summary["cluster"].tolist(),
                format_func=lambda x: f"Cluster {x} — {cluster_summary[cluster_summary['cluster']==x]['total_capacity_mw'].values[0]:,.0f} MW",
            )
            cluster_projects_df = df_clustered[df_clustered["cluster"] == selected]
            st.dataframe(cluster_projects_df, use_container_width=True, hide_index=True)
        else:
            st.info("No clusters found with current settings.")


# ═══════════════════════════════════════════════════════════════════════════
# PAGE 3 — Screening Tool
# ═══════════════════════════════════════════════════════════════════════════
elif page == "Screening Tool":
    st.title("Interconnection Screening Tool")
    st.caption(
        "Preliminary thermal and radial screening for a new interconnection request. "
        "This is a first-pass filter — not a substitute for a full ERCOT power flow study."
    )

    with st.form("screening_form"):
        col1, col2 = st.columns(2)
        with col1:
            substation = st.text_input("Point of Interconnection (substation name)", placeholder="e.g. TRAVIS COUNTY 138KV")
        with col2:
            project_mw = st.number_input("Project capacity (MW)", min_value=1.0, max_value=5000.0, value=200.0)

        compare_mode = st.checkbox("Compare multiple POIs")
        alt_subs = []
        if compare_mode:
            alt_input = st.text_area(
                "Additional substations to compare (one per line)",
                placeholder="WILLIAMSON COUNTY 138KV\nBURNET 69KV",
            )
            alt_subs = [s.strip() for s in alt_input.strip().splitlines() if s.strip()]

        submitted = st.form_submit_button("Run Screening")

    if submitted and substation:
        all_subs = [substation] + alt_subs
        results = batch_screen(all_subs, project_mw, G)

        for result in results:
            risk_color = {"LOW": "green", "MEDIUM": "orange", "HIGH": "red", "UNKNOWN": "gray"}[result.risk_level.value]

            with st.expander(f"**{result.substation}** — :{risk_color}[{result.risk_level.value} RISK]", expanded=True):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Thermal limit (MW)", f"{result.thermal_limit_mw:,.0f}")
                c2.metric("Existing queue (MW)", f"{result.existing_queue_mw:,.0f}")
                c3.metric("Total proposed (MW)", f"{result.total_proposed_mw:,.0f}")
                c4.metric("Utilization", f"{result.utilization_pct:.1f}%")

                if result.flags:
                    st.subheader("⚠ Flags")
                    for flag in result.flags:
                        st.warning(flag)
                if result.recommendations:
                    st.subheader("✓ Recommendations")
                    for rec in result.recommendations:
                        st.info(rec)
