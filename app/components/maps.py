"""
components/maps.py – Pydeck layer builders for the ParkIQ map.
"""
import pandas as pd
import pydeck as pdk

from parkiq.config import MAP_CENTER, MAP_ZOOM

# Carto dark-matter – full street map, no Mapbox token required
MAP_STYLE_DARK   = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
# Carto voyager – colourful street map (alternative)
MAP_STYLE_STREET = "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json"


def heatmap_layer(df: pd.DataFrame) -> pdk.Layer:
    return pdk.Layer(
        "HeatmapLayer",
        data=df[["latitude", "longitude"]].dropna().rename(
            columns={"latitude": "lat", "longitude": "lng"}
        ),
        get_position="[lng, lat]",
        aggregation="MEAN",
        threshold=0.05,
        opacity=0.6,
        pickable=False,
    )


def hex_layer(cis_df: pd.DataFrame, elevation_scale: int = 40) -> pdk.Layer:
    """3D hexbin extruded by CIS."""
    data = cis_df[["lat", "lon", "cis"]].dropna().copy()
    data.columns = ["lat", "lon", "elevation"]
    return pdk.Layer(
        "HexagonLayer",
        data=data,
        get_position="[lon, lat]",
        get_elevation="elevation",
        elevation_scale=elevation_scale,
        elevation_range=[0, 3000],
        extruded=True,
        radius=200,
        coverage=0.9,
        auto_highlight=True,
        pickable=True,
        opacity=0.6,
        color_range=[
            [0, 255, 100, 180],
            [255, 255, 0, 180],
            [255, 140, 0, 180],
            [255, 60, 0, 180],
            [180, 0, 0, 220],
        ],
    )


def scatter_layer(df: pd.DataFrame, color: list = None) -> pdk.Layer:
    color = color or [0, 180, 255, 180]
    cols = ["latitude", "longitude", "junction_name"]
    cols = [c for c in cols if c in df.columns]
    data = df[cols].dropna(subset=["latitude", "longitude"]).copy()
    if "junction_name" in data.columns:
        data["display_name"] = data["junction_name"]
    else:
        data["display_name"] = "Unknown"
    data = data[["latitude", "longitude", "display_name"]].rename(
        columns={"latitude": "lat", "longitude": "lng"}
    )
    return pdk.Layer(
        "ScatterplotLayer",
        data=data,
        get_position="[lng, lat]",
        get_color=color,
        get_radius=60,
        pickable=True,
        opacity=0.8,
        auto_highlight=True,
    )


def polygon_layer(hotspots: pd.DataFrame) -> pdk.Layer:
    """Hotspot hull polygons coloured by CIS."""
    rows = []
    for _, h in hotspots.iterrows():
        wkt = str(h.get("hull_wkt", ""))
        if not wkt or wkt == "nan":
            continue
        try:
            from shapely import wkt as swkt
            geom = swkt.loads(wkt)
            coords = list(geom.exterior.coords) if hasattr(geom, "exterior") else []
            if not coords:
                continue
            cis = float(h.get("max_cis", 0))
            r = int(min(255, cis * 2.55))
            g = int(max(0, 255 - cis * 2.55))
            rows.append({
                "polygon": [[c[0], c[1]] for c in coords],
                "cis": cis,
                "display_name": h.get("hotspot_name", "Unknown"),
                "fill_color": [r, g, 50, 140],
                "line_color": [r, g, 50, 200],
            })
        except Exception:
            continue
    return pdk.Layer(
        "PolygonLayer",
        data=rows,
        get_polygon="polygon",
        get_fill_color="fill_color",
        get_line_color="line_color",
        line_width_min_pixels=1,
        filled=True,
        stroked=True,
        pickable=True,
        auto_highlight=True,
        opacity=0.4,
    )


def path_layer(route_df: pd.DataFrame) -> pdk.Layer:
    """Patrol route as a path layer."""
    if route_df.empty:
        return pdk.Layer("PathLayer", data=[])
    coords = route_df[["lon", "lat"]].dropna().values.tolist()
    return pdk.Layer(
        "PathLayer",
        data=[{"path": coords, "name": "Patrol Route"}],
        get_path="path",
        get_color=[0, 120, 255, 200],
        width_min_pixels=3,
        pickable=True,
    )


def base_view(center=None, zoom=None) -> pdk.ViewState:
    c = center or MAP_CENTER
    return pdk.ViewState(latitude=c[0], longitude=c[1], zoom=zoom or MAP_ZOOM, pitch=45)
