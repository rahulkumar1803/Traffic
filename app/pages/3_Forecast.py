"""
pages/3_Forecast.py – Next-day hotspot forecast visualization.
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

from parkiq.config import FORECAST_PARQUET, CLEAN_PARQUET
from components.maps import base_view
from components.icons import render_heading

st.set_page_config(page_title="Forecast · ParkIQ", layout="wide")
render_heading("Next-Day Hotspot Forecast", "spark", level=1)

st.markdown(
    "LightGBM (Poisson) trained on H3 × date × time-bucket panel with "
    "lag-1d, lag-7d, rolling features, and neighbour context. "
    "Near-repeat (Hawkes-style) parking behavior is captured via the rolling window."
)


@st.cache_data
def _load():
    forecast = pd.read_parquet(FORECAST_PARQUET) if FORECAST_PARQUET.exists() else pd.DataFrame()
    clean = pd.read_parquet(CLEAN_PARQUET) if CLEAN_PARQUET.exists() else pd.DataFrame()
    
    # Create h3_r9 to junction_name mapping from clean data
    if not forecast.empty and not clean.empty and "h3_r9" in clean.columns:
        h3_map = clean[["h3_r9", "junction_name"]].drop_duplicates("h3_r9").set_index("h3_r9")["junction_name"].to_dict()
        forecast["hotspot_name"] = forecast["h3_r9"].map(h3_map).fillna("Unknown")
    else:
        forecast["hotspot_name"] = "Unknown"
    
    return forecast

forecast_df = _load()

if forecast_df.empty:
    st.warning("Forecast not available. Run `python scripts/build_artifacts.py` first.")
    st.stop()

# ── KPIs ────────────────────────────────────────────────────────────────────
pred_date = pd.to_datetime(forecast_df["date"].max()).date() if "date" in forecast_df.columns else "N/A"
top_cell  = forecast_df.iloc[0]["h3_r9"][:8] if len(forecast_df) else "N/A"
peak_pred = forecast_df["predicted_count"].max() if "predicted_count" in forecast_df.columns else 0

c1, c2, c3 = st.columns(3)
c1.metric("Forecast date",      str(pred_date))
c2.metric("Top at-risk cell",   top_cell)
c3.metric("Peak predicted count", f"{peak_pred:.1f}")

# ── Filters ─────────────────────────────────────────────────────────────────
buckets = ["All"] + sorted(forecast_df["time_bucket"].dropna().unique().tolist()) if "time_bucket" in forecast_df.columns else ["All"]
sel_bk = st.selectbox("Time bucket", buckets)

fdf = forecast_df.copy()
if sel_bk != "All":
    fdf = fdf[fdf["time_bucket"] == sel_bk]

# ── Bar chart: top cells ─────────────────────────────────────────────────────
top20 = fdf.nlargest(20, "predicted_count")
fig_bar = px.bar(top20, x="h3_r9", y="predicted_count", color="time_bucket",
                 title="Top 20 At-Risk H3 Cells (next day)",
                 labels={"predicted_count": "Predicted violations", "h3_r9": "H3 Cell"})
fig_bar.update_xaxes(tickangle=45)
st.plotly_chart(fig_bar, width='stretch')

# ── Map ─────────────────────────────────────────────────────────────────────
st.subheader("Forecast Map")
map_data = fdf[["lat", "lon", "predicted_count", "time_bucket", "hotspot_name"]].dropna(subset=["lat", "lon"]).copy()
if not map_data.empty:
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=map_data,
        get_position="[lon, lat]",
        get_radius="predicted_count * 30",
        get_fill_color="[255, 100 - predicted_count * 5, 0, 160]",
        pickable=True,
    )
    st.pydeck_chart(
        pdk.Deck(
            layers=[layer],
            initial_view_state=base_view(),
            map_style="https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json",
            tooltip={"text": "{hotspot_name}\nPredicted: {predicted_count}\nWindow: {time_bucket}"},
        ),
        width="stretch",
    )

# ── Raw table ───────────────────────────────────────────────────────────────
with st.expander("Forecast table"):
    st.dataframe(fdf.sort_values("predicted_count", ascending=False).head(100),
                 width='stretch')
