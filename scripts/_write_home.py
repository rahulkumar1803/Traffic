# Helper: writes app/Home.py with correct UTF-8 content
from pathlib import Path

HOME = Path(__file__).resolve().parent.parent / "app" / "Home.py"

content = """\
# -*- coding: utf-8 -*-
\"\"\"
app/Home.py - ParkIQ command-centre dashboard.
KPIs, alert snapshot, summary charts, static mini heatmap, nav cards.
The full interactive map with filters/replay lives on Page 1.
\"\"\"
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "app"))

import streamlit as st
import pandas as pd
import plotly.express as px
import pydeck as pdk

from parkiq.config import (
    CLEAN_PARQUET, CIS_PARQUET, HOTSPOT_PARQUET, ALERT_STATE_PARQUET,
)
from components.kpi import kpi_row, build_kpis
from components.maps import heatmap_layer, base_view
from components.notifications import alert_badge

st.set_page_config(
    page_title="ParkIQ \u2013 Bengaluru Parking Intelligence",
    page_icon="\U0001f6a6",
    layout="wide",
    initial_sidebar_state="collapsed",
)


@st.cache_data(show_spinner="Loading dashboard...")
def load_data():
    out = {}
    for name, path in [
        ("clean",    CLEAN_PARQUET),
        ("cis",      CIS_PARQUET),
        ("hotspots", HOTSPOT_PARQUET),
        ("alerts",   ALERT_STATE_PARQUET),
    ]:
        out[name] = pd.read_parquet(path) if path.exists() else pd.DataFrame()
    return out


data     = load_data()
df       = data["clean"]
cis_df   = data["cis"]
hotspots = data["hotspots"]
alert_df = data["alerts"]

if df.empty:
    st.error("Artefacts not found. Run `python scripts/build_artifacts.py` first.")
    st.stop()

# ── Header ──────────────────────────────────────────────────────────────────
st.markdown("## \U0001f6a6 ParkIQ \u2014 Bengaluru Parking Intelligence")
st.caption(
    f"Dataset: **{len(df):,}** parking violations"
    f" \u00b7 **Nov 2023 \u2013 Apr 2024**"
    f" \u00b7 **{df['police_station'].nunique() if 'police_station' in df.columns else '?'}** stations"
    f" \u00b7 **{len(hotspots)}** hotspots detected"
)
alert_badge(alert_df)
st.markdown("---")

# ── KPI row ─────────────────────────────────────────────────────────────────
kpis = build_kpis(df, hotspots, cis_df)
kpi_row(kpis)
st.markdown("---")

# ── Two summary charts side-by-side ─────────────────────────────────────────
left, right = st.columns(2)

with left:
    st.subheader("\U0001f3c6 Top 10 Stations by Peak CIS")
    if not hotspots.empty and "police_station" in hotspots.columns:
        top_st = (
            hotspots.groupby("police_station")["max_cis"]
            .max().nlargest(10).reset_index()
        )
        fig = px.bar(
            top_st, x="max_cis", y="police_station",
            orientation="h", color="max_cis",
            color_continuous_scale="Reds",
            labels={"max_cis": "Peak CIS", "police_station": ""},
        )
        fig.update_layout(
            showlegend=False, coloraxis_showscale=False,
            margin=dict(l=0, r=10, t=10, b=0),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, width="stretch")

with right:
    st.subheader("\u23f0 Violations by Hour of Day")
    if "hour" in df.columns:
        peak_buckets = {"morning_peak", "evening_peak"}
        hc = df.groupby(["hour", "time_bucket"]).size().reset_index(name="count")
        hc["Period"] = hc["time_bucket"].apply(
            lambda b: "Peak" if b in peak_buckets else "Off-peak"
        )
        fig2 = px.bar(
            hc, x="hour", y="count",
            color="Period",
            color_discrete_map={"Peak": "#ff4b4b", "Off-peak": "#5c9bd6"},
            labels={"count": "Violations", "hour": "Hour of day"},
        )
        fig2.update_layout(
            margin=dict(l=0, r=0, t=10, b=0),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig2, width="stretch")

st.markdown("---")

# ── Alert snapshot (left) + Top 5 hotspots table (right) ────────────────────
col_a, col_b = st.columns([1, 2])

with col_a:
    st.subheader("\U0001f6a8 Live Alert Snapshot")
    if not alert_df.empty:
        open_alerts = (
            alert_df[alert_df["status"] == "Open"]
            if "status" in alert_df.columns else alert_df
        )
        tier_counts = (
            open_alerts["tier"].value_counts()
            if "tier" in open_alerts.columns else pd.Series(dtype=int)
        )
        for tier, emoji, color in [
            ("Critical", "\U0001f534", "#ff2020"),
            ("Warning",  "\U0001f7e0", "#ff9900"),
            ("Watch",    "\U0001f7e2", "#00cc44"),
        ]:
            cnt = int(tier_counts.get(tier, 0))
            st.markdown(
                f"<div style='padding:10px;margin:4px 0;border-radius:8px;"
                f"background:{color}22;border-left:4px solid {color}'>"
                f"{emoji} <b>{tier}</b> \u2014 {cnt} open alert{'s' if cnt != 1 else ''}</div>",
                unsafe_allow_html=True,
            )
        st.caption(
            f"Total open: {len(open_alerts)} \u00b7 "
            "Go to **\U0001f6a8 Alert Center** for full view"
        )
    else:
        st.info("No alerts seeded yet.")

with col_b:
    st.subheader("\U0001f525 Top 5 Impact Zones")
    if not hotspots.empty:
        show_cols = [c for c in [
            "hotspot_name", "police_station", "junction_name",
            "count", "max_cis", "top_violation", "officers_needed",
        ] if c in hotspots.columns]
        top5 = hotspots.nlargest(5, "max_cis")[show_cols].reset_index(drop=True)
        top5.index += 1
        st.dataframe(top5, width="stretch")

st.markdown("---")

# ── Static mini heatmap (no controls) ───────────────────────────────────────
st.subheader("\U0001f5fa\ufe0f City-Wide Violation Density")
st.caption(
    "Static overview heatmap (20 k sample). "
    "Use **\U0001f4cd Live Hotspot Map** for the full interactive experience: "
    "3D CIS hexbins, hotspot polygons, filters, and live replay."
)
sample = df.sample(min(20_000, len(df)), random_state=42)
st.pydeck_chart(
    pdk.Deck(
        layers=[heatmap_layer(sample)],
        initial_view_state=base_view(),
        map_style="mapbox://styles/mapbox/dark-v10",
        tooltip=False,
    ),
    width="stretch",
)

st.markdown("---")

# ── Navigation cards ─────────────────────────────────────────────────────────
st.subheader("\U0001f4c2 Go to")
pages = [
    ("\U0001f4cd Live Hotspot Map",
     "Full interactive map \u2014 heatmap, 3D CIS hex, hotspot polygons, filters, live replay"),
    ("\U0001f4ca Congestion Impact",
     "CIS per-cell breakdown, radar charts, component weight explorer"),
    ("\U0001f52e Forecast",
     "LightGBM Poisson next-day predicted high-risk zones"),
    ("\U0001f694 Enforcement Planner",
     "OR-Tools patrol route, officer staffing, deployment schedule"),
    ("\U0001f4c8 Analytics",
     "Temporal, vehicle-type, station, weekday, repeat-offender deep-dives"),
    ("\U0001f6a8 Alert Center",
     "Watch / Warning / Critical cards, ack/resolve, station-scoped view"),
    ("\U0001f4cb Officer Briefing",
     "Generate and download shareable dispatch packet per hotspot"),
]
nav_cols = st.columns(4)
for i, (title, desc) in enumerate(pages):
    with nav_cols[i % 4]:
        st.markdown(
            f"<div style='padding:14px;border-radius:10px;"
            f"background:#1e2130;border:1px solid #2e3250;margin-bottom:10px'>"
            f"<b>{title}</b><br/>"
            f"<small style='color:#9ab'>{desc}</small></div>",
            unsafe_allow_html=True,
        )
"""

HOME.write_text(content, encoding="utf-8")
print(f"Written {HOME} ({len(content)} chars)")
