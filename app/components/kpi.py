"""
components/kpi.py – Streamlit KPI card helpers.
"""
import streamlit as st
import pandas as pd


def kpi_row(metrics: list[dict]) -> None:
    """
    Render a row of KPI cards.
    Each dict: {label, value, delta (opt), delta_color (opt)}.
    """
    cols = st.columns(len(metrics))
    for col, m in zip(cols, metrics):
        col.metric(
            label=m["label"],
            value=m["value"],
            delta=m.get("delta"),
            delta_color=m.get("delta_color", "normal"),
        )


def build_kpis(
    clean_df: pd.DataFrame,
    hotspots: pd.DataFrame,
    cis_df: pd.DataFrame,
) -> list[dict]:
    """Compute KPI values from artefacts."""
    total_violations = len(clean_df)
    active_hotspots  = len(hotspots)

    if not hotspots.empty and "hotspot_name" in hotspots.columns and "max_cis" in hotspots.columns:
        top_zone = hotspots.loc[hotspots["max_cis"].idxmax(), "hotspot_name"]
        top_cis  = hotspots["max_cis"].max()
    else:
        top_zone, top_cis = "N/A", 0.0

    unique_vehicles = clean_df["vehicle_number"].nunique() if "vehicle_number" in clean_df.columns else 0
    repeat_pct = 0.0
    if "is_repeat_offender" in clean_df.columns:
        repeat_pct = 100 * clean_df["is_repeat_offender"].mean()

    return [
        {"label": "Total Violations",   "value": f"{total_violations:,}"},
        {"label": "Active Hotspots",    "value": active_hotspots},
        {"label": "#1 Impact Zone",     "value": top_zone},
        {"label": "Peak CIS",           "value": f"{top_cis:.1f}"},
        {"label": "Unique Vehicles",    "value": f"{unique_vehicles:,}"},
        {"label": "Repeat Offenders",   "value": f"{repeat_pct:.1f}%"},
    ]
