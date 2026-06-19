"""
io_load.py – chunked CSV read with dtype coercion.
"""
import ast
import json
import logging
from pathlib import Path

import pandas as pd

from parkiq.config import RAW_CSV

logger = logging.getLogger(__name__)

# Columns that are always 100 % NULL in this dataset – skip on read
_DROP_COLS = ["description", "closed_datetime", "action_taken_timestamp"]

# Final dtypes after parsing
_STR_COLS = [
    "id", "location", "vehicle_number", "vehicle_type", "offence_code",
    "device_id", "created_by_id", "police_station", "junction_name",
    "updated_vehicle_number", "updated_vehicle_type", "validation_status",
]


def _parse_json_col(series: pd.Series) -> pd.Series:
    """Safely parse a column that contains JSON lists like '["A","B"]'."""
    def _safe(val):
        if pd.isna(val) or val in ("NULL", ""):
            return []
        try:
            result = json.loads(val)
            return result if isinstance(result, list) else [result]
        except (ValueError, TypeError):
            try:
                return ast.literal_eval(val)
            except Exception:
                return []
    return series.apply(_safe)


def load_raw(csv_path: Path = RAW_CSV, chunksize: int = 50_000) -> pd.DataFrame:
    """
    Read the raw CSV in chunks, drop useless columns, parse JSON list cols,
    and return a single DataFrame.
    """
    logger.info("Reading CSV: %s", csv_path)

    usecols = None  # read all; drop afterwards
    chunks = []
    reader = pd.read_csv(
        csv_path,
        chunksize=chunksize,
        low_memory=False,
        parse_dates=False,  # we parse manually to handle tz
    )
    for chunk in reader:
        # Drop always-null / useless columns if present
        drop = [c for c in _DROP_COLS if c in chunk.columns]
        chunk.drop(columns=drop, inplace=True)

        # Numeric geo
        chunk["latitude"]  = pd.to_numeric(chunk["latitude"],  errors="coerce")
        chunk["longitude"] = pd.to_numeric(chunk["longitude"], errors="coerce")

        chunks.append(chunk)

    df = pd.concat(chunks, ignore_index=True)
    logger.info("Raw shape: %s", df.shape)

    # Parse JSON-list columns
    df["violation_type"] = _parse_json_col(df["violation_type"])
    df["offence_code"]   = _parse_json_col(df["offence_code"].astype(str))

    # String coercion
    for col in _STR_COLS:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    return df
