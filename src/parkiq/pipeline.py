"""
pipeline.py – Orchestrate raw CSV → all processed Parquet artefacts.
Run once via scripts/build_artifacts.py before starting the Streamlit app.
"""
import logging
import time

import pandas as pd

from parkiq.config import (
    PROCESSED_DIR,
    CLEAN_PARQUET, H3_AGG_PARQUET, HOTSPOT_PARQUET,
    CIS_PARQUET, FORECAST_PARQUET, ROUTE_PARQUET,
    STAFFING_PARQUET,
)
from parkiq import io_load, clean, features, geo, impact, cluster, forecast as fc, routing, staffing, alerts

logger = logging.getLogger(__name__)


def run(skip_osm: bool = True, force: bool = False) -> dict[str, int]:
    """
    Run the full pipeline.

    Parameters
    ----------
    skip_osm : skip OSMnx road-class fetch (saves ~5 min if offline)
    force    : re-run all stages even if artefacts already exist

    Returns dict mapping artefact name → row count.
    """
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    counts: dict[str, int] = {}

    # ── 1. Load raw ───────────────────────────────────────────────────────
    logger.info("=== Stage 1: Load raw ===")
    df_raw = io_load.load_raw()

    # ── 2. Clean ──────────────────────────────────────────────────────────
    logger.info("=== Stage 2: Clean ===")
    if not force and CLEAN_PARQUET.exists():
        logger.info("  Skipping – %s exists", CLEAN_PARQUET)
        df_clean = pd.read_parquet(CLEAN_PARQUET)
    else:
        df_clean = clean.clean(df_raw, parking_only=False)  # keep all; parking flag is column
        # Feature engineering
        df_clean = features.build_features(df_clean)
        # Geo features
        df_clean = geo.build_geo_features(df_clean, skip_osm=skip_osm)
        df_clean.to_parquet(CLEAN_PARQUET, index=False)
        logger.info("  Saved %s (%d rows)", CLEAN_PARQUET.name, len(df_clean))
    counts["clean_events"] = len(df_clean)

    # Filter to parking only for downstream stages
    df = df_clean[df_clean["is_parking"]].copy() if "is_parking" in df_clean.columns else df_clean

    # ── 3. H3 aggregates + CIS ────────────────────────────────────────────
    logger.info("=== Stage 3: H3 aggregates + CIS ===")
    if not force and CIS_PARQUET.exists():
        logger.info("  Skipping – %s exists", CIS_PARQUET)
        cis_df = pd.read_parquet(CIS_PARQUET)
        agg_df = pd.read_parquet(H3_AGG_PARQUET) if H3_AGG_PARQUET.exists() else cis_df
    else:
        agg_df = impact.compute_h3_aggregates(df)
        agg_df.to_parquet(H3_AGG_PARQUET, index=False)
        cis_df = impact.compute_cis(agg_df)
        cis_df.to_parquet(CIS_PARQUET, index=False)
        logger.info("  CIS table: %d rows", len(cis_df))
    counts["h3_aggregates"] = len(agg_df)
    counts["cis_table"]     = len(cis_df)

    # ── 4. Hotspot detection ──────────────────────────────────────────────
    logger.info("=== Stage 4: Hotspot detection ===")
    if not force and HOTSPOT_PARQUET.exists():
        logger.info("  Skipping – %s exists", HOTSPOT_PARQUET)
        hotspots = pd.read_parquet(HOTSPOT_PARQUET)
    else:
        hotspots = cluster.detect_hotspots(df, cis_df)
        hotspots.to_parquet(HOTSPOT_PARQUET, index=False)
        logger.info("  %d hotspots detected", len(hotspots))
    counts["hotspots"] = len(hotspots)

    # ── 5. Station centroids ──────────────────────────────────────────────
    logger.info("=== Stage 5: Station centroids ===")
    centroids = alerts.build_station_centroids(df_clean)
    counts["stations"] = len(centroids)

    # ── 6. Forecast ───────────────────────────────────────────────────────
    logger.info("=== Stage 6: Forecast ===")
    if not force and FORECAST_PARQUET.exists():
        logger.info("  Skipping – %s exists", FORECAST_PARQUET)
        forecast_df = pd.read_parquet(FORECAST_PARQUET)
    else:
        model, panel = fc.train_forecast(df)
        forecast_df = fc.make_forecast(model, panel)
        forecast_df.to_parquet(FORECAST_PARQUET, index=False)
        logger.info("  Forecast rows: %d", len(forecast_df))
    counts["forecast"] = len(forecast_df)

    # ── 7. Staffing ───────────────────────────────────────────────────────
    logger.info("=== Stage 7: Staffing ===")
    if not force and STAFFING_PARQUET.exists():
        logger.info("  Skipping – %s exists", STAFFING_PARQUET)
        staffing_df = pd.read_parquet(STAFFING_PARQUET)
    else:
        staffing_df = staffing.build_staffing_table(hotspots, forecast_df)
        staffing_df.to_parquet(STAFFING_PARQUET, index=False)
        logger.info("  Staffing rows: %d", len(staffing_df))
    counts["staffing"] = len(staffing_df)

    # ── 8. Patrol route ───────────────────────────────────────────────────
    logger.info("=== Stage 8: Patrol route ===")
    if not force and ROUTE_PARQUET.exists():
        logger.info("  Skipping – %s exists", ROUTE_PARQUET)
        route_df = pd.read_parquet(ROUTE_PARQUET)
    else:
        route_df = routing.plan_patrol(staffing_df)
        route_df.to_parquet(ROUTE_PARQUET, index=False)
        logger.info("  Route stops: %d", len(route_df))
    counts["patrol_route"] = len(route_df)

    # ── 9. Alert seed ─────────────────────────────────────────────────────
    logger.info("=== Stage 9: Alert seed ===")
    alert_df = alerts.build_alerts(staffing_df, centroids, forecast_df)
    alerts.save_alert_state(alert_df)
    counts["alerts"] = len(alert_df)

    elapsed = time.time() - t0
    logger.info("Pipeline complete in %.1f s. Artefact row counts: %s", elapsed, counts)
    return counts
