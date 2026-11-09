"""Sample a weather corridor around the routed geometry.

Points sit on the roads and on short perpendicular offsets so the heatmap
follows the trip, rather than filling the whole bounding box of a long haul.
"""

from __future__ import annotations

from dataclasses import dataclass

from routing.logic.geo import bearing_deg, destination, interpolate


@dataclass(frozen=True)
class CorridorPlan:
    points: list[tuple[float, float]]  # (lat, lon)
    sample_spacing_miles: float


def _point_at(coords: list[tuple[float, float]], miles: list[float], target: float) -> tuple[float, float, float]:
    if target <= 0:
        bearing = bearing_deg(coords[0][0], coords[0][1], coords[1][0], coords[1][1]) if len(coords) > 1 else 0.0
        return coords[0][0], coords[0][1], bearing
    total = miles[-1]
    if target >= total:
        bearing = bearing_deg(coords[-2][0], coords[-2][1], coords[-1][0], coords[-1][1]) if len(coords) > 1 else 0.0
        return coords[-1][0], coords[-1][1], bearing
    index = 1
    while index < len(miles) - 1 and miles[index] < target:
        index += 1
    span = miles[index] - miles[index - 1]
    fraction = 0.0 if span <= 1e-9 else (target - miles[index - 1]) / span
    lon, lat = interpolate(coords[index - 1][0], coords[index - 1][1], coords[index][0], coords[index][1], fraction)
    bearing = bearing_deg(coords[index - 1][0], coords[index - 1][1], coords[index][0], coords[index][1])
    return lon, lat, bearing


def build_corridor(
    routes: list[tuple[list[tuple[float, float]], list[float]]],
    cap: int = 170,
) -> CorridorPlan:
    """`routes` entries are (lon/lat coords, cumulative miles)."""
    if not routes:
        return CorridorPlan([], 20.0)
    primary_total = routes[0][1][-1] if routes[0][1] else 0.0
    step = max(8.0, min(22.0, primary_total / 14.0 if primary_total else 12.0))
    offset = max(6.0, min(18.0, (primary_total or 40.0) * 0.06))
    points: list[tuple[float, float]] = []
    seen: set[tuple[float, float]] = set()

    def add(lat: float, lon: float) -> None:
        if len(points) >= cap:
            return
        key = (round(lat, 2), round(lon, 2))
        if key in seen:
            return
        seen.add(key)
        points.append((lat, lon))

    for coords, miles in routes:
        if len(coords) < 2 or not miles:
            continue
        total = miles[-1]
        cursor = 0.0
        while cursor <= total + 1e-6 and len(points) < cap:
            lon, lat, bearing = _point_at(coords, miles, min(cursor, total))
            add(lat, lon)
            for sign in (-1.0, 1.0):
                for scale in (0.65, 1.25):
                    shifted_lon, shifted_lat = destination(
                        lon,
                        lat,
                        bearing + 90.0 * sign,
                        offset * scale * 1609.344,
                    )
                    add(shifted_lat, shifted_lon)
            cursor += step
    return CorridorPlan(points[:cap], round(step, 2))
