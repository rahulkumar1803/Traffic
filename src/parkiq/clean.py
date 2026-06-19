"""
clean.py – dedup, datetime parsing, geo-validation, parking filter.
"""
import logging

import pandas as pd

from parkiq.config import BBOX, PARKING_KEYWORDS, SEVERITY_WEIGHTS

logger = logging.getLogger(__name__)


# ── Datetime parsing ───────────────────────────────────────────────────────

def _parse_dt(series: pd.Series) -> pd.Series:
    """Parse datetime column; convert to IST (UTC+5:30), return tz-naive."""
    dt = pd.to_datetime(series, utc=True, errors="coerce")
    dt = dt.dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
    return dt


# ── Primary violation extraction ──────────────────────────────────────────

def _primary_violation(vlist: list) -> str:
    """
    Given a list of violation strings, return the most severe one
    (highest SEVERITY_WEIGHTS score).  Falls back to first item.
    """
    if not vlist:
        return "__NON_PARKING__"
    best = max(vlist, key=lambda v: SEVERITY_WEIGHTS.get(str(v).upper(), 0))
    return str(best).upper()


def _is_parking(vlist: list) -> bool:
    """True if any violation in the list is a parking violation."""
    return any(str(v).upper() in PARKING_KEYWORDS for v in vlist)


# ── Main clean function ────────────────────────────────────────────────────

def clean(df: pd.DataFrame, parking_only: bool = True) -> pd.DataFrame:
    """
    Full cleaning pipeline.  Returns a tidy DataFrame ready for feature
    engineering.

    Parameters
    ----------
    df : raw DataFrame from io_load.load_raw()
    parking_only : if True (default) filter to parking violations only
    """
    logger.info("Start clean: %d rows", len(df))

    # 1. Parse datetimes
    df["created_datetime"]  = _parse_dt(df["created_datetime"])
    df["modified_datetime"] = _parse_dt(df.get("modified_datetime", pd.Series(dtype=str)))

    # Drop rows with missing created_datetime
    df = df.dropna(subset=["created_datetime"])

    # 2. Geo-validate: keep rows inside Bengaluru bbox
    df = df[
        df["latitude"].between(BBOX["lat_min"], BBOX["lat_max"]) &
        df["longitude"].between(BBOX["lon_min"], BBOX["lon_max"])
    ]
    logger.info("After bbox filter: %d rows", len(df))

    # 3. violation_type is already a list from io_load; normalise to uppercase strings
    df["violation_type"] = df["violation_type"].apply(
        lambda lst: [str(v).upper() for v in (lst if isinstance(lst, list) else [])]
    )

    # 4. Primary violation + is_parking flag
    df["primary_violation"] = df["violation_type"].apply(_primary_violation)
    df["is_parking"]        = df["violation_type"].apply(_is_parking)

    # 5. Severity weight (per row, based on primary violation)
    df["severity_weight"] = df["primary_violation"].map(
        lambda v: SEVERITY_WEIGHTS.get(v, SEVERITY_WEIGHTS["__OTHER_PARKING__"])
    )

    # 6. Parking filter
    if parking_only:
        before = len(df)
        df = df[df["is_parking"]].copy()
        logger.info("Parking filter: %d → %d rows", before, len(df))

    # 7. Dedup on (vehicle_number, created_datetime, location)
    before = len(df)
    df = df.drop_duplicates(
        subset=["vehicle_number", "created_datetime", "location"]
    )
    logger.info("After dedup: %d → %d rows", before, len(df))

    # 8. Junction flag
    df["near_junction"] = df["junction_name"].str.upper().ne("NO JUNCTION")

    # 9. Reset index
    df = df.reset_index(drop=True)
    logger.info("Clean done: %d rows", len(df))
    return df
