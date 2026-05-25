# app/main.py — Streamlit dashboard (multi-ISO version)
# Run with: streamlit run app/main.py

import streamlit as st
import pandas as pd
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from src.ingest import load_queue, download_substations, queue_summary
from src.cluster import cluster_projects, top_congestion_clusters
from src.network import (
    build_graph_from_substations, annotate_queue_capacity,
    load_graph, save_graph, graph_exists, caiso_offshore_wind_nodes,
)
from src.screening import screen_interconnection_point, batch_screen, RiskLevel
from src.visualize import queue_map, screening_map
from config import ISO, ISO_CONFIG, FUEL_COLORS

st.set_page_config(
    page_title="Interconnection Queue Analyzer",
    page_icon="⚡",
    layout="wide",
)

# ── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.title("⚡ Interconnection Analyzer")

iso_labels = {iso: cfg["label"] for iso, cfg in ISO_CONFIG.items()}
selected_label = st.sidebar.selectbox(
    "Grid operator (ISO)",
    options=list(iso_labels.values()),
)
active_iso = next(iso for iso, label in iso_labels.items() if label == selected_label)

st.sidebar.divider()

page = st.sidebar.radio(
    "Navigate",
    ["Queue Overview", "Geographic Clusters", "Screening Tool"],
)

refresh = st.sidebar.button("🔄 Refresh Queue Data")

# ISO info card in sidebar
cfg = ISO_CONFIG[active_iso]
st.sidebar.divider()
st.sidebar.caption(
    f"**{cfg['label']}**  \n"
    f"Max voltage: {cfg['max_voltage_kv']} kV  \n"
    f"State(s): {cfg['hifld_state'] or 'Multi-state'}"
)


# ── Data loading (cached per ISO) ─────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner="Loading queue...")
def get_queue(iso: ISO, force: bool = False):
    return load_queue(iso, force_refresh=force)


@st.cache_resource(show_spinner="Building network graph...")
def get_graph(iso: ISO):
    if graph_exists(iso):
        return load_graph(iso)
    G = build_graph_from_substations(iso)
    save_graph(G, iso)
    return G


df = get_queue(active_iso, force=refresh)
G  = get_graph(active_iso)
G  = annotate_queue_capacity(G, df)


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — Queue Overview
# ═══════════════════════════════════════════════════════════════════════════════
if page == "Queue Overview":
    st.title(f"{cfg['label']} Interconnection Queue")
    st.caption(f"{len(df):,} active projects | source: {active_iso.value} public queue report")

    # CAISO-specific callout
    if active_iso == ISO.CAISO:
        st.info(
            "🌊 **California queue note:** CAISO currently has over 100 GW of projects "
            "in queue — more than double the state's existing generating capacity. "
            "Offshore wind and large-scale storage are the fastest-growing categories.",
            icon="ℹ️",
        )

    # KPI row
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Projects",       f"{len(df):,}")
    col2.metric("Total Capacity (MW)",  f"{df['capacity_mw'].sum():,.0f}")

    solar_storage = df[df["fuel_type"].isin(["Solar", "Battery", "Offshore Wind"])]["capacity_mw"].sum()
    col3.metric("Solar + Storage + Offshore (MW)", f"{solar_storage:,.0f}")
    col4.metric(
        "Avg Days in Queue",
        f"{df['days_in_queue'].mean():.0f}" if "days_in_queue" in df.columns else "N/A"
    )

    st.divider()

    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Capacity by fuel type (MW)")
        fuel_summary = (
            df.groupby("fuel_type")["capacity_mw"]
            .sum()
            .sort_values(ascending=False)
            .reset_index()
            .rename(columns={"capacity_mw": "Total MW"})
        )
        st.bar_chart(fuel_summary.set_index("fuel_type"))

    with col_r:
        st.subheader("Projects by study phase")
        if "study_phase" in df.columns:
            phase_counts = df["study_phase"].value_counts().reset_index()
            phase_counts.columns = ["Study Phase", "Count"]
            st.dataframe(phase_counts, use_container_width=True, hide_index=True)
        else:
            st.info("Study phase data not available.")

    # CAISO offshore wind spotlight
    if active_iso == ISO.CAISO:
        offshore = df[df["fuel_type"] == "Offshore Wind"]
        if not offshore.empty:
            st.divider()
            st.subheader(f"🌊 Offshore wind spotlight — {len(offshore)} projects, "
                         f"{offshore['capacity_mw'].sum():,.0f} MW")
            st.dataframe(
                offshore[["project_name", "capacity_mw", "substation_name",
                           "study_phase", "days_in_queue"]].sort_values("capacity_mw", ascending=False),
                use_container_width=True,
                hide_index=True,
            )

    st.divider()
    st.subheader("Full queue")
    st.dataframe(
        df.sort_values("capacity_mw", ascending=False),
        use_container_width=True,
        hide_index=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE 2 — Geographic Clusters
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "Geographic Clusters":
    st.title("Geographic Cluster Analysis")
    st.caption(
        f"Projects within 15 miles of each other are grouped — "
        f"mirroring how {active_iso.value} batches projects into cluster studies."
    )

    if "latitude" not in df.columns or "longitude" not in df.columns:
        st.warning(
            f"{active_iso.value}'s public queue file doesn't include lat/lon coordinates. "
            "You'll need to geocode substation names against the HIFLD substation file. "
            "See README for instructions."
        )
        st.stop()

    df_clustered, cluster_summary = cluster_projects(df)

    if cluster_summary.empty:
        st.info("No clusters found with current radius settings.")
        st.stop()

    st.subheader(f"Top congestion clusters ({len(cluster_summary)} total)")
    top = top_congestion_clusters(cluster_summary)
    st.dataframe(top, use_container_width=True, hide_index=True)

    # CAISO offshore wind POI cluster highlight
    if active_iso == ISO.CAISO:
        offshore_nodes = caiso_offshore_wind_nodes(G)
        if offshore_nodes:
            st.info(
                f"🌊 **{len(offshore_nodes)} coastal substation(s)** identified as "
                f"potential offshore wind POIs: {', '.join(offshore_nodes[:5])}"
                + (" and more." if len(offshore_nodes) > 5 else ".")
            )

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
        use_container_width=True,
        hide_index=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE 3 — Screening Tool
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "Screening Tool":
    st.title("Interconnection Screening Tool")
    st.caption(
        "Preliminary thermal and radial screening for a new interconnection request. "
        "First-pass filter only — not a substitute for a full power flow study."
    )

    # ISO-specific guidance
    if active_iso == ISO.CAISO:
        st.info(
            "**CAISO note:** CAISO uses a cluster-based queue process. "
            "Projects are studied together in batches — your cost allocation depends "
            "heavily on what else is in your cluster. Use the Clusters page to check "
            "what's already queued near your POI."
        )
    elif active_iso == ISO.ERCOT:
        st.info(
            "**ERCOT note:** ERCOT uses a first-come, first-served queue. "
            "Queue position affects your Network Upgrade cost responsibility directly."
        )
    elif active_iso == ISO.PJM:
        st.info(
            "**PJM note:** PJM is transitioning to a cluster-based process under "
            "FERC Order 2023. Confirm the current cycle dates before submitting."
        )

    with st.form("screening_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            substation = st.text_input(
                "Point of Interconnection (substation name)",
                placeholder="e.g. MORRO BAY 230KV" if active_iso == ISO.CAISO else "e.g. TRAVIS COUNTY 138KV"
            )
        with col2:
            project_mw = st.number_input(
                "Project capacity (MW)", min_value=1.0, max_value=5000.0, value=200.0
            )
        with col3:
            fuel_options = list(FUEL_COLORS.keys())
            fuel_type = st.selectbox("Fuel type", fuel_options)

        compare_mode = st.checkbox("Compare multiple POIs")
        alt_subs = []
        if compare_mode:
            alt_input = st.text_area(
                "Additional substations to compare (one per line)",
                placeholder="DIABLO CANYON 500KV\nMOSSLANDING 230KV" if active_iso == ISO.CAISO
                else "WILLIAMSON COUNTY 138KV\nBURNET 69KV",
            )
            alt_subs = [s.strip() for s in alt_input.strip().splitlines() if s.strip()]

        submitted = st.form_submit_button("Run Screening")

    if submitted and substation:
        all_subs = [substation] + alt_subs
        results  = batch_screen(all_subs, project_mw, G, active_iso, fuel_type)

        RISK_COLOR = {
            "LOW":     "green",
            "MEDIUM":  "orange",
            "HIGH":    "red",
            "UNKNOWN": "gray",
        }

        for result in results:
            rc = RISK_COLOR[result.risk_level.value]
            with st.expander(
                f"**{result.substation}** — :{rc}[{result.risk_level.value} RISK]",
                expanded=True,
            ):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Thermal limit (MW)",  f"{result.thermal_limit_mw:,.0f}")
                c2.metric("Existing queue (MW)", f"{result.existing_queue_mw:,.0f}")
                c3.metric("Total proposed (MW)", f"{result.total_proposed_mw:,.0f}")
                c4.metric("Utilization",         f"{result.utilization_pct:.1f}%")

                if result.flags:
                    st.subheader("⚠ Flags")
                    for flag in result.flags:
                        # Severity-based display
                        if any(kw in flag.upper() for kw in ["HIGH", "OFFSHORE", "RADIAL"]):
                            st.error(flag)
                        else:
                            st.warning(flag)

                if result.recommendations:
                    st.subheader("✓ Recommendations")
                    for rec in result.recommendations:
                        st.info(rec)

        # Comparison table when multiple POIs screened
        if len(results) > 1:
            st.divider()
            st.subheader("POI comparison")
            comparison = pd.DataFrame([r.to_dict() for r in results])[
                ["substation", "risk_level", "utilization_pct",
                 "thermal_limit_mw", "existing_queue_mw", "transmission_paths"]
            ]
            st.dataframe(comparison, use_container_width=True, hide_index=True)
