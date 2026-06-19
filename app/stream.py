"""
stream.py – Replay engine: steps through timestamps to simulate a live feed.
"""
import time
from typing import Generator

import pandas as pd
import streamlit as st
from components.icons import render_heading


@st.cache_data(show_spinner=False)
def _sorted_events(clean_parquet: str) -> pd.DataFrame:
    df = pd.read_parquet(clean_parquet)
    df = df.sort_values("created_datetime").reset_index(drop=True)
    return df


def replay_generator(
    df: pd.DataFrame,
    window_minutes: int = 30,
) -> Generator[pd.DataFrame, None, None]:
    """
    Yield successive windows of violations in timestamp order.
    Each yield = one time-window slice (simulate real-time feed).
    """
    df = df.sort_values("created_datetime")
    t_start = df["created_datetime"].min()
    t_end   = df["created_datetime"].max()
    t_cur   = t_start
    delta   = pd.Timedelta(minutes=window_minutes)

    while t_cur <= t_end:
        window = df[
            (df["created_datetime"] >= t_cur) &
            (df["created_datetime"] < t_cur + delta)
        ]
        yield window
        t_cur += delta


def build_replay_ui(df: pd.DataFrame) -> pd.DataFrame:
    """
    Render replay slider + play/pause in Streamlit sidebar.
    Returns the current slice of violations for the selected timestamp.
    """
    st.sidebar.markdown("---")
    render_heading("Live Replay", "play", level=3, container=st.sidebar)

    dates = pd.to_datetime(df["created_datetime"]).dt.date.unique()
    dates = sorted(dates)

    if not dates:
        return df

    selected_date = st.sidebar.select_slider(
        "Replay date",
        options=dates,
        value=dates[len(dates) // 2],
        format_func=lambda d: str(d),
    )

    hour = st.sidebar.slider("Hour", 0, 23, 8)
    window = st.sidebar.slider("Window (min)", 15, 120, 30, step=15)

    t_from = pd.Timestamp(str(selected_date)) + pd.Timedelta(hours=hour)
    t_to   = t_from + pd.Timedelta(minutes=window)

    slice_df = df[
        (df["created_datetime"] >= t_from) &
        (df["created_datetime"] < t_to)
    ]
    st.sidebar.caption(f"{len(slice_df)} events in window")
    return slice_df
