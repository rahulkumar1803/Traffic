"""
pages/6_Alert_Center.py – Control-room alert feed + per-station notification cards.
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

from parkiq.config import ALERT_STATE_PARQUET, STATION_PARQUET
from parkiq.alerts import load_alert_state, save_alert_state, tier_emoji
from components.notifications import alert_badge, alert_card, station_alerts
from components.maps import base_view
from components.icons import render_heading

st.set_page_config(page_title="Alert Center · ParkIQ", layout="wide")
render_heading("Station Alert Center", "alert", level=1)


@st.cache_data(ttl=10)
def _load_alerts():
    return load_alert_state()

@st.cache_data
def _load_stations():
    return pd.read_parquet(STATION_PARQUET) if STATION_PARQUET.exists() else pd.DataFrame()

alert_df  = _load_alerts()
stations_df = _load_stations()

if alert_df.empty:
    st.info("No alerts yet. Run `python scripts/build_artifacts.py` to seed alerts.")
    st.stop()

# ── Role / station scope ──────────────────────────────────────────────────
st.sidebar.header("Officer Role")
all_stations = ["All"] + sorted(alert_df["police_station"].dropna().unique().tolist())
sel_station = st.sidebar.selectbox("Station (login scope)", all_stations)
sel_status  = st.sidebar.multiselect("Status", ["Open","Acknowledged","Resolved"],
                                      default=["Open","Acknowledged"])

# ── Badge ─────────────────────────────────────────────────────────────────
alert_badge(alert_df)

# ── Scoped view ───────────────────────────────────────────────────────────
scoped = station_alerts(alert_df, sel_station)
if sel_status:
    scoped = scoped[scoped["status"].isin(sel_status)]

# ── Summary metrics ───────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total alerts",  len(scoped))
c2.metric("🔴 Critical",   (scoped["tier"] == "Critical").sum())
c3.metric("🟠 Warning",    (scoped["tier"] == "Warning").sum())
c4.metric("🟢 Watch",      (scoped["tier"] == "Watch").sum())

# ── Sort controls ─────────────────────────────────────────────────────────
sort_by = st.selectbox("Sort by", ["cis (high→low)", "tier", "created_at"], index=0)
if sort_by == "cis (high→low)":
    scoped = scoped.sort_values("cis", ascending=False)
elif sort_by == "tier":
    tier_order = {"Critical": 0, "Warning": 1, "Watch": 2}
    scoped = scoped.iloc[scoped["tier"].map(tier_order).argsort()]
else:
    scoped = scoped.sort_values("created_at", ascending=False)

# ── Alert cards ───────────────────────────────────────────────────────────
st.markdown("---")
st.subheader(f"Alerts — {sel_station}")

# We need mutable state_df for ack/resolve buttons
state_df = load_alert_state()

for _, row in scoped.iterrows():
    state_df = alert_card(row, state_df)

# ── Map: alert locations ──────────────────────────────────────────────────
st.markdown("---")
st.subheader("Alert Locations")
map_data = scoped[["lat","lon","hotspot_name","cis","tier"]].dropna()
if not map_data.empty:
    color_map = {"Critical": [255, 32, 32, 200], "Warning": [255, 153, 0, 200], "Watch": [0, 204, 68, 200]}
    map_data = map_data.copy()
    map_data["color"] = map_data["tier"].map(color_map).apply(lambda x: x if isinstance(x, list) else [100,100,100,150])
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=map_data,
        get_position="[lon, lat]",
        get_fill_color="color",
        get_radius=300,
        pickable=True,
    )
    st.pydeck_chart(
        pdk.Deck(layers=[layer], initial_view_state=base_view(),
                 map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
                 tooltip={"text": "{tier}: {hotspot_name}\nCIS: {cis}"}),
        width='stretch',
    )

# ── Pre-warning section ───────────────────────────────────────────────────
pre = scoped[scoped.get("is_prewarning", pd.Series(False, index=scoped.index)).fillna(False)]
if not pre.empty:
    st.warning(f"⚠️ {len(pre)} pre-warning(s) issued based on forecast – deploy early!")
    st.dataframe(pre[["hotspot_name","tier","cis","recommended_window","police_station"]],
                 width='stretch')
