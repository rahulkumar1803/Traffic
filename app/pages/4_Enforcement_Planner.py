"""
pages/4_Enforcement_Planner.py – Ranked priority zones + OR-Tools patrol route.
"""
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "app"))

import streamlit as st
import pandas as pd
import plotly.express as px
import pydeck as pdk

from parkiq.config import ROUTE_PARQUET, STAFFING_PARQUET
from components.maps import base_view
from components.icons import render_heading

st.set_page_config(page_title="Enforcement Planner · ParkIQ", layout="wide")
render_heading("Enforcement Planner", "shield", level=1)

st.markdown(
    "OR-Tools VRP optimises patrol routes across the highest-CIS hotspots. "
    f"Routes are split across **patrol teams** to minimise travel distance "
    "while covering maximum impact zones."
)


@st.cache_data
def _load():
    route   = pd.read_parquet(ROUTE_PARQUET)   if ROUTE_PARQUET.exists()   else pd.DataFrame()
    staff   = pd.read_parquet(STAFFING_PARQUET) if STAFFING_PARQUET.exists() else pd.DataFrame()
    return route, staff

route_df, staffing_df = _load()

if staffing_df.empty:
    st.warning("Run `python scripts/build_artifacts.py` first.")
    st.stop()

# ── Priority ranking ─────────────────────────────────────────────────────────
st.subheader("Priority Enforcement Zones")
cols_show = [c for c in ["hotspot_name","police_station","max_cis","officers_needed",
                          "top_violation","staffing_rationale"] if c in staffing_df.columns]
ranked = staffing_df.sort_values("max_cis", ascending=False).reset_index(drop=True)
ranked.index += 1
st.dataframe(ranked[cols_show].head(30), width='stretch')

# ── Officers needed chart ─────────────────────────────────────────────────────
if "officers_needed" in staffing_df.columns:
    fig_staff = px.bar(
        ranked.head(20), x="hotspot_name", y="officers_needed",
        color="officers_needed", color_continuous_scale="Oranges",
        title="Officers Needed – Top 20 Zones",
    )
    fig_staff.update_xaxes(tickangle=45)
    st.plotly_chart(fig_staff, width='stretch')

# ── Patrol route map ─────────────────────────────────────────────────────────
st.subheader("Optimised Patrol Route")
if not route_df.empty:
    col_t = st.selectbox("Filter by team", ["All"] + sorted(route_df["team"].unique().tolist()) if "team" in route_df.columns else ["All"])
    r = route_df if col_t == "All" else route_df[route_df["team"] == int(col_t)]

    route_path = pdk.Layer(
        "PathLayer",
        data=[{"path": r[["lon", "lat"]].dropna().values.tolist()}],
        get_path="path",
        get_color=[0, 120, 255, 200],
        width_min_pixels=3,
        pickable=False,
    )
    stop_layer = pdk.Layer(
        "ScatterplotLayer",
        data=r[["lat", "lon", "stop_order", "hotspot_name", "cis", "team"]].dropna(subset=["lat", "lon"]),
        get_position="[lon, lat]",
        get_color=[255, 165, 0, 200],
        get_radius=80,
        pickable=True,
        auto_highlight=True,
    )

    st.pydeck_chart(
        pdk.Deck(layers=[route_path, stop_layer], initial_view_state=base_view(),
                 map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
                 tooltip={"text": "Stop {stop_order}: {hotspot_name}\nCIS: {cis}\nTeam: {team}"}),
        width='stretch',
    )

    with st.expander("Route details"):
        st.dataframe(r.sort_values("stop_order"), width='stretch')
else:
    st.info("No route computed yet.")

# ── Time-of-day schedule ─────────────────────────────────────────────────────
st.subheader("Recommended Deployment Schedule")
schedule = pd.DataFrame({
    "Time window":    ["06:00–08:00","08:00–11:00","11:00–17:00","17:00–21:00","21:00–23:00"],
    "Priority zones": ["School zones, residential","Major roads, junctions (morning peak)",
                       "Market areas, footpaths","Main roads, junctions (evening peak)","Night patrol – main corridors"],
    "Recommended teams": [1, 3, 2, 3, 1],
})
st.table(schedule)
