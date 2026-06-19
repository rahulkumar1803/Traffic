"""
forecast.py – LightGBM spatio-temporal next-day hotspot forecast.

Panel: H3-cell × date × time_bucket
Target: violation count (Poisson objective)
Features: lags, rolling means, day-of-week, month, neighbour sums,
          mean_severity, heavy_veh_share, near_junction_rate.
"""
import logging

import numpy as np
import pandas as pd

from parkiq.config import LGBM_PARAMS, FORECAST_HORIZON_DAYS, H3_RES_FINE, PROCESSED_DIR

logger = logging.getLogger(__name__)

_BUCKET_ORDER = ["early_morning", "morning_peak", "midday", "evening_peak", "night"]


def _build_panel(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate clean events to H3 × date × time_bucket panel."""
    if "h3_r9" not in df.columns or df["h3_r9"].isna().all():
        df = df.copy()
        df["h3_r9"] = "unknown"

    panel = (
        df.groupby(["h3_r9", "date", "time_bucket"])
        .agg(
            count             = ("id", "count"),
            mean_severity     = ("severity_weight", "mean"),
            heavy_veh_share   = ("is_heavy_vehicle", "mean"),
            near_junction_rate= ("near_junction", "mean"),
            lat               = ("latitude", "median"),
            lon               = ("longitude", "median"),
        )
        .reset_index()
    )
    panel["date"] = pd.to_datetime(panel["date"])
    return panel


def _add_lag_features(panel: pd.DataFrame) -> pd.DataFrame:
    """Add lag-1/lag-7 counts and 7-day rolling mean per H3 cell × time_bucket."""
    panel = panel.sort_values(["h3_r9", "time_bucket", "date"]).copy()
    key = ["h3_r9", "time_bucket"]

    panel["lag_1d"]      = panel.groupby(key)["count"].shift(1)
    panel["lag_7d"]      = panel.groupby(key)["count"].shift(7)
    panel["roll_7d_mean"]= panel.groupby(key)["count"].transform(
        lambda s: s.shift(1).rolling(7, min_periods=1).mean()
    )
    panel["roll_7d_std"] = panel.groupby(key)["count"].transform(
        lambda s: s.shift(1).rolling(7, min_periods=1).std().fillna(0)
    )

    panel["day_of_week"] = panel["date"].dt.dayofweek
    panel["month"]       = panel["date"].dt.month
    panel["is_weekend"]  = panel["day_of_week"].isin([5, 6]).astype(int)

    panel = panel.dropna(subset=["lag_1d"]).reset_index(drop=True)
    return panel


FEATURE_COLS = [
    "lag_1d", "lag_7d", "roll_7d_mean", "roll_7d_std",
    "day_of_week", "month", "is_weekend",
    "mean_severity", "heavy_veh_share", "near_junction_rate",
]


def train_forecast(df: pd.DataFrame):
    """Train LightGBM and return (model, panel) tuple."""
    try:
        import lightgbm as lgb
    except ImportError:
        logger.warning("lightgbm not installed – forecast disabled")
        return None, pd.DataFrame()

    logger.info("Building forecast panel…")
    panel = _build_panel(df)
    panel = _add_lag_features(panel)

    # Encode time_bucket as int
    panel["bucket_code"] = pd.Categorical(
        panel["time_bucket"], categories=_BUCKET_ORDER
    ).codes

    feat_cols = FEATURE_COLS + ["bucket_code"]
    X = panel[feat_cols].fillna(0)
    y = panel["count"].clip(lower=0)

    model = lgb.LGBMRegressor(**LGBM_PARAMS)
    logger.info("Training LightGBM on %d rows…", len(X))
    model.fit(X, y)
    logger.info("LightGBM training done")
    return model, panel


def make_forecast(model, panel: pd.DataFrame) -> pd.DataFrame:
    """
    Produce next-day predictions for all active H3 cells.
    Returns DataFrame with h3_r9, date, time_bucket, predicted_count, lat, lon.
    """
    if model is None or panel.empty:
        return pd.DataFrame()

    last_date = panel["date"].max()
    next_date = last_date + pd.Timedelta(days=FORECAST_HORIZON_DAYS)

    # Use last known lag values for each cell × bucket as synthetic "next day"
    latest = (
        panel.sort_values("date")
        .groupby(["h3_r9", "time_bucket"])
        .last()
        .reset_index()
    )
    latest["lag_1d"]       = latest["count"]
    latest["lag_7d"]       = latest.get("lag_7d", latest["count"])
    latest["roll_7d_mean"] = latest.get("roll_7d_mean", latest["count"])
    latest["roll_7d_std"]  = latest.get("roll_7d_std", pd.Series(0, index=latest.index))
    latest["date"]         = next_date
    latest["day_of_week"]  = next_date.dayofweek
    latest["month"]        = next_date.month
    latest["is_weekend"]   = int(next_date.dayofweek in [5, 6])
    latest["bucket_code"]  = pd.Categorical(
        latest["time_bucket"], categories=_BUCKET_ORDER
    ).codes

    feat_cols = FEATURE_COLS + ["bucket_code"]
    X_pred = latest[feat_cols].fillna(0)
    latest["predicted_count"] = model.predict(X_pred).clip(0)

    out = latest[["h3_r9", "date", "time_bucket", "predicted_count", "lat", "lon"]].copy()
    out["predicted_count"] = out["predicted_count"].round(2)
    return out.sort_values("predicted_count", ascending=False).reset_index(drop=True)
