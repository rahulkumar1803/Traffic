"""Reusable SVG icon headings for Streamlit pages."""
import re
from pathlib import Path

import streamlit as st

_ICON_DIR = Path(__file__).resolve().parents[1] / "assets" / "icons"


def _svg_markup(icon_name: str, size: int = 20) -> str:
    svg_path = _ICON_DIR / f"{icon_name}.svg"
    if not svg_path.exists():
        return ""

    svg = svg_path.read_text(encoding="utf-8").strip()
    # Normalize icon dimensions so one size control works for all SVG files.
    svg = re.sub(r'width="\d+"', f'width="{size}"', svg, count=1)
    svg = re.sub(r'height="\d+"', f'height="{size}"', svg, count=1)
    return svg


def render_heading(text: str, icon_name: str, level: int = 2, container=None) -> None:
    """Render a heading with a local SVG icon instead of emoji."""
    target = container if container is not None else st
    icon_size = {1: 34, 2: 30, 3: 26}.get(level, 24)
    svg = _svg_markup(icon_name, size=icon_size)
    html = (
        f"<h{level} style='display:flex;align-items:center;gap:10px;margin:0.2rem 0 0.65rem 0;'>"
        f"<span style='display:inline-flex;line-height:0'>{svg}</span>"
        f"<span>{text}</span>"
        f"</h{level}>"
    )
    target.markdown(html, unsafe_allow_html=True)
