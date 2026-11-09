"""Keyless geocoding. Photon first, Nominatim if Photon is unavailable.

A `lat, lon` string is accepted directly and is not sent to a geocoder.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote

from routing.services.http import HttpError, http_json

COORD_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


@dataclass(frozen=True)
class Place:
    label: str
    lat: float
    lon: float
    query: str
    rank: int = 3


def _valid_coord(lat: float, lon: float) -> bool:
    return -90 <= lat <= 90 and -180 <= lon <= 180


def parse_coordinate_query(query: str) -> Place | None:
    match = COORD_RE.match(query.strip())
    if not match:
        return None
    lat = float(match.group(1))
    lon = float(match.group(2))
    if not _valid_coord(lat, lon):
        return None
    label = f"{lat:.4f}, {lon:.4f}"
    return Place(label=label, lat=lat, lon=lon, query=query.strip())


def _place_rank(props: dict) -> int:
    key = str(props.get("osm_key") or props.get("type") or "").lower()
    value = str(props.get("osm_value") or props.get("addresstype") or "").lower()
    if value in {"city", "town", "village", "municipality", "hamlet", "locality"}:
        return 0
    if key in {"place", "boundary"} or value in {"administrative", "county", "state"}:
        return 1
    if key in {"highway", "aeroway"}:
        return 2
    if key in {"amenity", "tourism", "shop", "office", "leisure", "historic", "building", "craft"}:
        return 5
    return 3


def choose_matches(places: list[Place], limit: int = 5) -> list[Place]:
    """Prefer cities over points of interest when both match the query."""
    ordered = sorted(enumerate(places), key=lambda item: (item[1].rank, item[0]))
    ranked = [place for _index, place in ordered]
    if any(place.rank <= 1 for place in ranked):
        ranked = [place for place in ranked if place.rank <= 1]
    unique: list[Place] = []
    seen: set[str] = set()
    for place in ranked:
        key = place.label.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(place)
    return unique[:limit]


def _photon_label(props: dict) -> str:
    parts: list[str] = []
    name = props.get("name") or props.get("street")
    if name:
        parts.append(str(name))
    locality = props.get("city") or props.get("county")
    if locality and locality not in parts:
        parts.append(str(locality))
    state = props.get("state")
    if state:
        parts.append(str(state))
    country = props.get("country")
    if country and country not in {"United States", "USA", "United States of America"}:
        parts.append(str(country))
    return ", ".join(parts) or "Unnamed place"


def _nominatim_label(item: dict) -> str:
    return item.get("display_name") or "Unnamed place"


def search_places(query: str, fetch=http_json, limit: int = 5) -> list[Place]:
    text = query.strip()
    if len(text) < 2:
        return []
    direct = parse_coordinate_query(text)
    if direct is not None:
        return [direct]
    encoded = quote(text)
    photon_url = f"https://photon.komoot.io/api/?q={encoded}&limit=10&lang=en"
    try:
        payload = fetch(photon_url, timeout=8)
    except (HttpError, TimeoutError, OSError):
        payload = None
    places: list[Place] = []
    if isinstance(payload, dict) and not payload.get("error"):
        for feature in payload.get("features") or []:
            geometry = feature.get("geometry") or {}
            coords = geometry.get("coordinates") or []
            if len(coords) < 2:
                continue
            lon, lat = float(coords[0]), float(coords[1])
            if not _valid_coord(lat, lon):
                continue
            props = feature.get("properties") or {}
            places.append(Place(_photon_label(props), lat, lon, text, _place_rank(props)))
        if places:
            return choose_matches(places, limit)
    nominatim_url = (
        "https://nominatim.openstreetmap.org/search"
        f"?q={encoded}&format=jsonv2&limit={limit}&addressdetails=1"
    )
    try:
        payload = fetch(nominatim_url, timeout=8)
    except (HttpError, TimeoutError, OSError):
        return []
    if not isinstance(payload, list):
        return []
    for item in payload:
        try:
            lat = float(item["lat"])
            lon = float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if not _valid_coord(lat, lon):
            continue
        places.append(Place(_nominatim_label(item), lat, lon, text, _place_rank(item)))
    return choose_matches(places, limit)
