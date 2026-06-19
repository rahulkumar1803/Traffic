#!/usr/bin/env python
"""
scripts/build_artifacts.py
Run once before launching the Streamlit app.

Usage:
    python scripts/build_artifacts.py [--force] [--osm]

Options:
    --force  Re-run all stages even if artefacts exist.
    --osm    Fetch real OSM road network (needs internet; ~5 min).
             Default: skip OSM (uses heuristic road class).
"""
import argparse
import logging
import sys
from pathlib import Path

# Make sure src/ is on the path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt="%H:%M:%S",
)

from parkiq.pipeline import run


def main():
    parser = argparse.ArgumentParser(description="Build ParkIQ artefacts")
    parser.add_argument("--force", action="store_true", help="Rebuild all stages")
    parser.add_argument("--osm",   action="store_true", help="Fetch live OSM road network")
    args = parser.parse_args()

    counts = run(skip_osm=not args.osm, force=args.force)
    print("\n=== Artefact row counts ===")
    for name, n in counts.items():
        status = "✓" if n > 0 else "✗ EMPTY"
        print(f"  {status}  {name}: {n}")

    empty = [k for k, v in counts.items() if v == 0]
    if empty:
        print(f"\nWARNING: empty artefacts: {empty}")
        sys.exit(1)
    print("\nAll artefacts built successfully.")


if __name__ == "__main__":
    main()
