"""Vercel Python entrypoint.

This endpoint exists to satisfy Vercel's Python runtime requirements.
The Streamlit UI should be hosted on a Streamlit-compatible platform.
"""
from __future__ import annotations

import json
import os
from typing import Iterable, Tuple


def _json_response(status: str, payload: dict) -> Tuple[str, list[tuple[str, str]], Iterable[bytes]]:
    body = json.dumps(payload).encode("utf-8")
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
    ]
    return status, headers, [body]


def _html_response(status: str, html: str) -> Tuple[str, list[tuple[str, str]], Iterable[bytes]]:
    body = html.encode("utf-8")
    headers = [
        ("Content-Type", "text/html; charset=utf-8"),
        ("Content-Length", str(len(body))),
    ]
    return status, headers, [body]


def _redirect_response(location: str) -> Tuple[str, list[tuple[str, str]], Iterable[bytes]]:
    body = b""
    headers = [
        ("Location", location),
        ("Cache-Control", "no-store"),
        ("Content-Length", "0"),
    ]
    return "307 Temporary Redirect", headers, [body]


def app(environ, start_response):
    """WSGI entrypoint for Vercel Python runtime."""
    path = environ.get("PATH_INFO", "/")
        streamlit_url = os.environ.get("STREAMLIT_PUBLIC_URL", "").strip()

    if path in ("/health", "/healthz"):
        status, headers, body = _json_response(
            "200 OK",
            {
                "status": "ok",
                "service": "parkiq-vercel-entrypoint",
            },
        )
        elif streamlit_url:
                status, headers, body = _redirect_response(streamlit_url)
    else:
                status, headers, body = _html_response(
            "200 OK",
                        """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>ParkIQ Live</title>
    <style>
        body { font-family: system-ui, sans-serif; margin: 0; background: #0b1220; color: #e2e8f0; }
        .wrap { max-width: 760px; margin: 64px auto; padding: 0 20px; }
        .card { background: #111a2d; border: 1px solid #24324f; border-radius: 14px; padding: 22px; }
        h1 { margin: 0 0 12px; font-size: 1.5rem; }
        p { line-height: 1.6; color: #b6c2d9; }
        code { background: #1a2740; padding: 2px 6px; border-radius: 6px; color: #d7e3ff; }
    </style>
</head>
<body>
    <div class="wrap">
        <div class="card">
            <h1>ParkIQ Vercel Endpoint Is Live</h1>
            <p>This domain currently serves a lightweight Python endpoint.</p>
            <p>To show the Streamlit app here, set Vercel env var <code>STREAMLIT_PUBLIC_URL</code> to your deployed Streamlit URL. Requests will auto-redirect.</p>
            <p>Local run command: <code>streamlit run app/Home.py</code></p>
        </div>
    </div>
</body>
</html>
""",
        )

    start_response(status, headers)
    return body
