"""
tests/test_pipeline.py – Core sanity checks for ParkIQ pipeline components.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
import numpy as np
import pandas as pd

from parkiq.config import (
    SEVERITY_WEIGHTS, PARKING_KEYWORDS, CIS_WEIGHTS,
    H3_RES_FINE, BBOX,
)
from parkiq.clean import _primary_violation, _is_parking
from parkiq.impact import compute_h3_aggregates, compute_cis
from parkiq.staffing import estimate_officers
from parkiq.alerts import cis_to_tier


# ── 1. Severity map correctness ───────────────────────────────────────────

def test_severity_weights_range():
    for k, v in SEVERITY_WEIGHTS.items():
        assert 0 <= v <= 1, f"Severity weight out of range for {k}: {v}"


def test_parking_keywords_have_weights():
    for kw in PARKING_KEYWORDS:
        assert kw in SEVERITY_WEIGHTS, f"{kw} missing from SEVERITY_WEIGHTS"


def test_primary_violation_picks_highest():
    vlist = ["WRONG PARKING", "PARKING IN A MAIN ROAD"]
    pv = _primary_violation(vlist)
    assert pv == "PARKING IN A MAIN ROAD", f"Expected PARKING IN A MAIN ROAD, got {pv}"


def test_is_parking_true():
    assert _is_parking(["NO PARKING", "OTHER"]) is True


def test_is_parking_false():
    assert _is_parking(["SPEEDING"]) is False


# ── 2. CIS weights sum to 1 ───────────────────────────────────────────────

def test_cis_weights_sum():
    total = sum(CIS_WEIGHTS.values())
    assert abs(total - 1.0) < 1e-6, f"CIS weights sum to {total}, expected 1.0"


# ── 3. CIS output in [0, 100] ─────────────────────────────────────────────

def _make_dummy_agg(n=20):
    rng = np.random.default_rng(42)
    return pd.DataFrame({
        "h3_r9":              [f"cell_{i}" for i in range(n)],
        "count":              rng.integers(1, 200, n),
        "mean_severity":      rng.uniform(0.3, 1.0, n),
        "near_junction_sum":  rng.integers(0, 50, n),
        "peak_sum":           rng.integers(0, 100, n),
        "heavy_sum":          rng.integers(0, 20, n),
        "lat":                rng.uniform(12.9, 13.1, n),
        "lon":                rng.uniform(77.5, 77.7, n),
        "road_class":         rng.choice(["primary","secondary","tertiary","other"], n),
        "dist_junction_m":    rng.uniform(0, 500, n),
        "near_junction_rate": rng.uniform(0, 1, n),
        "peak_concentration": rng.uniform(0, 1, n),
        "heavy_vehicle_share":rng.uniform(0, 0.5, n),
        "junction_factor":    rng.uniform(0, 1, n),
    })


def test_cis_in_range():
    agg = _make_dummy_agg(50)
    cis_df = compute_cis(agg)
    assert "cis" in cis_df.columns
    assert cis_df["cis"].between(0, 100).all(), "CIS values outside [0, 100]"


# ── 4. Cluster produces ≥1 hotspot ────────────────────────────────────────

def test_hotspot_detection_nonempty():
    rng = np.random.default_rng(0)
    n = 300
    # Clustered lat/lon within Bengaluru
    lats = np.concatenate([
        rng.normal(12.97, 0.005, n // 3),
        rng.normal(12.94, 0.005, n // 3),
        rng.normal(13.00, 0.005, n // 3),
    ])
    lons = np.concatenate([
        rng.normal(77.59, 0.005, n // 3),
        rng.normal(77.56, 0.005, n // 3),
        rng.normal(77.62, 0.005, n // 3),
    ])
    df = pd.DataFrame({
        "id":               [f"id{i}" for i in range(n)],
        "latitude":         lats,
        "longitude":        lons,
        "primary_violation":["WRONG PARKING"] * n,
        "severity_weight":  [0.5] * n,
        "near_junction":    [True] * n,
        "junction_name":    ["KR Market"] * n,
        "police_station":   ["Upparpet"] * n,
        "h3_r9":            [f"cell_{i % 10}" for i in range(n)],
        "cell_cis":         rng.uniform(40, 90, n),
        "time_bucket":      ["evening_peak"] * n,
        "is_heavy_vehicle": [False] * n,
    })
    from parkiq.cluster import detect_hotspots
    cis_stub = pd.DataFrame({"h3_r9": [f"cell_{i}" for i in range(10)],
                              "cis": rng.uniform(40, 90, 10)})
    hotspots = detect_hotspots(df, cis_stub)
    assert len(hotspots) >= 1, "Expected at least 1 hotspot"


# ── 5. officers_needed in [1, 6] ─────────────────────────────────────────

@pytest.mark.parametrize("viol,vph", [
    ("WRONG PARKING", 1.0),
    ("PARKING IN A MAIN ROAD", 10.0),
    ("DOUBLE PARKING", 20.0),
    ("NO PARKING", 0.5),
])
def test_officers_in_range(viol, vph):
    hotspot = pd.Series({
        "top_violation":   viol,
        "hull_wkt":        "",
        "road_class":      "secondary",
        "heavy_vehicle_share": 0.1,
    })
    result = estimate_officers(hotspot, vph)
    n = result["officers_needed"]
    assert 1 <= n <= 6, f"officers_needed={n} out of [1,6] for viol={viol}, vph={vph}"


# ── 6. Alert tier routing ─────────────────────────────────────────────────

@pytest.mark.parametrize("cis,expected", [
    (25,  "None"),
    (45,  "Watch"),
    (65,  "Warning"),
    (85,  "Critical"),
    (100, "Critical"),
])
def test_alert_tiers(cis, expected):
    assert cis_to_tier(cis) == expected


# ── 7. H3 round-trip ─────────────────────────────────────────────────────

def test_h3_roundtrip():
    try:
        import h3
    except ImportError:
        pytest.skip("h3 not installed")
    lat, lon = 12.9716, 77.5946
    cell = h3.latlng_to_cell(lat, lon, H3_RES_FINE)
    assert cell is not None
    center = h3.cell_to_latlng(cell)
    assert abs(center[0] - lat) < 0.002
    assert abs(center[1] - lon) < 0.002


# ── 8. Bbox validation ────────────────────────────────────────────────────

def test_bengaluru_bbox():
    assert BBOX["lat_min"] < BBOX["lat_max"]
    assert BBOX["lon_min"] < BBOX["lon_max"]
    # Known Bengaluru coordinate (City Market)
    lat, lon = 12.9634, 77.5760
    assert BBOX["lat_min"] <= lat <= BBOX["lat_max"]
    assert BBOX["lon_min"] <= lon <= BBOX["lon_max"]
