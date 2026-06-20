"""Vercel Python entrypoint.

This endpoint exists to satisfy Vercel's Python runtime requirements.
The Streamlit UI should be hosted on a Streamlit-compatible platform.
"""
from __future__ import annotations

import json
from typing import Iterable, Tuple


def _json_response(status: str, payload: dict) -> Tuple[str, list[tuple[str, str]], Iterable[bytes]]:
    body = json.dumps(payload).encode("utf-8")
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
    ]
    return status, headers, [body]


def app(environ, start_response):
    """WSGI entrypoint for Vercel Python runtime."""
    path = environ.get("PATH_INFO", "/")

    if path in ("/health", "/healthz"):
        status, headers, body = _json_response(
            "200 OK",
            {
                "status": "ok",
                "service": "parkiq-vercel-entrypoint",
            },
        )
    else:
        status, headers, body = _json_response(
            "200 OK",
            {
                "message": "Vercel Python entrypoint is live.",
                "note": "This repository's main UI is a Streamlit app (app/Home.py).",
                "streamlit_command": "streamlit run app/Home.py",
            },
        )

    start_response(status, headers)
    return body
