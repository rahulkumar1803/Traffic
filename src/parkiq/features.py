"""
features.py – temporal, spatial, severity and repeat-offender features.
"""
import logging

import numpy as np
import pandas as pd

from parkiq.config import TIME_BUCKETS, HEAVY_VEHICLE_TYPES, SEVERITY_WEIGHTS

logger = logging.getLogger(__name__)


def _time_bucket(hour: int) -> str:
    for name, (start, end) in TIME_BUCKETS.items():
        if start <= hour < end:
            return name
    return "night"


def add_temporal(df: pd.DataFrame) -> pd.DataFrame:
    """Add hour, day_of_week, is_weekend, time_bucket, month, date."""
    dt = df["created_datetime"]
    df = df.copy()
    df["hour"]        = dt.dt.hour
    df["day_of_week"] = dt.dt.dayofweek          # 0=Mon … 6=Sun
    df["is_weekend"]  = df["day_of_week"].isin([5, 6])
    df["time_bucket"] = df["hour"].apply(_time_bucket)
    df["month"]       = dt.dt.month
    df["date"]        = dt.dt.date
    return df


def add_severity(df: pd.DataFrame) -> pd.DataFrame:
    """severity_weight already set in clean.py; add normalised version."""
    df = df.copy()
    max_w = max(SEVERITY_WEIGHTS.values())
    df["severity_norm"] = df["severity_weight"] / max_w
    return df


def add_vehicle_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add is_heavy_vehicle flag."""
    df = df.copy()
    vtype = df["vehicle_type"].str.upper().fillna("")
    df["is_heavy_vehicle"] = vtype.isin(HEAVY_VEHICLE_TYPES)
    return df


def add_repeat_offender(df: pd.DataFrame) -> pd.DataFrame:
    """
    Flag vehicles that appear more than once in the dataset.
    Also compute per-vehicle violation count.
    """
    df = df.copy()
    counts = df["vehicle_number"].value_counts()
    df["vehicle_count"]     = df["vehicle_number"].map(counts)
    df["is_repeat_offender"] = df["vehicle_count"] > 1
    return df


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Apply all feature engineering steps."""
    logger.info("Building features…")
    df = add_temporal(df)
    df = add_severity(df)
    df = add_vehicle_features(df)
    df = add_repeat_offender(df)
    logger.info("Features done: %d cols", len(df.columns))
    return df
