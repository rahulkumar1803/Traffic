"""
geo.py – H3 binning, OSMnx road fetch/cache, junction & road-class features.
"""
import logging
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from parkiq.config import (
    H3_RES_FINE, H3_RES_COARSE,
    BBOX, EXTERNAL_DIR, OSM_GRAPH_FILE, JUNCTION_FILE,
)

logger = logging.getLogger(__name__)


# ── H3 binning ────────────────────────────────────────────────────────────

def add_h3(df: pd.DataFrame) -> pd.DataFrame:
    """Add h3_r9 and h3_r8 columns."""
    try:
        import h3
    except ImportError:
        logger.warning("h3 not installed – skipping H3 binning")
        df["h3_r9"] = None
        df["h3_r8"] = None
        return df

    df = df.copy()
    df["h3_r9"] = df.apply(
        lambda r: h3.latlng_to_cell(r["latitude"], r["longitude"], H3_RES_FINE),
        axis=1,
    )
    df["h3_r8"] = df.apply(
        lambda r: h3.latlng_to_cell(r["latitude"], r["longitude"], H3_RES_COARSE),
        axis=1,
    )
    return df


# ── OSMnx road network ────────────────────────────────────────────────────

def _load_or_fetch_graph():
    """Load cached OSM graph or fetch from internet."""
    import osmnx as ox
    if OSM_GRAPH_FILE.exists():
        logger.info("Loading cached OSM graph from %s", OSM_GRAPH_FILE)
        return ox.load_graphml(OSM_GRAPH_FILE)

    logger.info("Fetching Bengaluru drive network from OSM (one-time)…")
    place = "Bengaluru, Karnataka, India"
    G = ox.graph_from_place(place, network_type="drive")
    EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(G, OSM_GRAPH_FILE)
    logger.info("OSM graph saved to %s", OSM_GRAPH_FILE)
    return G


def _build_node_gdf(G):
    import osmnx as ox
    nodes, _ = ox.graph_to_gdfs(G)
    return nodes


def add_road_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add road_class and dist_to_major_road_m using the OSM drive network.
    Falls back gracefully if osmnx is unavailable.
    """
    try:
        import osmnx as ox
        from shapely.geometry import Point
    except ImportError:
        logger.warning("osmnx/shapely not available – skipping road features")
        df["road_class"] = "unknown"
        df["dist_to_major_road_m"] = np.nan
        return df

    G = _load_or_fetch_graph()
    nodes = _build_node_gdf(G)

    df = df.copy()

    # Snap each violation point to nearest OSM node to get highway tag
    lats = df["latitude"].values
    lons = df["longitude"].values

    road_classes = []
    for lat, lon in zip(lats, lons):
        try:
            node_id = ox.nearest_nodes(G, lon, lat)
            # walk outgoing edges to get highway type
            edge_data = [d for _, _, d in G.edges(node_id, data=True)]
            hw_types = [d.get("highway", "unknown") for d in edge_data]
            # flatten lists
            flat = []
            for h in hw_types:
                if isinstance(h, list):
                    flat.extend(h)
                else:
                    flat.append(h)
            if any(t in ("motorway", "trunk", "primary") for t in flat):
                road_classes.append("primary")
            elif any(t == "secondary" for t in flat):
                road_classes.append("secondary")
            elif any(t == "tertiary" for t in flat):
                road_classes.append("tertiary")
            else:
                road_classes.append("other")
        except Exception:
            road_classes.append("unknown")

    df["road_class"] = road_classes
    # Simplified dist metric: 0 for primary, 50 for secondary, 100 for others
    _dist_map = {"primary": 0, "secondary": 50, "tertiary": 75, "other": 100, "unknown": 100}
    df["dist_to_major_road_m"] = df["road_class"].map(_dist_map)
    return df


# ── Junction distance ─────────────────────────────────────────────────────

def _haversine_m(lat1, lon1, lat2, lon2):
    R = 6_371_000  # Earth radius in metres
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi  = np.radians(lat2 - lat1)
    dlam  = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlam / 2) ** 2
    return R * 2 * np.arcsin(np.sqrt(a))


def build_junction_coords(df: pd.DataFrame) -> pd.DataFrame:
    """
    Derive junction centroids from the dataset itself (median lat/lon per
    junction_name) and cache to EXTERNAL_DIR.
    Returns the junction coords DataFrame.
    """
    JUNCTION_FILE.parent.mkdir(parents=True, exist_ok=True)
    if JUNCTION_FILE.exists():
        return pd.read_parquet(JUNCTION_FILE)

    junc = df[df["near_junction"]].groupby("junction_name").agg(
        lat=("latitude", "median"),
        lon=("longitude", "median"),
        count=("id", "count"),
    ).reset_index()
    junc.to_parquet(JUNCTION_FILE, index=False)
    logger.info("Junction coords cached: %d junctions", len(junc))
    return junc


def add_junction_distance(df: pd.DataFrame, junc: pd.DataFrame) -> pd.DataFrame:
    """Add dist_to_nearest_junction_m column."""
    if junc.empty:
        df["dist_to_nearest_junction_m"] = np.nan
        return df

    jlats = junc["lat"].values
    jlons = junc["lon"].values

    dists = []
    for lat, lon in zip(df["latitude"].values, df["longitude"].values):
        d = _haversine_m(lat, lon, jlats, jlons)
        dists.append(d.min())

    df = df.copy()
    df["dist_to_nearest_junction_m"] = dists
    return df


def build_geo_features(df: pd.DataFrame, skip_osm: bool = False) -> pd.DataFrame:
    """
    Full geo feature pipeline:
    H3 → junction coords → junction distance → (optionally) road class.
    """
    logger.info("Building geo features…")
    df = add_h3(df)
    junc = build_junction_coords(df)
    df = add_junction_distance(df, junc)
    if not skip_osm:
        df = add_road_features(df)
    else:
        df["road_class"]           = "unknown"
        df["dist_to_major_road_m"] = np.nan
    logger.info("Geo features done")
    return df
