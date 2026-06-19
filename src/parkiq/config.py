"""
ParkIQ – central configuration.
All paths, constants, model weights live here so they can be tuned in one place.
"""
from pathlib import Path

# ── Repo root ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]

# ── Data paths ─────────────────────────────────────────────────────────────
RAW_CSV = ROOT / "data" / "raw" / "jan to may police violation_anonymized791b166.csv"
PROCESSED_DIR = ROOT / "data" / "processed"
EXTERNAL_DIR = ROOT / "data" / "external"

# Processed artefact filenames
CLEAN_PARQUET       = PROCESSED_DIR / "clean_events.parquet"
H3_AGG_PARQUET      = PROCESSED_DIR / "h3_aggregates.parquet"
HOTSPOT_PARQUET     = PROCESSED_DIR / "hotspots.parquet"
CIS_PARQUET         = PROCESSED_DIR / "cis_table.parquet"
FORECAST_PARQUET    = PROCESSED_DIR / "forecast.parquet"
ROUTE_PARQUET       = PROCESSED_DIR / "patrol_route.parquet"
STATION_PARQUET     = PROCESSED_DIR / "station_centroids.parquet"
STAFFING_PARQUET    = PROCESSED_DIR / "staffing.parquet"
ALERT_STATE_PARQUET = PROCESSED_DIR / "alert_state.parquet"

# OSM cache
OSM_GRAPH_FILE   = EXTERNAL_DIR / "bengaluru_drive.graphml"
JUNCTION_FILE    = EXTERNAL_DIR / "junction_coords.parquet"

# ── Bengaluru bounding box ─────────────────────────────────────────────────
BBOX = dict(lat_min=12.81, lat_max=13.26, lon_min=77.45, lon_max=77.77)

# ── H3 resolutions ────────────────────────────────────────────────────────
H3_RES_FINE   = 9   # ≈174 m – used for hotspot detection & CIS
H3_RES_COARSE = 8   # ≈461 m – used for the heatmap overview

# ── Violation severity weights ─────────────────────────────────────────────
# Higher = worse impact on traffic flow
SEVERITY_WEIGHTS: dict[str, float] = {
    "PARKING IN A MAIN ROAD":       1.0,
    "DOUBLE PARKING":               1.0,
    "PARKING NEAR ROAD CROSSING":   0.95,
    "PARKING NEAR TRAFFIC LIGHT":   0.95,
    "PARKING NEAR BUSTOP":          0.90,
    "PARKING ON FOOTPATH":          0.85,
    "NO PARKING":                   0.60,
    "WRONG PARKING":                0.50,
    # fallback for any other parking violation
    "__OTHER_PARKING__":            0.40,
    # non-parking (kept in dataset but downweighted)
    "__NON_PARKING__":              0.10,
}

# Violations considered "parking" (filter in clean.py)
PARKING_KEYWORDS = {
    "PARKING IN A MAIN ROAD",
    "DOUBLE PARKING",
    "PARKING NEAR ROAD CROSSING",
    "PARKING NEAR TRAFFIC LIGHT",
    "PARKING NEAR BUSTOP",
    "PARKING ON FOOTPATH",
    "NO PARKING",
    "WRONG PARKING",
}

# ── Vehicle type weights (blocking potential) ──────────────────────────────
HEAVY_VEHICLE_TYPES = {"BUS", "TRUCK", "LORRY", "MAXI-CAB", "TRACTOR", "TANKER"}

# ── Congestion Impact Score weights ────────────────────────────────────────
# Must sum to 1.0
CIS_WEIGHTS = dict(
    density        = 0.25,
    mean_severity  = 0.25,
    junction       = 0.20,
    road_class     = 0.15,
    peak_conc      = 0.10,
    heavy_veh      = 0.05,
)

# ── Time buckets ───────────────────────────────────────────────────────────
TIME_BUCKETS = {
    "morning_peak":  (8,  11),
    "midday":        (11, 17),
    "evening_peak":  (17, 21),
    "night":         (21, 24),
    "early_morning": (0,   8),
}

# ── Alert thresholds ───────────────────────────────────────────────────────
ALERT_WATCH    = 40
ALERT_WARNING  = 60
ALERT_CRITICAL = 80
PREWARNING_LEAD_MIN = 60  # minutes before forecasted peak to issue pre-warning

# ── Staffing model constants ───────────────────────────────────────────────
BASE_HANDLE_MIN  = 5   # minutes to ticket a violation
TOW_EXTRA_MIN    = 15  # extra minutes if towing
AREA_THRESH_M2   = 50_000  # hull area above which spread_factor kicks in
HEAVY_VEH_THRESH = 0.25    # heavy vehicle share triggering +1 officer

# ── LightGBM forecast ─────────────────────────────────────────────────────
FORECAST_HORIZON_DAYS = 1
LGBM_PARAMS = dict(
    objective      = "poisson",
    metric         = "poisson",
    n_estimators   = 400,
    learning_rate  = 0.05,
    num_leaves     = 63,
    subsample      = 0.8,
    colsample_bytree = 0.8,
    random_state   = 42,
    n_jobs         = -1,
    verbose        = -1,
)

# ── HDBSCAN ───────────────────────────────────────────────────────────────
HDBSCAN_MIN_CLUSTER_SIZE = 30
HDBSCAN_MIN_SAMPLES      = 10

# ── OR-Tools routing ──────────────────────────────────────────────────────
TOP_N_HOTSPOTS_ROUTE = 20  # hotspots to include in patrol route
NUM_PATROL_TEAMS     = 3
ROUTE_TIME_LIMIT_SEC = 10

# ── Map defaults ──────────────────────────────────────────────────────────
MAP_CENTER = [12.97, 77.59]  # Bengaluru city centre
MAP_ZOOM   = 12
