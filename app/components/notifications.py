"""
components/notifications.py – Alert notification cards and badges.
"""
import streamlit as st
import pandas as pd

from parkiq.alerts import tier_emoji, acknowledge_alert, resolve_alert, save_alert_state


def _tier_color(tier: str) -> str:
    return {"Critical": "#ff2020", "Warning": "#ff9900", "Watch": "#00cc44"}.get(tier, "#888")


def alert_badge(alert_df: pd.DataFrame) -> None:
    """Show a header badge with open alert counts per tier."""
    if alert_df.empty:
        return
    open_df = alert_df[alert_df["status"] == "Open"]
    crit  = (open_df["tier"] == "Critical").sum()
    warn  = (open_df["tier"] == "Warning").sum()
    watch = (open_df["tier"] == "Watch").sum()
    st.markdown(
        f"**Alerts:** 🔴 {crit} Critical &nbsp;|&nbsp; 🟠 {warn} Warning &nbsp;|&nbsp; 🟢 {watch} Watch",
        unsafe_allow_html=True,
    )


def alert_card(row: pd.Series, state_df: pd.DataFrame) -> pd.DataFrame:
    """Render a single alert card with Acknowledge / Resolve buttons."""
    tier   = row.get("tier", "Watch")
    color  = _tier_color(tier)
    emoji  = tier_emoji(tier)
    status = row.get("status", "Open")

    with st.container(border=True):
        c1, c2 = st.columns([5, 1])
        with c1:
            st.markdown(
                f"<span style='color:{color};font-weight:bold'>{emoji} {tier}</span> – "
                f"**{row.get('hotspot_name', 'Unknown')}**",
                unsafe_allow_html=True,
            )
            st.caption(
                f"CIS: {row.get('cis',0):.1f} | "
                f"Station: {row.get('police_station','?')} | "
                f"Officers: {row.get('officers_needed',1)} | "
                f"Window: {row.get('recommended_window','?')} | "
                f"Status: {status}"
            )
            if row.get("is_prewarning"):
                st.info("⚠️ Pre-warning: predicted peak – deploy early")
        with c2:
            aid = str(row.get("alert_id", ""))
            if status == "Open":
                if st.button("Ack", key=f"ack_{aid}"):
                    state_df = acknowledge_alert(aid, state_df)
                    save_alert_state(state_df)
                    st.rerun()
            if status in ("Open", "Acknowledged"):
                if st.button("Resolve", key=f"res_{aid}"):
                    state_df = resolve_alert(aid, state_df)
                    save_alert_state(state_df)
                    st.rerun()
    return state_df


def station_alerts(
    alert_df: pd.DataFrame,
    station: str,
) -> pd.DataFrame:
    """Return alerts scoped to a specific station."""
    if station == "All":
        return alert_df
    return alert_df[alert_df["police_station"] == station]
