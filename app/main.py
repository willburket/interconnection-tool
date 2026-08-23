# app/main.py — CAISO Interconnection Analyzer
# Run with: streamlit run app/main.py

import streamlit as st
import pandas as pd
import sys
from pathlib import Path
import psutil

sys.path.append(str(Path(__file__).parent.parent))
from src.ingest import load_data, queue_summary, load_caiso_queue, load_nyiso_queue, normalize_columns
from src.cluster import cluster_projects, top_congestion_clusters
from src.network import (
    build_graph, annotate_queue_capacity,
    load_graph, save_graph, graph_exists, offshore_wind_candidates,
)
from src.screening import screen_interconnection_point, batch_screen, RiskLevel
from src.visualize import queue_map, screening_map
from config import FUEL_COLORS, RENEWABLE_FUELS

# def handle_iso_change():
#     # iso = st.session_state.iso_selector
#     # st.session_state.df = load_data(iso)
#     # # any other reset logic, e.g. clearing a selected POI
#     # st.session_state.selected_poi = None
#     st.session_state["queue_data"] = None  # clear stale data from the previous ISO
#     st.session_state["selected_report"] = None

def load_caiso_queue_report():
    df = pd.DataFrame()
    df = load_caiso_queue()

    # df = df.rename(columns={
    #     "net mws to grid": "capacity_mw",
    #     "fuel-1": "fuel_type",
    #     "mw-1": "fuel_mw",
    # })
    # df["fuel_type"] = df["fuel_type"].str.title()  # e.g. "Solar", "Battery", "Wind Turbine"
    return df
 
 
def load_nyiso_queue_report():
    df = pd.DataFrame()
    df = load_nyiso_queue()

    # df = df.rename(columns={
    #     "sp (mw)": "capacity_mw",
    #     "type/ fuel": "fuel_type",
    #     "sp (mw)": "fuel_mw",
    # })
    # df["fuel_type"] = df["fuel_type"].str.title()  # e.g. "Solar", "Battery", "Wind Turbine"
    return df
 
 
def handle_iso_change():
    # Runs before rerun — clear stale state tied to the previous ISO
    st.session_state["queue_data"] = None
 
 
def load_queue_data(iso: str) -> pd.DataFrame:
    if iso == "CAISO":
        return load_caiso_queue_report()
    elif iso == "NYISO":
        return load_nyiso_queue_report()
    else:
        raise ValueError(f"Unknown ISO: {iso}")

st.set_page_config(
    page_title="CAISO & NYISO Interconnection Analyzer",
    page_icon="⚡",
    layout="wide",
)

# ── Sidebar ──────────────────────────────────────────────────────────────────
# iso = 'CAISO'
iso = st.sidebar.selectbox("Select ISO", ["CAISO", "NYISO"], on_change= handle_iso_change, key="iso_selector")
st.sidebar.title(f"{iso} Interconnection Queue Analysis")
st.sidebar.caption("Multi-ISO Queue & Network Screening Tool")
st.sidebar.header("Data Source")
page    = st.sidebar.radio("Navigate", ["Queue Overview", "Geographic Clusters", "Screening Tool"])

# refresh = st.sidebar.button("🔄 Refresh Queue Data")

st.sidebar.divider()
st.sidebar.caption("Data sources: CAISO & NYISO public queue report · HIFLD substations")



# ── Data loading ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner="Loading queue...")
def get_queue(force: bool = False, iso: str = iso):

    return load_data(iso)

@st.cache_resource(show_spinner="Building network graph...")
def get_graph():
    if graph_exists():
        return load_graph()
    G = build_graph()
    save_graph(G)
    return G

df = get_queue()

G  = get_graph()
G  = annotate_queue_capacity(G, df)
# Load (or reuse cached) data for the current ISO
if st.session_state.get("queue_data") is None:
    st.session_state["queue_data"] = load_queue_data(iso)
 
df = st.session_state["queue_data"]



# ═══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — Queue Overview
# ═══════════════════════════════════════════════════════════════════════════════
if page == "Queue Overview":
    if df.empty:
        st.warning(f"No queue data loaded for {iso} yet.")
    else:

        # cols = COLUMN_MAP[iso]
        

        st.title(f"{iso} Interconnection Queue")
        st.caption(f"{len(df):,} active projects · source: CAISO/NYISO Generator Interconnection Queue Report")


        # KPI row
        # c1, c2, c3, c4 = st.columns(4)
        # c1.metric("Total Projects",      f"{len(df):,}")
        # c2.metric("Total Capacity (MW)", f"{df['net mws to grid'].sum():,.0f}")
        # c3.metric(
        #     "Solar + Storage + Wind (MW)",
        #     f"{df[df['fuel-1'].isin(['Solar','Battery','Wind Turbine'])]['mw-1'].sum():,.0f}"       
        # )
        # c4.metric(
        #     "Avg Days in Queue",
        #     f"{df['days_in_queue'].mean():.0f}" if "days_in_queue" in df.columns else "N/A"
        # )

        # NORMALIZE COLUMNS HERE
        df = normalize_columns(df, iso)
        print("CURRENT DF COLUMNS")
        print(df.columns)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Projects", f"{len(df):,}")
        c2.metric("Total Capacity (MW)", f"{df['capacity_mw'].sum():,.0f}")
        c3.metric(
            "Solar + Storage + Wind (MW)",
            f"{df[df['fuel_type'].isin(RENEWABLE_FUELS)]['fuel_mw'].sum():,.0f}"
        )
        c4.metric(
            "Avg Days in Queue",
            f"{df['days_in_queue'].mean():.0f}" if "days_in_queue" in df.columns else "N/A"
        )
        st.divider()

        col_l, col_r = st.columns(2)



        with col_l:
            st.subheader("Capacity by fuel type (MW)")
            fuel_summary = (
                df.groupby("fuel_type")["capacity_mw"]
                .sum().sort_values(ascending=False)
                .reset_index().rename(columns={"capacity_mw": "Total MW"})
            )
            st.bar_chart(fuel_summary.set_index("fuel_type"))

        with col_r:
            st.subheader("Projects by study phase")
            if "study_phase" in df.columns:
                phase_counts = df["study_phase"].value_counts().reset_index()
                phase_counts.columns = ["Study Phase", "Count"]
                st.dataframe(phase_counts, width="content", hide_index=True)

        # Offshore wind spotlight
        # offshore = df[df["fuel-1"] == "wind turbine"]
        # if not offshore.empty:
        #     st.divider()
        #     st.subheader(f"🌊 Offshore wind — {len(offshore)} projects, {offshore['net mws to grid'].sum():,.0f} MW")
        #     st.dataframe(
        #         offshore[["name", "net mws to grid", "station or transmission line",
        #                 "study_phase", "days_in_queue"]].sort_values("net mws to grid", ascending=False),
        #         width=True, hide_index=True,
        #     )

    st.divider()
    st.subheader("Full queue")
    st.dataframe(df.sort_values("capacity_mw", ascending=False), width="content", hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE 2 — Geographic Clusters
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "Geographic Clusters":
    # st.write(f"RAM available: {psutil.virtual_memory().available / 1e9:.1f} GB")

    # matched = df.dropna(subset=["latitude", "longitude"])
    # st.write(f"Rows going into DBSCAN: {len(matched):,}")


    st.title("Geographic Cluster Analysis")
    st.caption(
            "Projects within 15 miles of each other are grouped — "
            "mirroring how CAISO batches projects into cluster studies."
        )
    
    if "latitude" not in df.columns or "longitude" not in df.columns:
        st.warning(
            "CAISO's public queue file doesn't include lat/lon coordinates. "
            "You'll need to geocode substation names against the HIFLD substation file. "
            "See README for instructions."
        )
        st.stop()
    try:

        df_clustered, cluster_summary = cluster_projects(df)

    except Exception as e:
        import traceback
        st.error(f"Error: {e}")
        st.code(traceback.format_exc())
        st.stop()
    
    if cluster_summary.empty:
        st.info("No clusters found with current radius settings.")
        st.stop()

    st.subheader(f"Top congestion clusters ({len(cluster_summary)} total)")
    st.dataframe(top_congestion_clusters(cluster_summary), width='content', hide_index=True)

    # Offshore wind POI callout
    # ow_nodes = offshore_wind_candidates(G)
    # if ow_nodes:
    #     st.info(
    #         f"🌊 **{len(ow_nodes)} coastal substation(s)** identified as potential "
    #         f"offshore wind POIs: {', '.join(ow_nodes[:5])}"
    #         + (" and more." if len(ow_nodes) > 5 else ".")
    #     )

    selected = st.selectbox(
        "Drill into cluster",
        options=cluster_summary["cluster"].tolist(),
        format_func=lambda x: (
            f"Cluster {x} — "
            f"{cluster_summary[cluster_summary['cluster']==x]['total_capacity_mw'].values[0]:,.0f} MW | "
            f"{cluster_summary[cluster_summary['cluster']==x]['project_count'].values[0]} projects"
        ),
    )
    st.dataframe(
        df_clustered[df_clustered["cluster"] == selected],
        width='content', hide_index=True,
    )

    print("drilled in successfully")


    


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE 3 — Screening Tool
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "Screening Tool":
    st.title("Interconnection Screening Tool")
    st.caption(
        "Preliminary thermal and radial screening for a new interconnection request. "
        "First-pass filter only — not a substitute for a full power flow study."
    )

    # st.info(
    #     "**CAISO note:** CAISO uses a cluster-based queue process. Projects are studied "
    #     "together in batches — your cost allocation depends heavily on what else is in "
    #     "your cluster. Use the Clusters page to check what's already queued near your POI."
    # )

    with st.form("screening_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            substation = st.text_input("Point of Interconnection (substation name)", placeholder="e.g. DAVIS CREEK")
        with c2:
            project_mw = st.number_input("Project capacity (MW)", min_value=1.0, max_value=5000.0, value=200.0)
        with c3:
            fuel_type = st.selectbox("Fuel type", list(FUEL_COLORS.keys()))

        compare_mode = st.checkbox("Compare multiple POIs")
        alt_subs = []
        if compare_mode:
            alt_input = st.text_area(
                "Additional substations to compare (one per line)",
                placeholder="DIABLO CANYON 500KV\nMOSSLANDING 230KV",
            )
            alt_subs = [s.strip() for s in alt_input.strip().splitlines() if s.strip()]

        submitted = st.form_submit_button("Run Screening")

    if submitted and substation:
        results = batch_screen([substation] + alt_subs, project_mw, G, fuel_type)



        RISK_COLOR = {"LOW": "green", "MEDIUM": "orange", "HIGH": "red", "UNKNOWN": "gray"}

        for result in results:
            rc = RISK_COLOR[result.risk_level.value]
            with st.expander(f"**{result.substation}** — :{rc}[{result.risk_level.value} RISK]", expanded=True):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Thermal limit (MW)",  f"{result.thermal_limit_mw:,.0f}")
                c2.metric("Existing queue (MW)", f"{result.existing_queue_mw:,.0f}")
                c3.metric("Total proposed (MW)", f"{result.total_proposed_mw:,.0f}")
                c4.metric("Utilization",         f"{result.utilization_pct:.1f}%")

                if result.flags:
                    st.subheader("⚠ Flags")
                    for flag in result.flags:
                        if any(kw in flag.upper() for kw in ["HIGH", "OFFSHORE", "RADIAL"]):
                            st.error(flag)
                        else:
                            st.warning(flag)

                if result.recommendations:
                    st.subheader("✓ Recommendations")
                    for rec in result.recommendations:
                        st.info(rec)

        if len(results) > 1:
            st.divider()
            st.subheader("POI comparison")
            comparison = pd.DataFrame([r.to_dict() for r in results])[
                ["substation", "risk_level", "utilization_pct",
                 "thermal_limit_mw", "existing_queue_mw", "transmission_paths"]
            ]
            st.dataframe(comparison, width="content", hide_index=True)
