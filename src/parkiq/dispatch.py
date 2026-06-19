"""
dispatch.py – Build and render shareable officer briefing packets.
"""
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from parkiq.config import PROCESSED_DIR

logger = logging.getLogger(__name__)

_RECOMMENDED_ACTION: dict[str, str] = {
    "PARKING IN A MAIN ROAD":     "Deploy towing crane + barricade; issue notice to repeat offenders.",
    "DOUBLE PARKING":             "Immediate towing; deploy cones to prevent recurrence.",
    "PARKING NEAR ROAD CROSSING": "Standing patrol + barricade; issue on-the-spot challan.",
    "PARKING NEAR TRAFFIC LIGHT": "Standing patrol; coordinate with traffic signal team.",
    "PARKING NEAR BUSTOP":        "Erect no-parking signage; brief bus depot about bus bay.",
    "PARKING ON FOOTPATH":        "Tow + fine; notify civic body for bollard installation.",
    "NO PARKING":                 "Challan + tow repeat offenders; install reflective no-parking board.",
    "WRONG PARKING":              "Issue challan; place temporary no-parking cone.",
}


def _top_n_repeat_offenders(df: pd.DataFrame, cluster_id: int, n: int = 10) -> list[str]:
    if "cluster_id" not in df.columns or "vehicle_number" not in df.columns:
        return []
    grp = df[df["cluster_id"] == cluster_id]
    counts = grp["vehicle_number"].value_counts()
    repeats = counts[counts > 1]
    return repeats.head(n).index.tolist()


def build_briefing(
    hotspot: pd.Series,
    df_events: pd.DataFrame,
) -> dict:
    """
    Construct a briefing packet dict for a single hotspot.
    """
    top_viol = str(hotspot.get("top_violation", "WRONG PARKING"))
    action = _RECOMMENDED_ACTION.get(top_viol, "Issue challan and monitor zone.")

    cluster_id = int(hotspot.get("cluster_id", -1))
    repeat_offenders = _top_n_repeat_offenders(df_events, cluster_id)

    return dict(
        hotspot_name       = hotspot.get("hotspot_name", "Unknown Zone"),
        junction           = hotspot.get("junction_name", "No Junction"),
        police_station     = hotspot.get("police_station", "Unknown"),
        lat                = float(hotspot.get("lat_centroid", 0)),
        lon                = float(hotspot.get("lon_centroid", 0)),
        cis                = float(hotspot.get("max_cis", hotspot.get("cis", 0))),
        cis_breakdown      = dict(
            density        = float(hotspot.get("density_n", 0)),
            severity       = float(hotspot.get("severity_n", 0)),
            junction       = float(hotspot.get("junction_n", 0)),
            road_class     = float(hotspot.get("road_n", 0)),
            peak_conc      = float(hotspot.get("peak_conc_n", 0)),
            heavy_vehicle  = float(hotspot.get("heavy_veh_n", 0)),
        ),
        top_violation      = top_viol,
        recommended_window = hotspot.get("recommended_window", "evening_peak"),
        officers_needed    = int(hotspot.get("officers_needed", 1)),
        staffing_rationale = hotspot.get("staffing_rationale", ""),
        recommended_action = action,
        repeat_offenders   = repeat_offenders,
        generated_at       = datetime.now().isoformat(),
    )


def render_markdown(briefing: dict) -> str:
    """Render briefing dict to a markdown string."""
    lines = [
        f"# ParkIQ Officer Briefing — {briefing['hotspot_name']}",
        f"_Generated: {briefing['generated_at']}_",
        "",
        "## Where",
        f"- **Zone:** {briefing['hotspot_name']}",
        f"- **Junction:** {briefing['junction']}",
        f"- **Nearest Station:** {briefing['police_station']}",
        f"- **GPS:** {briefing['lat']:.5f}, {briefing['lon']:.5f}",
        "",
        "## When",
        f"- **Recommended window:** {briefing['recommended_window'].replace('_',' ').title()}",
        "",
        "## What – Congestion Impact Score",
        f"- **CIS: {briefing['cis']:.1f} / 100**",
        "- Breakdown:",
    ]
    for k, v in briefing["cis_breakdown"].items():
        lines.append(f"  - {k.replace('_',' ').title()}: {v:.3f}")
    lines += [
        "",
        f"- **Top Violation:** {briefing['top_violation']}",
        "",
        "## How Many",
        f"- **Officers needed:** {briefing['officers_needed']}",
        f"- _Rationale: {briefing['staffing_rationale']}_",
        "",
        "## Recommended Action",
        briefing["recommended_action"],
        "",
        "## Repeat Offenders (top vehicles)",
    ]
    if briefing["repeat_offenders"]:
        for v in briefing["repeat_offenders"]:
            lines.append(f"- {v}")
    else:
        lines.append("- None identified in current window")
    return "\n".join(lines)


def export_pdf(markdown_text: str, path: Path) -> Path:
    """Export briefing as PDF using reportlab (fallback: write markdown)."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm

        styles = getSampleStyleSheet()
        doc = SimpleDocTemplate(str(path), pagesize=A4)
        story = []
        for line in markdown_text.splitlines():
            clean = line.lstrip("#- ").strip()
            if not clean:
                story.append(Spacer(1, 5 * mm))
            elif line.startswith("# "):
                story.append(Paragraph(clean, styles["Title"]))
            elif line.startswith("## "):
                story.append(Paragraph(clean, styles["Heading2"]))
            else:
                story.append(Paragraph(clean, styles["Normal"]))
        doc.build(story)
    except ImportError:
        md_path = path.with_suffix(".md")
        md_path.write_text(markdown_text, encoding="utf-8")
        return md_path
    return path
