"""
cluster.py – HDBSCAN hotspot detection + convex-hull polygons.
Also exposes a per-time-window variant for temporal hotspots.
"""
import logging

import numpy as np
import pandas as pd

from parkiq.config import (
    HDBSCAN_MIN_CLUSTER_SIZE, HDBSCAN_MIN_SAMPLES,
)

logger = logging.getLogger(__name__)

# UTM zone 43N (covers Bengaluru) – EPSG:32643
_UTM_CRS = "EPSG:32643"
_WGS84   = "EPSG:4326"


def _to_utm(lat: np.ndarray, lon: np.ndarray):
    """Project WGS-84 to UTM-43N metres."""
    try:
        import pyproj
        transformer = pyproj.Transformer.from_crs("EPSG:4326", _UTM_CRS, always_xy=True)
        x, y = transformer.transform(lon, lat)
        return x, y
    except ImportError:
        # Approximate: 1 deg lat ≈ 111 km, 1 deg lon ≈ 91 km at 13° N
        x = (lon - 77.59) * 91_000
        y = (lat - 12.97) * 111_000
        return x, y


def detect_hotspots(df: pd.DataFrame, cis_table: pd.DataFrame) -> pd.DataFrame:
    """
    Run HDBSCAN on violation coordinates projected to UTM.
    Returns a DataFrame with one row per cluster (hotspot):
      cluster_id, lat_centroid, lon_centroid, count, mean_cis,
      max_cis, hull_wkt, police_station (majority vote), junction_name (majority).
    """
    try:
        import hdbscan as hdbscan_lib
    except ImportError:
        logger.warning("hdbscan not installed – using simple grid-based fallback")
        return _grid_fallback(df, cis_table)

    logger.info("Running HDBSCAN on %d points…", len(df))
    lats = df["latitude"].values
    lons = df["longitude"].values
    x, y = _to_utm(lats, lons)
    coords = np.column_stack([x, y])

    clusterer = hdbscan_lib.HDBSCAN(
        min_cluster_size=HDBSCAN_MIN_CLUSTER_SIZE,
        min_samples=HDBSCAN_MIN_SAMPLES,
        metric="euclidean",
    )
    labels = clusterer.fit_predict(coords)

    df = df.copy()
    df["cluster_id"] = labels

    noise_mask = labels == -1
    logger.info(
        "HDBSCAN: %d clusters, %d noise points",
        len(set(labels)) - (1 if -1 in labels else 0),
        noise_mask.sum(),
    )

    # Build H3-level CIS lookup
    if "h3_r9" in df.columns and not cis_table.empty:
        cis_lookup = cis_table.set_index("h3_r9")["cis"].to_dict()
        df["cell_cis"] = df["h3_r9"].map(cis_lookup).fillna(0)
    else:
        df["cell_cis"] = 0

    # Summarise clusters
    cluster_df = _summarise_clusters(df[~noise_mask])
    return cluster_df


def _summarise_clusters(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for cid, grp in df.groupby("cluster_id"):
        lats = grp["latitude"].values
        lons = grp["longitude"].values
        hull_wkt = _convex_hull_wkt(lats, lons)

        station_mode = (
            grp["police_station"].mode()[0]
            if "police_station" in grp.columns and len(grp) > 0
            else "Unknown"
        )
        junction_mode = (
            grp["junction_name"].mode()[0]
            if "junction_name" in grp.columns and len(grp) > 0
            else "No Junction"
        )
        rows.append(dict(
            cluster_id      = int(cid),
            lat_centroid    = float(lats.mean()),
            lon_centroid    = float(lons.mean()),
            count           = len(grp),
            mean_cis        = float(grp["cell_cis"].mean()),
            max_cis         = float(grp["cell_cis"].max()),
            hull_wkt        = hull_wkt,
            police_station  = station_mode,
            junction_name   = junction_mode,
            top_violation   = _top_violation(grp),
        ))
    hotspots = pd.DataFrame(rows).sort_values("max_cis", ascending=False).reset_index(drop=True)
    hotspots["hotspot_name"] = hotspots.apply(
        lambda r: _hotspot_name(r), axis=1
    )
    return hotspots


def _top_violation(grp: pd.DataFrame) -> str:
    if "primary_violation" in grp.columns:
        return grp["primary_violation"].value_counts().index[0]
    return "UNKNOWN"


def _hotspot_name(row) -> str:
    jn = str(row.get("junction_name", "No Junction"))
    if jn.upper() not in ("NO JUNCTION", "NAN", ""):
        return jn
    return f"Zone-{row['cluster_id']} ({row['police_station']})"


def _convex_hull_wkt(lats: np.ndarray, lons: np.ndarray) -> str:
    """Return WKT convex hull polygon or empty string on failure."""
    try:
        from shapely.geometry import MultiPoint
        mp = MultiPoint(list(zip(lons, lats)))
        hull = mp.convex_hull
        return hull.wkt
    except Exception:
        return ""


def _grid_fallback(df: pd.DataFrame, cis_table: pd.DataFrame) -> pd.DataFrame:
    """Simple fallback: group by H3 cell (if available) or 0.01° grid."""
    df = df.copy()
    if "h3_r9" in df.columns:
        df["cluster_id"] = df["h3_r9"].astype("category").cat.codes
    else:
        df["grid_lat"] = (df["latitude"] * 100).astype(int)
        df["grid_lon"] = (df["longitude"] * 100).astype(int)
        df["cluster_id"] = df.groupby(["grid_lat", "grid_lon"]).ngroup()
    return _summarise_clusters(df)


# ── Temporal variant ──────────────────────────────────────────────────────

def detect_hotspots_window(
    df: pd.DataFrame,
    cis_table: pd.DataFrame,
    time_bucket: str,
) -> pd.DataFrame:
    """HDBSCAN restricted to a specific time_bucket."""
    if "time_bucket" not in df.columns:
        return detect_hotspots(df, cis_table)
    subset = df[df["time_bucket"] == time_bucket]
    if len(subset) < HDBSCAN_MIN_CLUSTER_SIZE:
        return pd.DataFrame()
    result = detect_hotspots(subset, cis_table)
    result["time_bucket"] = time_bucket
    return result
