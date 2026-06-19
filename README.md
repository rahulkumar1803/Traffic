# ParkIQ — AI-Driven Parking Intelligence for Bengaluru

> **Hackathon project** — detects illegal-parking hotspots, quantifies their
> congestion impact, forecasts tomorrow's risk zones, and outputs an optimised
> enforcement patrol plan. All on an interactive live Bengaluru map.

---

## Architecture overview

```
gridlock/
├── data/
│   ├── raw/        ← original 109 MB CSV
│   ├── processed/  ← Parquet artefacts (fast Streamlit load)
│   └── external/   ← cached OSM road network + junction coords
├── src/parkiq/     ← Python package (all logic)
├── app/            ← Streamlit multi-page app
├── scripts/        ← build_artifacts.py (run once)
├── tests/          ← pytest suite
└── requirements.txt
```

**Performance principle:** the CSV is processed *once* by `build_artifacts.py`
into small Parquet files. The Streamlit app reads only Parquet → instant load.

---

## Quick start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Build all artefacts (takes ~3–5 min first run)
python scripts/build_artifacts.py

# Optional: include real OSM road network (needs internet, ~5 min extra)
python scripts/build_artifacts.py --osm

# 3. Launch the app
streamlit run app/Home.py

# 4. Run tests
pytest tests/ -v
```

---

## The 8 deliverables

| # | Deliverable | Location |
|---|------------|---------|
| 1 | **Hotspot detection** — HDBSCAN density clustering | `src/parkiq/cluster.py` · Page 1 |
| 2 | **Congestion Impact Score (CIS 0–100)** | `src/parkiq/impact.py` · Page 2 |
| 3 | **Live Bengaluru map** — heatmap + 3D hex + hotspot polygons + stream + patrol path | `app/Home.py` · Page 1 |
| 4 | **Forecast** — LightGBM Poisson next-day hotspot | `src/parkiq/forecast.py` · Page 3 |
| 5 | **Enforcement planner** — OR-Tools VRP + schedule | `src/parkiq/routing.py` · Page 4 |
| 6 | **Station Alert Center** — Watch/Warning/Critical + ack/resolve | `src/parkiq/alerts.py` · Page 6 |
| 7 | **Officer staffing estimator** — workload model | `src/parkiq/staffing.py` · Page 4 |
| 8 | **Dispatch briefing** — shareable markdown/PDF packet | `src/parkiq/dispatch.py` · Page 7 |

---

## Congestion Impact Score methodology

```
CIS = 100 × ( w₁·density_norm
            + w₂·mean_severity_norm
            + w₃·junction_factor_norm
            + w₄·road_class_norm
            + w₅·peak_concentration_norm
            + w₆·heavy_vehicle_share_norm )
```

| Component | Default weight | Rationale |
|-----------|---------------|-----------|
| Violation density | **0.25** | More cars blocked = more congestion |
| Mean severity | **0.25** | Main-road/junction violations block more lanes |
| Junction proximity | **0.20** | Near-junction parking causes intersection blocking |
| Road class | **0.15** | Primary/trunk arterials carry more flow |
| Peak-hour concentration | **0.10** | Violations during rush-hour have outsized impact |
| Heavy-vehicle share | **0.05** | HGV/bus harder to pass, longer tow time |

All weights live in `src/parkiq/config.py` and are shown in the UI.
Each term is min-max normalised across the dataset → CIS ∈ [0, 100].

---

## Alert tiers

| Tier | CIS threshold | Action |
|------|--------------|--------|
| 🟢 Watch    | 40–59 | Log |
| 🟠 Warning  | 60–79 | Notify nearest station |
| 🔴 Critical | ≥ 80  | Notify station + control room + top priority |

Pre-warnings issued **60 min before** a forecasted peak bucket (configurable in `config.py`).

---

## Officer staffing model

```python
service_time     = BASE_HANDLE_MIN + tow_share × TOW_EXTRA_MIN   # 5–12.5 min
capacity/officer = 60 / service_time
base_officers    = ceil(violations_per_hour / capacity)
officers_needed  = clamp(base + spread_factor + road_factor + heavy_factor, 1, 6)
```

All constants in `config.py`. Rationale shown per hotspot in the UI.

---

## Models & algorithms

| Stage | Algorithm | Library |
|-------|-----------|---------|
| Hotspot detection | HDBSCAN (UTM-projected) | `hdbscan` |
| Spatial binning | Uber H3 hex grid (res 9 ≈ 174 m) | `h3` |
| Impact score | Composite CIS (weighted, normalised) | `numpy` |
| Forecast | LightGBM Poisson regressor | `lightgbm` |
| Patrol routing | OR-Tools VRP/TSP | `ortools` |
| Road context | OSMnx Bengaluru drive network | `osmnx` |

---

## Sanity check — expected top hotspots

After building artefacts the highest-CIS hotspots should cluster near:
- **Upparpet / City Market / KR Market** (highest station volume in dataset)
- **Malleshwaram / Shivajinagar** (major junction density)
- **Koramangala / Bellandur** (main-road parking violations)

This confirms the pipeline is faithful to the source data.

---

## Open assumptions

- **"Live"** = replayed historical stream (no real-time API exists in the dataset).
- OSM fetch needs internet **once** at build time; cached offline for the demo.
- CIS is derived/explainable by design — no external traffic API required.
- Webhook/SMS/email dispatch is stubbed with a log call; integration path is obvious.
