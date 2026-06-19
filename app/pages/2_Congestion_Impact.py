"""
pages/2_Congestion_Impact.py – CIS explorer: per-cell breakdown, top zones, charts.
"""
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "app"))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from parkiq.config import CIS_PARQUET, HOTSPOT_PARQUET, CIS_WEIGHTS
from components.icons import render_heading

st.set_page_config(page_title="Congestion Impact · ParkIQ", layout="wide")
render_heading("Congestion Impact Score (CIS)", "chart", level=1)

st.info(
    "CIS quantifies each hotspot's effect on traffic flow using six components. "
    "All weights are transparent and tunable in `config.py`."
)


@st.cache_data
def _load():
    cis  = pd.read_parquet(CIS_PARQUET)  if CIS_PARQUET.exists()  else pd.DataFrame()
    hs   = pd.read_parquet(HOTSPOT_PARQUET) if HOTSPOT_PARQUET.exists() else pd.DataFrame()
    return cis, hs

cis_df, hotspots = _load()

if cis_df.empty:
    st.warning("Run `python scripts/build_artifacts.py` first.")
    st.stop()

# ── CIS weight breakdown (config) ─────────────────────────────────────────
st.subheader("CIS Component Weights")
weight_df = pd.DataFrame(
    {"Component": list(CIS_WEIGHTS.keys()), "Weight": list(CIS_WEIGHTS.values())}
)
fig_w = px.bar(weight_df, x="Component", y="Weight", color="Component",
               title="CIS Formula Weights (tunable in config.py)")
st.plotly_chart(fig_w, width='stretch')

# ── Distribution ───────────────────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    fig_hist = px.histogram(cis_df, x="cis", nbins=40,
                            color_discrete_sequence=["#ff6b35"],
                            title="CIS Distribution across H3 cells")
    st.plotly_chart(fig_hist, width='stretch')

with col2:
    if not hotspots.empty and "max_cis" in hotspots.columns:
        fig_hs = px.bar(
            hotspots.sort_values("max_cis", ascending=False).head(20),
            x="hotspot_name", y="max_cis",
            color="max_cis", color_continuous_scale="Reds",
            title="Top 20 Hotspots by CIS",
        )
        fig_hs.update_xaxes(tickangle=45)
        st.plotly_chart(fig_hs, width='stretch')

# ── Per-hotspot radar chart ────────────────────────────────────────────────
if not hotspots.empty:
    st.subheader("CIS Component Breakdown — Select a Hotspot")
    radar_cols = [c for c in ["density_n","severity_n","junction_n","road_n","peak_conc_n","heavy_veh_n"]
                  if c in hotspots.columns]
    if radar_cols and "hotspot_name" in hotspots.columns:
        sel_zone = st.selectbox(
            "Hotspot",
            hotspots.sort_values("max_cis", ascending=False)["hotspot_name"].tolist(),
        )
        row = hotspots[hotspots["hotspot_name"] == sel_zone].iloc[0]
        vals = [float(row.get(c, 0)) for c in radar_cols]
        labels = [c.replace("_n", "").replace("_", " ").title() for c in radar_cols]
        fig_r = go.Figure(go.Scatterpolar(
            r=vals + [vals[0]], theta=labels + [labels[0]],
            fill="toself", fillcolor="rgba(255,80,0,0.3)",
            line=dict(color="#ff5000"),
        ))
        fig_r.update_layout(polar=dict(radialaxis=dict(range=[0, 1])),
                            title=f"CIS Breakdown: {sel_zone}")
        st.plotly_chart(fig_r, width='stretch')

# ── Raw CIS table ──────────────────────────────────────────────────────────
with st.expander("Raw CIS table (top 100 cells)"):
    cols = [c for c in ["h3_r9","count","mean_severity","junction_factor","road_class","cis"]
            if c in cis_df.columns]
    st.dataframe(cis_df[cols].sort_values("cis", ascending=False).head(100),
                 width='stretch')
