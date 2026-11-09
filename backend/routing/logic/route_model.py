"""Normalized engine routes and distinctness checks."""

from __future__ import annotations

from dataclasses import dataclass, field

from routing.logic.geo import cumulative_miles, point_segment_miles


@dataclass
class NormalizedRoute:
    provider: str
    kind: str
    profile: str
    road_name: str | None
    coords: list[tuple[float, float]]
    edge_miles: list[float]
    edge_seconds: list[float]
    duration_seconds: float
    engine_distance_miles: float
    has_toll: bool | None = None
    has_highway: bool | None = None
    via: dict | None = None
    timing: str = "engine"
    spine: list[tuple[float, float]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.spine:
            self.spine = _spine(self.coords, self.cumulative_miles())

    @property
    def distance_miles(self) -> float:
        return sum(self.edge_miles)

    def cumulative_miles(self) -> list[float]:
        miles = [0.0]
        for edge in self.edge_miles:
            miles.append(miles[-1] + edge)
        return miles


def _spine(coords: list[tuple[float, float]], miles: list[float], step: float = 2.0) -> list[tuple[float, float]]:
    if len(coords) < 2:
        return list(coords)
    kept = [coords[0]]
    next_mark = step
    total = miles[-1]
    for index in range(1, len(coords)):
        if miles[index] >= next_mark or index == len(coords) - 1:
            kept.append(coords[index])
            while next_mark <= miles[index]:
                next_mark += step
        if miles[index] >= total:
            break
    if kept[-1] != coords[-1]:
        kept.append(coords[-1])
    return kept


def distance_to_route_miles(lon: float, lat: float, route: NormalizedRoute) -> float:
    spine = route.spine or route.coords
    if not spine:
        return 1e9
    if len(spine) == 1:
        only = spine[0]
        return point_segment_miles(lon, lat, only[0], only[1], only[0], only[1])
    best = 1e9
    for index in range(len(spine) - 1):
        distance = point_segment_miles(lon, lat, spine[index][0], spine[index][1], spine[index + 1][0], spine[index + 1][1])
        if distance < best:
            best = distance
    return best


def overlap_ratio(candidate: NormalizedRoute, other: NormalizedRoute, near_miles: float = 3.0) -> float:
    samples = candidate.spine
    if not samples:
        return 1.0
    close = 0
    for lon, lat in samples:
        if distance_to_route_miles(lon, lat, other) <= near_miles:
            close += 1
    return close / len(samples)


def is_distinct(candidate: NormalizedRoute, existing: list[NormalizedRoute], threshold: float = 0.8) -> bool:
    for other in existing:
        forward = overlap_ratio(candidate, other)
        backward = overlap_ratio(other, candidate)
        if forward >= threshold and backward >= threshold:
            return False
    return True


def dedupe_routes(routes: list[NormalizedRoute]) -> list[NormalizedRoute]:
    kept: list[NormalizedRoute] = []
    for route in routes:
        if is_distinct(route, kept):
            kept.append(route)
    return kept


def geometry_miles(coords: list[tuple[float, float]]) -> list[float]:
    cumulative = cumulative_miles(coords)
    return [cumulative[index + 1] - cumulative[index] for index in range(len(cumulative) - 1)]
