"""Geometry helpers. Distances use a spherical Earth of 6,371 km."""

from __future__ import annotations

import math

EARTH_M = 6_371_000.0
METERS_PER_MILE = 1609.344


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return EARTH_M * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))


def haversine_miles(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    return haversine_m(lon1, lat1, lon2, lat2) / METERS_PER_MILE


def bearing_deg(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlmb = math.radians(lon2 - lon1)
    y = math.sin(dlmb) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlmb)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def destination(lon: float, lat: float, bearing: float, distance_m: float) -> tuple[float, float]:
    ang = distance_m / EARTH_M
    theta = math.radians(bearing)
    phi1 = math.radians(lat)
    lam1 = math.radians(lon)
    phi2 = math.asin(math.sin(phi1) * math.cos(ang) + math.cos(phi1) * math.sin(ang) * math.cos(theta))
    lam2 = lam1 + math.atan2(
        math.sin(theta) * math.sin(ang) * math.cos(phi1),
        math.cos(ang) - math.sin(phi1) * math.sin(phi2),
    )
    return math.degrees(lam2), math.degrees(phi2)


def interpolate(lon1: float, lat1: float, lon2: float, lat2: float, fraction: float) -> tuple[float, float]:
    t = min(1.0, max(0.0, fraction))
    return lon1 + (lon2 - lon1) * t, lat1 + (lat2 - lat1) * t


def decode_polyline(encoded: str, precision: int = 6) -> list[tuple[float, float]]:
    """Decode an encoded polyline to (lon, lat) pairs."""
    index = 0
    lat = 0
    lon = 0
    factor = 10**precision
    coords: list[tuple[float, float]] = []
    length = len(encoded)
    while index < length:
        for coord in (0, 1):
            shift = 0
            result = 0
            while True:
                if index >= length:
                    raise ValueError("Truncated polyline.")
                chunk = ord(encoded[index]) - 63
                index += 1
                result |= (chunk & 0x1F) << shift
                shift += 5
                if chunk < 0x20:
                    break
            delta = ~(result >> 1) if (result & 1) else (result >> 1)
            if coord == 0:
                lat += delta
            else:
                lon += delta
        coords.append((lon / factor, lat / factor))
    return coords


def encode_polyline(coords: list[tuple[float, float]], precision: int = 6) -> str:
    """Encode (lon, lat) pairs. Used by tests and not by the live routing path."""
    factor = 10**precision
    prev_lat = 0
    prev_lon = 0
    out: list[str] = []

    def _encode(value: int) -> None:
        value = ~(value << 1) if value < 0 else (value << 1)
        while value >= 0x20:
            out.append(chr((0x20 | (value & 0x1F)) + 63))
            value >>= 5
        out.append(chr(value + 63))

    for lon, lat in coords:
        ilat = int(round(lat * factor))
        ilon = int(round(lon * factor))
        _encode(ilat - prev_lat)
        _encode(ilon - prev_lon)
        prev_lat, prev_lon = ilat, ilon
    return "".join(out)


def point_segment_miles(
    lon: float,
    lat: float,
    lon1: float,
    lat1: float,
    lon2: float,
    lat2: float,
) -> float:
    """Approximate miles from a point to a short segment, in a local projection."""
    lat0 = math.radians(lat1)
    scale_x = math.cos(lat0) * EARTH_M / METERS_PER_MILE
    scale_y = EARTH_M / METERS_PER_MILE

    def xy(lo: float, la: float) -> tuple[float, float]:
        return math.radians(lo - lon1) * scale_x, math.radians(la - lat1) * scale_y

    px, py = xy(lon, lat)
    bx, by = xy(lon2, lat2)
    denom = bx * bx + by * by
    if denom <= 1e-12:
        return math.hypot(px, py)
    t = max(0.0, min(1.0, (px * bx + py * by) / denom))
    return math.hypot(px - t * bx, py - t * by)


def cumulative_miles(coords: list[tuple[float, float]]) -> list[float]:
    miles = [0.0]
    for index in range(len(coords) - 1):
        lon1, lat1 = coords[index]
        lon2, lat2 = coords[index + 1]
        miles.append(miles[-1] + haversine_miles(lon1, lat1, lon2, lat2))
    return miles


def simplify_keep_miles(
    coords: list[tuple[float, float]],
    miles: list[float],
    epsilon_m: float,
) -> tuple[list[tuple[float, float]], list[float]]:
    """Douglas-Peucker. Kept vertices retain their original route miles."""
    count = len(coords)
    if count <= 2:
        return list(coords), list(miles)
    keep = [False] * count
    keep[0] = True
    keep[-1] = True
    stack = [(0, count - 1)]
    limit = epsilon_m / METERS_PER_MILE
    while stack:
        start, end = stack.pop()
        if end <= start + 1:
            continue
        farthest = -1.0
        farthest_at = None
        lon1, lat1 = coords[start]
        lon2, lat2 = coords[end]
        for index in range(start + 1, end):
            lon, lat = coords[index]
            distance = point_segment_miles(lon, lat, lon1, lat1, lon2, lat2)
            if distance > farthest:
                farthest = distance
                farthest_at = index
        if farthest_at is not None and farthest > limit:
            keep[farthest_at] = True
            stack.append((start, farthest_at))
            stack.append((farthest_at, end))
    kept_coords = [coord for coord, flag in zip(coords, keep) if flag]
    kept_miles = [mile for mile, flag in zip(miles, keep) if flag]
    return kept_coords, kept_miles
