"""
routing.py – OR-Tools VRP/TSP patrol route over top-N hotspots weighted by CIS.
"""
import logging

import numpy as np
import pandas as pd

from parkiq.config import (
    TOP_N_HOTSPOTS_ROUTE, NUM_PATROL_TEAMS, ROUTE_TIME_LIMIT_SEC,
)

logger = logging.getLogger(__name__)


def _haversine_m(lat1, lon1, lat2, lon2):
    R = 6_371_000
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlam = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlam / 2) ** 2
    return R * 2 * np.arcsin(np.sqrt(a))


def _build_distance_matrix(lats, lons):
    n = len(lats)
    mat = np.zeros((n, n), dtype=int)
    for i in range(n):
        for j in range(n):
            if i != j:
                mat[i][j] = int(_haversine_m(lats[i], lons[i], lats[j], lons[j]))
    return mat.tolist()


def plan_patrol(hotspots: pd.DataFrame) -> pd.DataFrame:
    """
    Select top-N hotspots by max_cis and compute an OR-Tools VRP route.
    Falls back to CIS-sorted list if OR-Tools is unavailable.

    Returns a DataFrame with: stop_order, hotspot_name, lat, lon, cis, team.
    """
    if hotspots.empty:
        return pd.DataFrame()

    top = (
        hotspots.nlargest(TOP_N_HOTSPOTS_ROUTE, "max_cis")
        .reset_index(drop=True)
    )

    lats = top["lat_centroid"].values
    lons = top["lon_centroid"].values

    # Add depot (city centre) at index 0
    DEPOT_LAT, DEPOT_LON = 12.9716, 77.5946  # Bengaluru city centre
    all_lats = np.concatenate([[DEPOT_LAT], lats])
    all_lons = np.concatenate([[DEPOT_LON], lons])

    try:
        route = _ortools_route(all_lats, all_lons)
    except Exception as e:
        logger.warning("OR-Tools routing failed (%s) – using greedy fallback", e)
        route = list(range(1, len(all_lats)))  # greedy: visit in CIS order

    # Build output (skip depot index 0)
    rows = []
    for stop_idx, node in enumerate(route):
        if node == 0:
            continue
        h_idx = node - 1
        rows.append(dict(
            stop_order   = stop_idx,
            hotspot_name = top.iloc[h_idx].get("hotspot_name", f"Zone-{h_idx}"),
            lat          = float(lats[h_idx]),
            lon          = float(lons[h_idx]),
            cis          = float(top.iloc[h_idx]["max_cis"]),
            team         = (stop_idx % NUM_PATROL_TEAMS) + 1,
        ))
    return pd.DataFrame(rows)


def _ortools_route(lats, lons):
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2

    dist_matrix = _build_distance_matrix(lats, lons)
    n = len(lats)
    manager = pywrapcp.RoutingIndexManager(n, NUM_PATROL_TEAMS, 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        fi = manager.IndexToNode(from_index)
        ti = manager.IndexToNode(to_index)
        return dist_matrix[fi][ti]

    transit_idx = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)
    routing.AddDimension(transit_idx, 0, 10_000_000, True, "Distance")
    dist_dimension = routing.GetDimensionOrDie("Distance")
    dist_dimension.SetGlobalSpanCostCoefficient(100)

    search_params = pywrapcp.DefaultRoutingSearchParameters()
    search_params.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_params.time_limit.seconds = ROUTE_TIME_LIMIT_SEC

    solution = routing.SolveWithParameters(search_params)
    if not solution:
        raise RuntimeError("No solution found")

    route_nodes = []
    for vehicle_id in range(NUM_PATROL_TEAMS):
        index = routing.Start(vehicle_id)
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            route_nodes.append(node)
            index = solution.Value(routing.NextVar(index))
    return route_nodes
