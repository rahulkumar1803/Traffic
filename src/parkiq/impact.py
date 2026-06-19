"""
impact.py – Congestion Impact Score (CIS, 0-100) per H3 cell and per hotspot.

Formula
-------
CIS = 100 * ( w_density * density_n
            + w_severity * severity_n
            + w_junction * junction_n
            + w_road     * road_n
            + w_peak     * peak_conc_n
            + w_heavy    * heavy_veh_n )

Each component is min-max normalised to [0, 1].
Weights are read from config.CIS_WEIGHTS and must sum to 1.
"""
import logging

import numpy as np
import pandas as pd

from parkiq.config import CIS_WEIGHTS

logger = logging.getLogger(__name__)


def _minmax(s: pd.Series) -> pd.Series:
    lo, hi = s.min(), s.max()
    if hi == lo:
        return pd.Series(np.zeros(len(s)), index=s.index)
    return (s - lo) / (hi - lo)


def _road_class_score(series: pd.Series) -> pd.Series:
    _map = {"primary": 1.0, "secondary": 0.7, "tertiary": 0.4, "other": 0.2, "unknown": 0.1}
    return series.map(_map).fillna(0.1)


def compute_h3_aggregates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate cleaned+featured events to H3 res-9 cells.
    Returns one row per H3 cell with all fields needed for CIS.
    """
    if "h3_r9" not in df.columns or df["h3_r9"].isna().all():
        logger.warning("h3_r9 column missing – CIS will be approximate")
        df = df.copy()
        df["h3_r9"] = "unknown"

    # Peak-hour flag: fraction of violations in peak buckets
    peak_buckets = {"morning_peak", "evening_peak"}
    df = df.copy()
    df["is_peak"] = df["time_bucket"].isin(peak_buckets) if "time_bucket" in df.columns else False

    agg = df.groupby("h3_r9").agg(
        count             = ("id", "count"),
        mean_severity     = ("severity_weight", "mean"),
        near_junction_sum = ("near_junction", "sum"),
        peak_sum          = ("is_peak", "sum"),
        heavy_sum         = ("is_heavy_vehicle", "sum"),
        lat               = ("latitude", "median"),
        lon               = ("longitude", "median"),
        road_class        = ("road_class", lambda s: s.mode()[0] if len(s) else "unknown"),
        dist_junction_m   = ("dist_to_nearest_junction_m", "median"),
    ).reset_index()

    agg["near_junction_rate"] = agg["near_junction_sum"] / agg["count"]
    agg["peak_concentration"] = agg["peak_sum"] / agg["count"]
    agg["heavy_vehicle_share"] = agg["heavy_sum"] / agg["count"]

    # Junction factor: inverse distance (closer = higher)
    agg["junction_factor"] = 1 / (1 + agg["dist_junction_m"].fillna(500) / 100)

    return agg


def compute_cis(agg: pd.DataFrame) -> pd.DataFrame:
    """
    Given H3 aggregate DataFrame, compute CIS for each cell.
    Returns agg DataFrame with added `cis` column.
    """
    w = CIS_WEIGHTS
    assert abs(sum(w.values()) - 1.0) < 1e-6, "CIS weights must sum to 1"

    agg = agg.copy()
    agg["density_n"]    = _minmax(agg["count"])
    agg["severity_n"]   = _minmax(agg["mean_severity"])
    agg["junction_n"]   = _minmax(agg["junction_factor"])
    agg["road_n"]       = _minmax(_road_class_score(agg["road_class"]))
    agg["peak_conc_n"]  = _minmax(agg["peak_concentration"])
    agg["heavy_veh_n"]  = _minmax(agg["heavy_vehicle_share"])

    agg["cis"] = 100 * (
        w["density"]       * agg["density_n"]   +
        w["mean_severity"] * agg["severity_n"]  +
        w["junction"]      * agg["junction_n"]  +
        w["road_class"]    * agg["road_n"]       +
        w["peak_conc"]     * agg["peak_conc_n"] +
        w["heavy_veh"]     * agg["heavy_veh_n"]
    )
    agg["cis"] = agg["cis"].clip(0, 100).round(2)
    logger.info(
        "CIS computed: min=%.1f median=%.1f max=%.1f",
        agg["cis"].min(), agg["cis"].median(), agg["cis"].max(),
    )
    return agg
