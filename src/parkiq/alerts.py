"""
alerts.py – Alert tier assignment, nearest-station routing, pre-warnings,
and acknowledge/resolve state management.
"""
import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from parkiq.config import (
    ALERT_WATCH, ALERT_WARNING, ALERT_CRITICAL,
    PREWARNING_LEAD_MIN, PROCESSED_DIR,
    ALERT_STATE_PARQUET, STATION_PARQUET,
)

logger = logging.getLogger(__name__)


# ── Tier logic ────────────────────────────────────────────────────────────

def cis_to_tier(cis: float) -> str:
    if cis >= ALERT_CRITICAL:
        return "Critical"
    if cis >= ALERT_WARNING:
        return "Warning"
    if cis >= ALERT_WATCH:
        return "Watch"
    return "None"


def tier_emoji(tier: str) -> str:
    return {"Critical": "🔴", "Warning": "🟠", "Watch": "🟢"}.get(tier, "⚪")


# ── Station centroids ─────────────────────────────────────────────────────

def build_station_centroids(df: pd.DataFrame) -> pd.DataFrame:
    """
    Derive police station centroids from the dataset (median lat/lon).
    Cache to STATION_PARQUET.
    """
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    if STATION_PARQUET.exists():
        return pd.read_parquet(STATION_PARQUET)

    centroids = (
        df.groupby("police_station")
        .agg(lat=("latitude", "median"), lon=("longitude", "median"), count=("id", "count"))
        .reset_index()
    )
    centroids.to_parquet(STATION_PARQUET, index=False)
    logger.info("Station centroids cached: %d stations", len(centroids))
    return centroids


def _haversine_m(lat1, lon1, lat2, lon2):
    R = 6_371_000
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlam = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlam / 2) ** 2
    return R * 2 * np.arcsin(np.sqrt(a))


def nearest_station(lat: float, lon: float, centroids: pd.DataFrame) -> str:
    """Return the police_station name nearest to (lat, lon)."""
    if centroids.empty:
        return "Unknown"
    dists = _haversine_m(lat, lon, centroids["lat"].values, centroids["lon"].values)
    return centroids.iloc[dists.argmin()]["police_station"]


# ── Alert table ───────────────────────────────────────────────────────────

def build_alerts(
    hotspots: pd.DataFrame,
    centroids: pd.DataFrame,
    forecast: pd.DataFrame = None,
    officers_col: bool = True,
) -> pd.DataFrame:
    """
    Generate alert rows for each hotspot that crosses Watch threshold.
    Optionally add pre-warnings from the forecast.
    """
    alerts = []
    now = datetime.now()

    for _, h in hotspots.iterrows():
        cis_val = float(h.get("max_cis", h.get("cis", 0)))
        tier = cis_to_tier(cis_val)
        if tier == "None":
            continue

        station = h.get("police_station", "Unknown")
        if station in ("Unknown", "nan", ""):
            station = nearest_station(
                h["lat_centroid"], h["lon_centroid"], centroids
            )

        alerts.append(dict(
            alert_id        = f"ALERT-{h['cluster_id']}",
            hotspot_name    = h.get("hotspot_name", f"Zone-{h['cluster_id']}"),
            cluster_id      = int(h["cluster_id"]),
            cis             = round(cis_val, 1),
            tier            = tier,
            police_station  = station,
            officers_needed = int(h.get("officers_needed", 1)),
            lat             = float(h["lat_centroid"]),
            lon             = float(h["lon_centroid"]),
            created_at      = now,
            status          = "Open",
            is_prewarning   = False,
            recommended_window = h.get("recommended_window", "evening_peak"),
        ))

    # Pre-warnings from forecast
    if forecast is not None and not forecast.empty:
        peak_rows = forecast[
            (forecast["time_bucket"].isin(["morning_peak", "evening_peak"])) &
            (forecast["predicted_count"] >= 5)
        ].head(20)
        for _, f in peak_rows.iterrows():
            deploy_by = now + timedelta(minutes=PREWARNING_LEAD_MIN)
            alerts.append(dict(
                alert_id        = f"PRE-{f['h3_r9']}",
                hotspot_name    = f"Forecast-{f['h3_r9'][:6]}",
                cluster_id      = -1,
                cis             = float(f.get("predicted_count", 0)) * 5,  # proxy
                tier            = "Watch",
                police_station  = nearest_station(f["lat"], f["lon"], centroids),
                officers_needed = 1,
                lat             = float(f["lat"]),
                lon             = float(f["lon"]),
                created_at      = now,
                status          = "Open",
                is_prewarning   = True,
                recommended_window = f["time_bucket"],
            ))

    return pd.DataFrame(alerts)


# ── State persistence ─────────────────────────────────────────────────────

def load_alert_state() -> pd.DataFrame:
    if ALERT_STATE_PARQUET.exists():
        return pd.read_parquet(ALERT_STATE_PARQUET)
    return pd.DataFrame()


def save_alert_state(df: pd.DataFrame) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(ALERT_STATE_PARQUET, index=False)


def acknowledge_alert(alert_id: str, state_df: pd.DataFrame) -> pd.DataFrame:
    if "alert_id" in state_df.columns:
        state_df.loc[state_df["alert_id"] == alert_id, "status"] = "Acknowledged"
    return state_df


def resolve_alert(alert_id: str, state_df: pd.DataFrame) -> pd.DataFrame:
    if "alert_id" in state_df.columns:
        state_df.loc[state_df["alert_id"] == alert_id, "status"] = "Resolved"
    return state_df


# ── Webhook stub (production hook) ────────────────────────────────────────

def send_notification(alert: dict) -> None:
    """
    Stub: in production replace with SMS/email/webhook.
    Currently logs the alert for judges to see the integration path.
    """
    logger.info(
        "[NOTIFY-STUB] %s %s → station=%s CIS=%.1f",
        tier_emoji(alert.get("tier", "")),
        alert.get("hotspot_name"),
        alert.get("police_station"),
        alert.get("cis", 0),
    )
