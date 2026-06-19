"""
pages/7_Officer_Briefing.py – Generate, preview and download dispatch packets.
"""
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "app"))
import tempfile

import streamlit as st
import pandas as pd

from parkiq.config import STAFFING_PARQUET, CLEAN_PARQUET, PROCESSED_DIR
from parkiq.dispatch import build_briefing, render_markdown, export_pdf
from components.icons import render_heading

st.set_page_config(page_title="Officer Briefing · ParkIQ", layout="wide")
render_heading("Officer Dispatch Briefing", "clipboard", level=1)

st.markdown(
    "Generate a shareable, printable briefing packet for any hotspot. "
    "Officers get: **where, when, what, how many, recommended action, repeat offenders**."
)


@st.cache_data
def _load():
    hs  = pd.read_parquet(STAFFING_PARQUET) if STAFFING_PARQUET.exists() else pd.DataFrame()
    raw = pd.read_parquet(CLEAN_PARQUET)    if CLEAN_PARQUET.exists()    else pd.DataFrame()
    return hs, raw

hotspots, df_events = _load()

if hotspots.empty:
    st.warning("Run `python scripts/build_artifacts.py` first.")
    st.stop()

# ── Merge cluster_id into events if needed ────────────────────────────────
# events need cluster_id for repeat-offender lookup
# During pipeline the events don't carry cluster_id – we skip that gracefully

# ── Hotspot selector ──────────────────────────────────────────────────────
ranked = hotspots.sort_values("max_cis", ascending=False)
sel_name = st.selectbox(
    "Select hotspot",
    ranked["hotspot_name"].tolist() if "hotspot_name" in ranked.columns else ["N/A"],
)

if st.button("Generate Briefing", type="primary"):
    with st.spinner("Building briefing…"):
        row = hotspots[hotspots["hotspot_name"] == sel_name].iloc[0]
        briefing = build_briefing(row, df_events)
        md = render_markdown(briefing)

    st.success("Briefing ready")
    st.markdown("---")
    st.markdown(md)

    # ── Downloads ─────────────────────────────────────────────────────────
    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.download_button(
            "⬇️ Download Markdown",
            data=md.encode("utf-8"),
            file_name=f"briefing_{sel_name[:30].replace(' ','_')}.md",
            mime="text/markdown",
        )
    with c2:
        tmp = Path(tempfile.mktemp(suffix=".pdf"))
        pdf_path = export_pdf(md, tmp)
        pdf_data = pdf_path.read_bytes() if pdf_path.suffix == ".pdf" else None
        if pdf_data:
            st.download_button(
                "⬇️ Download PDF",
                data=pdf_data,
                file_name=f"briefing_{sel_name[:30].replace(' ','_')}.pdf",
                mime="application/pdf",
            )
        else:
            st.info("PDF: install `reportlab` for PDF export (markdown downloaded above)")
    with c3:
        if st.button("Copy (show raw)"):
            st.code(md, language="markdown")

    # ── Structured summary table ──────────────────────────────────────────
    st.markdown("---")
    st.subheader("Quick Summary")
    summary = {
        "Zone":            briefing["hotspot_name"],
        "Junction":        briefing["junction"],
        "Station":         briefing["police_station"],
        "CIS":             f"{briefing['cis']:.1f}",
        "Officers needed": briefing["officers_needed"],
        "Peak window":     briefing["recommended_window"],
        "Top violation":   briefing["top_violation"],
        "Repeat offenders":len(briefing["repeat_offenders"]),
    }
    st.table(pd.DataFrame([(k, str(v)) for k, v in summary.items()], columns=["Field", "Value"]))

    if briefing["repeat_offenders"]:
        st.markdown("**Top repeat-offender vehicles:**")
        st.write(", ".join(briefing["repeat_offenders"]))
