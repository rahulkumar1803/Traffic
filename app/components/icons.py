"""Reusable SVG icon headings for Streamlit pages."""
from pathlib import Path

import streamlit as st

_ICON_DIR = Path(__file__).resolve().parents[1] / "assets" / "icons"


def _svg_markup(icon_name: str, size: int = 20) -> str:
    svg_path = _ICON_DIR / f"{icon_name}.svg"
    if not svg_path.exists():
        return ""

    svg = svg_path.read_text(encoding="utf-8").strip()
    svg = svg.replace('width="22"', f'width="{size}"')
    svg = svg.replace('height="22"', f'height="{size}"')
    return svg


def render_heading(text: str, icon_name: str, level: int = 2, container=None) -> None:
    """Render a heading with a local SVG icon instead of emoji."""
    target = container if container is not None else st
    svg = _svg_markup(icon_name)
    html = (
        f"<h{level} style='display:flex;align-items:center;gap:10px;margin:0.2rem 0 0.65rem 0;'>"
        f"<span style='display:inline-flex;line-height:0'>{svg}</span>"
        f"<span>{text}</span>"
        f"</h{level}>"
    )
    target.markdown(html, unsafe_allow_html=True)
