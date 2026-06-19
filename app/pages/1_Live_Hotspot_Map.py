"""
pages/1_Live_Hotspot_Map.py – Interactive hotspot map with filters and 3D CIS view.
"""
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "app"))

import streamlit as st
import pandas as pd
import pydeck as pdk

from parkiq.config import CLEAN_PARQUET, HOTSPOT_PARQUET, ROUTE_PARQUET
from components.maps import (
    heatmap_layer, scatter_layer, polygon_layer, path_layer, base_view
)
from components.icons import render_heading
from stream import build_replay_ui

st.set_page_config(page_title="Live Hotspot Map · ParkIQ", layout="wide")
render_heading("Live Hotspot Map", "pin", level=1)


@st.cache_data(show_spinner=False)
def _load():
    out = {}
    for k, p in [("clean", CLEAN_PARQUET),
                 ("hotspots", HOTSPOT_PARQUET), ("route", ROUTE_PARQUET)]:
        out[k] = pd.read_parquet(p) if p.exists() else pd.DataFrame()
    return out

data = _load()
df, hotspots, route_df = data["clean"], data["hotspots"], data["route"]

if df.empty:
    st.warning("Run `python scripts/build_artifacts.py` first.")
    st.stop()

# ── Sidebar ────────────────────────────────────────────────────────────────
st.sidebar.header("Layer controls")
show_heat    = st.sidebar.checkbox("Heatmap",       True)
show_polygon = st.sidebar.checkbox("Hotspot hulls", True)
show_stream  = st.sidebar.checkbox("Live stream",   True)
show_route   = st.sidebar.checkbox("Patrol route",  False)

# Filters
st.sidebar.header("Filters")
stations = ["All"] + sorted(df["police_station"].dropna().unique().tolist())
sel_st = st.sidebar.selectbox("Station", stations, key="hs_st")
buckets = ["All"] + sorted(df["time_bucket"].dropna().unique().tolist()) if "time_bucket" in df.columns else ["All"]
sel_bk = st.sidebar.selectbox("Time of day", buckets, key="hs_bk")

fdf = df.copy()
if sel_st != "All":
    fdf = fdf[fdf["police_station"] == sel_st]
if sel_bk != "All" and "time_bucket" in fdf.columns:
    fdf = fdf[fdf["time_bucket"] == sel_bk]

replay_df = build_replay_ui(fdf)

# ── Map ────────────────────────────────────────────────────────────────────
layers = []
if show_heat    and not replay_df.empty:  layers.append(heatmap_layer(replay_df))
if show_polygon and not hotspots.empty:   layers.append(polygon_layer(hotspots))
if show_stream  and not replay_df.empty:  layers.append(scatter_layer(replay_df))
if show_route   and not route_df.empty:   layers.append(path_layer(route_df))

st.pydeck_chart(
    pdk.Deck(layers=layers, initial_view_state=base_view(),
             map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
             tooltip={"text": "{display_name}"}),
    width='stretch',
)

# ── Hotspot table ──────────────────────────────────────────────────────────
st.subheader(f"Top Hotspots ({len(hotspots)})")
if not hotspots.empty:
    cols = [c for c in ["hotspot_name","police_station","junction_name","count","max_cis","top_violation"]
            if c in hotspots.columns]
    st.dataframe(
        hotspots[cols].sort_values("max_cis", ascending=False).head(30),
        width='stretch',
    )
