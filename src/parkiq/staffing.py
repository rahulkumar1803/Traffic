"""
staffing.py – officer-count estimation per hotspot.
Transparent workload model: every constant lives in config.py.
"""
import math
import logging

import pandas as pd

from parkiq.config import (
    BASE_HANDLE_MIN, TOW_EXTRA_MIN,
    AREA_THRESH_M2, HEAVY_VEH_THRESH,
)

logger = logging.getLogger(__name__)

# Tow-rate heuristic: fraction of incidents that need towing by violation type
_TOW_RATE: dict[str, float] = {
    "PARKING IN A MAIN ROAD":     0.40,
    "DOUBLE PARKING":             0.50,
    "PARKING NEAR ROAD CROSSING": 0.30,
    "PARKING NEAR TRAFFIC LIGHT": 0.30,
    "PARKING ON FOOTPATH":        0.25,
    "PARKING NEAR BUSTOP":        0.20,
    "NO PARKING":                 0.15,
    "WRONG PARKING":              0.10,
}

_ROAD_CLASS_ADD = {"primary": 1, "trunk": 1}  # extra officer for multi-lane arterials


def _hull_area_m2(hull_wkt: str) -> float:
    """Return approximate hull area in m² from WKT, or 0 on failure."""
    try:
        from shapely import wkt as shapely_wkt
        from shapely.ops import transform
        import pyproj
        geom = shapely_wkt.loads(hull_wkt)
        project = pyproj.Transformer.from_crs(
            "EPSG:4326", "EPSG:32643", always_xy=True
        ).transform
        geom_utm = transform(project, geom)
        return geom_utm.area
    except Exception:
        return 0.0


def estimate_officers(hotspot: pd.Series, violations_per_hour: float) -> dict:
    """
    Estimate officers needed for a single hotspot.

    Parameters
    ----------
    hotspot : row from hotspot DataFrame
    violations_per_hour : expected violations to handle per hour
                          (use predicted_count from forecast or historical rate)

    Returns dict with officers_needed (int) and rationale (str).
    """
    top_viol = str(hotspot.get("top_violation", "WRONG PARKING"))
    tow_share = _TOW_RATE.get(top_viol, 0.10)

    service_time = BASE_HANDLE_MIN + tow_share * TOW_EXTRA_MIN
    capacity_per_officer = 60 / service_time  # violations handled per officer per hour

    base_officers = max(1.0, violations_per_hour / capacity_per_officer)

    # Spread factor
    hull_wkt = str(hotspot.get("hull_wkt", ""))
    area = _hull_area_m2(hull_wkt)
    spread_factor = 1 if area <= AREA_THRESH_M2 else 2

    # Road class factor
    road = str(hotspot.get("road_class", "other")).lower()
    road_factor = 1 if road in _ROAD_CLASS_ADD else 0

    # Heavy vehicle factor
    heavy_share = float(hotspot.get("heavy_vehicle_share", 0) or 0)
    heavy_factor = 1 if heavy_share > HEAVY_VEH_THRESH else 0

    officers = int(math.ceil(base_officers)) + (spread_factor - 1) + road_factor + heavy_factor
    officers = max(1, min(6, officers))

    rationale = (
        f"~{violations_per_hour:.1f} incidents/hr; "
        f"service_time={service_time:.1f} min (tow_rate={tow_share*100:.0f}%); "
        f"spread={'large' if spread_factor==2 else 'compact'}; "
        f"road_class={road}; heavy_veh={heavy_share*100:.0f}%"
    )
    return {"officers_needed": officers, "rationale": rationale}


def build_staffing_table(
    hotspots: pd.DataFrame,
    forecast: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build full staffing table joining hotspot list with peak-hour forecast.
    Returns hotspots DataFrame with officers_needed + rationale columns.
    """
    rows = []
    peak_forecast = pd.DataFrame()
    if not forecast.empty and "time_bucket" in forecast.columns:
        peak_forecast = forecast[
            forecast["time_bucket"].isin(["morning_peak", "evening_peak"])
        ]

    for _, h in hotspots.iterrows():
        # Estimate violations per hour at this hotspot's lat/lon
        # Use forecasted count from nearest H3 cell if available
        vph = _estimate_vph(h, peak_forecast)
        result = estimate_officers(h, vph)
        rows.append(result)

    out = hotspots.copy()
    out["officers_needed"] = [r["officers_needed"] for r in rows]
    out["staffing_rationale"] = [r["rationale"] for r in rows]
    return out


def _estimate_vph(hotspot: pd.Series, peak_forecast: pd.DataFrame) -> float:
    """Return expected violations/hour for a hotspot during its peak window."""
    if peak_forecast.empty:
        # Fallback: use historical count / assumed 5 hours of peak daily
        return float(hotspot.get("count", 10)) / (5 * 30)  # per hour over ~30 days

    h3 = str(hotspot.get("h3_r9", "")) if "h3_r9" in hotspot.index else ""
    if h3 and h3 in peak_forecast["h3_r9"].values:
        pred = peak_forecast[peak_forecast["h3_r9"] == h3]["predicted_count"].mean()
        return float(pred) if not pd.isna(pred) else 2.0
    return 2.0
