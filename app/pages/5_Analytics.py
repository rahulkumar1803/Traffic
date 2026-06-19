"""
pages/5_Analytics.py – Exploratory analytics: temporal, spatial, vehicle breakdown.
"""
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "app"))

import streamlit as st
import pandas as pd
import plotly.express as px

from parkiq.config import CLEAN_PARQUET
from components.icons import render_heading

st.set_page_config(page_title="Analytics · ParkIQ", layout="wide")
render_heading("Analytics", "trend", level=1)


@st.cache_data
def _load():
    return pd.read_parquet(CLEAN_PARQUET) if CLEAN_PARQUET.exists() else pd.DataFrame()

df = _load()

if df.empty:
    st.warning("Run `python scripts/build_artifacts.py` first.")
    st.stop()

# ── Temporal ─────────────────────────────────────────────────────────────────
st.subheader("Violations by Hour of Day")
if "hour" in df.columns:
    hour_counts = df.groupby("hour").size().reset_index(name="count")
    fig_h = px.bar(hour_counts, x="hour", y="count", color="count",
                   color_continuous_scale="Reds", title="Violations by Hour")
    st.plotly_chart(fig_h, width='stretch')

col1, col2 = st.columns(2)
with col1:
    if "day_of_week" in df.columns:
        dow = df.groupby("day_of_week").size().reset_index(name="count")
        dow["day"] = dow["day_of_week"].map({0:"Mon",1:"Tue",2:"Wed",3:"Thu",4:"Fri",5:"Sat",6:"Sun"})
        fig_d = px.bar(dow, x="day", y="count", title="Violations by Day of Week",
                       color_discrete_sequence=["#636EFA"])
        st.plotly_chart(fig_d, width='stretch')
with col2:
    if "month" in df.columns:
        mon = df.groupby("month").size().reset_index(name="count")
        mon["month_name"] = mon["month"].map({11:"Nov",12:"Dec",1:"Jan",2:"Feb",3:"Mar",4:"Apr"})
        fig_m = px.line(mon, x="month_name", y="count", markers=True,
                        title="Violations by Month", color_discrete_sequence=["#EF553B"])
        st.plotly_chart(fig_m, width='stretch')

# ── Violation type breakdown ───────────────────────────────────────────────
st.subheader("Violation Type Distribution")
if "primary_violation" in df.columns:
    vt = df["primary_violation"].value_counts().reset_index()
    vt.columns = ["violation", "count"]
    fig_vt = px.pie(vt.head(10), names="violation", values="count",
                    title="Top 10 Violation Types", hole=0.35)
    st.plotly_chart(fig_vt, width='stretch')

# ── Vehicle type ──────────────────────────────────────────────────────────
col3, col4 = st.columns(2)
with col3:
    if "vehicle_type" in df.columns:
        veh = df["vehicle_type"].value_counts().head(10).reset_index()
        veh.columns = ["vehicle_type", "count"]
        fig_v = px.bar(veh, x="vehicle_type", y="count", title="Top Vehicle Types",
                       color_discrete_sequence=["#AB63FA"])
        fig_v.update_xaxes(tickangle=45)
        st.plotly_chart(fig_v, width='stretch')

with col4:
    if "police_station" in df.columns:
        ps = df["police_station"].value_counts().head(15).reset_index()
        ps.columns = ["station", "count"]
        fig_ps = px.bar(ps, x="station", y="count", title="Top 15 Police Stations by Volume",
                        color_discrete_sequence=["#00CC96"])
        fig_ps.update_xaxes(tickangle=45)
        st.plotly_chart(fig_ps, width='stretch')

# ── Repeat offenders ──────────────────────────────────────────────────────
st.subheader("Top Repeat Offenders")
if "vehicle_number" in df.columns:
    repeat = df["vehicle_number"].value_counts().head(20).reset_index()
    repeat.columns = ["vehicle_number", "violations"]
    fig_r = px.bar(repeat, x="vehicle_number", y="violations",
                   title="Top 20 Vehicles by Violation Count",
                   color="violations", color_continuous_scale="Reds")
    fig_r.update_xaxes(tickangle=45)
    st.plotly_chart(fig_r, width='stretch')

# ── Time bucket heatmap ───────────────────────────────────────────────────
st.subheader("Violations: Hour × Day Heatmap")
if "hour" in df.columns and "day_of_week" in df.columns:
    pivot = df.groupby(["day_of_week","hour"]).size().unstack(fill_value=0)
    pivot.index = [["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][i] for i in pivot.index]
    fig_hm = px.imshow(pivot, color_continuous_scale="YlOrRd",
                        title="Violation Density: Hour × Weekday",
                        labels={"x":"Hour","y":"Day","color":"Violations"})
    st.plotly_chart(fig_hm, width='stretch')
