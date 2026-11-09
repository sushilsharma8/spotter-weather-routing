"""Checkpoint placement and duration-based ETAs.

Miles are measured along the routed geometry. Time at a mile is interpolated
from the routing engine's per-edge driving durations, then scaled so the
destination ETA matches the engine's total duration. A constant truck speed
is not assumed.

The destination is always a checkpoint. A final spacing point that would land
within 0.05 miles of the destination is replaced by the destination so the
remainder is a single segment.
"""

from __future__ import annotations

from dataclasses import dataclass

from routing.logic.geo import interpolate


@dataclass(frozen=True)
class Checkpoint:
    index: int
    mile: float
    lon: float
    lat: float
    elapsed_seconds: float
    is_origin: bool
    is_destination: bool


def checkpoint_miles(total_miles: float, spacing_miles: float) -> list[float]:
    if spacing_miles <= 0:
        raise ValueError("Spacing must be positive.")
    if total_miles <= 0.02:
        if total_miles <= 0:
            return [0.0]
        return [0.0, total_miles]
    miles = [0.0]
    cursor = float(spacing_miles)
    while cursor < total_miles - 0.05:
        miles.append(cursor)
        cursor += spacing_miles
    if total_miles - miles[-1] > 0.02:
        miles.append(total_miles)
    else:
        miles[-1] = total_miles
    return miles


def scale_durations(durations: list[float], target_seconds: float) -> list[float]:
    cleaned = [max(0.0, float(value)) for value in durations]
    total = sum(cleaned)
    if total <= 0 or target_seconds <= 0:
        return cleaned
    factor = target_seconds / total
    return [value * factor for value in cleaned]


def place_checkpoints(
    coords: list[tuple[float, float]],
    edge_miles: list[float],
    edge_seconds: list[float],
    spacing_miles: float,
) -> list[Checkpoint]:
    if len(coords) < 2:
        raise ValueError("A route needs at least two coordinates.")
    if len(edge_miles) != len(coords) - 1 or len(edge_seconds) != len(coords) - 1:
        raise ValueError("Edge metrics must match the coordinate segments.")

    cumulative_miles = [0.0]
    cumulative_seconds = [0.0]
    for miles, seconds in zip(edge_miles, edge_seconds):
        cumulative_miles.append(cumulative_miles[-1] + max(0.0, miles))
        cumulative_seconds.append(cumulative_seconds[-1] + max(0.0, seconds))
    total_miles = cumulative_miles[-1]
    total_seconds = cumulative_seconds[-1]
    targets = checkpoint_miles(total_miles, spacing_miles)

    checkpoints: list[Checkpoint] = []
    edge_index = 0
    last_edge = len(coords) - 2
    for position, target in enumerate(targets):
        origin = position == 0
        destination = position == len(targets) - 1
        if origin:
            checkpoints.append(
                Checkpoint(position, 0.0, coords[0][0], coords[0][1], 0.0, True, destination)
            )
            continue
        if destination:
            checkpoints.append(
                Checkpoint(
                    position,
                    total_miles,
                    coords[-1][0],
                    coords[-1][1],
                    total_seconds,
                    False,
                    True,
                )
            )
            continue
        while edge_index < last_edge and cumulative_miles[edge_index + 1] < target - 1e-9:
            edge_index += 1
        start_miles = cumulative_miles[edge_index]
        end_miles = cumulative_miles[edge_index + 1]
        span = end_miles - start_miles
        fraction = 0.0 if span <= 1e-12 else (target - start_miles) / span
        fraction = min(1.0, max(0.0, fraction))
        lon, lat = interpolate(
            coords[edge_index][0],
            coords[edge_index][1],
            coords[edge_index + 1][0],
            coords[edge_index + 1][1],
            fraction,
        )
        elapsed = cumulative_seconds[edge_index] + (
            cumulative_seconds[edge_index + 1] - cumulative_seconds[edge_index]
        ) * fraction
        checkpoints.append(Checkpoint(position, target, lon, lat, elapsed, False, False))
    return checkpoints
