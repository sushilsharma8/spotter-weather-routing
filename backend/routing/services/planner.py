"""Stateless trip planning and weather assessment."""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from routing.logic.assess import assess_route, classify_clock_hours
from routing.logic.corridor import build_corridor
from routing.logic.geo import haversine_miles, simplify_keep_miles
from routing.logic.ranking import recommend
from routing.logic.sampling import place_checkpoints
from routing.services.geocode import Place, parse_coordinate_query, search_places
from routing.services.routes import RoutingFailure, collect_routes
from routing.services.weather import fetch_series

ASSUMPTIONS = [
    "Wind bands are continuous and are not rounded first: below 25 mph is Low, [25, 35) is Moderate, [35, 45) is High, [45, 55) is Severe, and 55 mph or more is No Travel.",
    "Where published rain or snow ranges share an endpoint, the higher-risk band is used. Rain of exactly 1.00 in/hr and snow depth of exactly 3.0 in/hr stay Severe, because No Travel is strictly above those values.",
    "Load overrides are strict. 30,000 lb and 40,000 lb do not trigger them. Wind from 45 up to 55 mph with load above 30,000 lb is No Travel. Wind from 35 up to 45 mph with load above 40,000 lb is Severe.",
    "Combined checkpoint risk is the highest of load-adjusted wind, rain, and snow. A missing component is Unknown. Unknown is never stored as Low.",
    "Each segment takes the higher risk of its two endpoints, so both the departure weather and the arrival weather affect the miles between them. Category miles partition the geometry length. Average risk uses Low=1, Moderate=2, High=3, Severe=4, No Travel=5, weighted by miles.",
    "A route with any No Travel or Unknown miles stays on the map and is left out of the recommendation. If every route is ineligible, nothing is recommended.",
    "Eligible routes are ordered by fewest Severe miles, then fewest High miles, then lowest average risk, then shortest engine travel time.",
    "Checkpoint clocks follow the routing engine's elapsed driving time along the actual geometry. Weather is linearly interpolated between hourly forecast values at that ETA and is not extrapolated past the forecast.",
    "Snowfall is snow-depth intensity, not liquid water equivalent. An hourly forecast total is treated as the average intensity for that hour.",
    "The 0–48 hour slider is a clock offset from departure for the corridor heatmap. It is not the truck's position. Checkpoint colors use driving ETAs, which can differ from the slider hour.",
    "Weather requests are snapped to a 0.01 degree cell so nearby points share one forecast. Public forecast models are coarser than that.",
    "Driving routes are car profiles. They are not certified truck routes and do not apply truck road restrictions.",
]

RISK_SCALE = {
    "0": "unknown",
    "1": "low",
    "2": "moderate",
    "3": "high",
    "4": "severe",
    "5": "no_travel",
}


class PlanError(Exception):
    def __init__(self, message: str, status: int = 400, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.details = details or {}


def parse_departure(value: str, timezone_name: str) -> datetime:
    if not isinstance(value, str) or "T" not in value:
        raise PlanError("Departure must be a local date and time.")
    raw = value.strip()
    tail = raw[10:]
    if "Z" in tail or "+" in tail or "-" in tail:
        raise PlanError("Send departure as a wall-clock time without an offset. The timezone field applies to it.")
    try:
        naive = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise PlanError("Departure is not a valid date and time.") from exc
    if naive.tzinfo is not None:
        raise PlanError("Departure must not include a timezone offset.")
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise PlanError(f"Unknown timezone: {timezone_name}.") from exc
    aware = naive.replace(tzinfo=zone)
    round_trip = aware.astimezone(timezone.utc).astimezone(zone)
    if round_trip.replace(tzinfo=None) != naive:
        folded = naive.replace(tzinfo=zone, fold=1)
        folded_back = folded.astimezone(timezone.utc).astimezone(zone)
        if folded_back.replace(tzinfo=None) == naive:
            return folded
        raise PlanError("That departure time does not exist in the selected timezone (daylight-saving gap).")
    return aware


def _number(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PlanError(f"{name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise PlanError(f"{name} must be a finite number.")
    return number


def _spacing(value) -> int:
    number = _number(value, "Checkpoint spacing")
    if number not in {10, 25, 50}:
        raise PlanError("Checkpoint spacing must be 10, 25, or 50 miles.")
    return int(number)


def _load(value) -> float:
    number = _number(value, "Load weight")
    if number < 0 or number > 200_000:
        raise PlanError("Load weight must be between 0 and 200,000 lb.")
    return number


def _place_from_input(value, name: str, fetch) -> tuple[Place, list[Place]]:
    if isinstance(value, str):
        query = value.strip()
        point = None
        label = None
    elif isinstance(value, dict):
        query = str(value.get("query") or value.get("label") or "").strip()
        label = value.get("label")
        lat = value.get("lat")
        lon = value.get("lon")
        point = None
        if lat is not None or lon is not None:
            lat_f = _number(lat, f"{name} latitude")
            lon_f = _number(lon, f"{name} longitude")
            if not (-90 <= lat_f <= 90 and -180 <= lon_f <= 180):
                raise PlanError(f"{name} coordinates are out of range.")
            point = (lat_f, lon_f)
    else:
        raise PlanError(f"{name} must be a place name or coordinates.")
    if point is not None:
        place = Place(label=str(label or query or f"{point[0]:.4f}, {point[1]:.4f}"), lat=point[0], lon=point[1], query=query)
        return place, []
    if not query:
        raise PlanError(f"Enter {name.lower()}.")
    direct = parse_coordinate_query(query)
    if direct is not None:
        return direct, []
    matches = search_places(query, fetch=fetch, limit=5)
    if not matches:
        raise PlanError(f"No match for {name.lower()} \"{query}\". Try a city, address, or lat, lon pair.", status=422)
    return matches[0], matches[1:4]


def _place_json(place: Place) -> dict:
    return {"label": place.label, "lat": place.lat, "lon": place.lon, "query": place.query}


def _simplify_route(route):
    cumulative = route.cumulative_miles()
    coords, miles = route.coords, cumulative
    for epsilon in (40, 90, 180):
        coords, miles = simplify_keep_miles(route.coords, cumulative, epsilon)
        if len(coords) <= 1800:
            break
    return [[round(lon, 5), round(lat, 5)] for lon, lat in coords], [round(mile, 4) for mile in miles]


def plan_trip(payload: dict, fetch=None) -> dict:
    if not isinstance(payload, dict):
        raise PlanError("Request body must be a JSON object.")
    fetch_json = fetch
    spacing = _spacing(payload.get("spacing_miles"))
    load_lb = _load(payload.get("load_lb"))
    timezone_name = str(payload.get("timezone") or "").strip()
    if not timezone_name:
        raise PlanError("Choose a timezone. Departure is read in that zone, not from the browser clock.")
    departure = parse_departure(str(payload.get("departure") or ""), timezone_name)
    origin, origin_alts = _place_from_input(payload.get("origin"), "Origin", fetch_json or _default_fetch())
    destination, destination_alts = _place_from_input(payload.get("destination"), "Destination", fetch_json or _default_fetch())
    apart = haversine_miles(origin.lon, origin.lat, destination.lon, destination.lat)
    if apart < 1:
        raise PlanError("Origin and destination resolve to the same place.")
    try:
        routes, notes, provider_errors = collect_routes(
            (origin.lat, origin.lon),
            (destination.lat, destination.lon),
            fetch_json or _default_fetch(),
        )
    except RoutingFailure as exc:
        raise PlanError(str(exc), status=502, details={"providers": []}) from exc
    letters = "ABCDEFGH"
    prepared = []
    corridor_input = []
    for index, route in enumerate(routes):
        checkpoints = place_checkpoints(route.coords, route.edge_miles, route.edge_seconds, spacing)
        geometry, geometry_miles = _simplify_route(route)
        cumulative = route.cumulative_miles()
        corridor_input.append((route.coords, cumulative))
        prepared.append(
            {
                "id": letters[index],
                "provider": route.provider,
                "kind": route.kind,
                "profile": route.profile,
                "road_name": route.road_name,
                "timing": route.timing,
                "truck_restrictions": False,
                "has_toll": route.has_toll,
                "has_highway": route.has_highway,
                "via": route.via,
                "distance_miles": route.distance_miles,
                "engine_distance_miles": route.engine_distance_miles,
                "duration_seconds": route.duration_seconds,
                "geometry": {"coordinates": geometry, "miles": geometry_miles},
                "checkpoints": [
                    {
                        "index": point.index,
                        "mile": point.mile,
                        "lat": point.lat,
                        "lon": point.lon,
                        "elapsed_seconds": point.elapsed_seconds,
                        "is_origin": point.is_origin,
                        "is_destination": point.is_destination,
                    }
                    for point in checkpoints
                ],
            }
        )
    corridor = build_corridor(corridor_input)
    return {
        "plan_id": uuid.uuid4().hex,
        "origin": _place_json(origin),
        "destination": _place_json(destination),
        "origin_alternatives": [_place_json(place) for place in origin_alts],
        "destination_alternatives": [_place_json(place) for place in destination_alts],
        "departure": departure.isoformat(),
        "timezone": timezone_name,
        "load_lb": load_lb,
        "spacing_miles": spacing,
        "routes": prepared,
        "route_count": len(prepared),
        "notes": notes,
        "provider_errors": provider_errors,
        "assumptions": ASSUMPTIONS,
        "corridor": {
            "sample_spacing_miles": corridor.sample_spacing_miles,
            "points": [{"lat": lat, "lon": lon} for lat, lon in corridor.points],
        },
    }


def assess_trip(payload: dict, fetch=None) -> dict:
    if not isinstance(payload, dict):
        raise PlanError("Request body must be a JSON object.")
    load_lb = _load(payload.get("load_lb"))
    timezone_name = str(payload.get("timezone") or "").strip()
    departure = parse_departure(str(payload.get("departure") or ""), timezone_name)
    routes = payload.get("routes")
    if not isinstance(routes, list) or not routes:
        raise PlanError("Assessment needs the planned routes.")
    flat_points: list[tuple[float, float]] = []
    spans: list[tuple[int, int]] = []
    latest = departure
    for route in routes:
        checkpoints = route.get("checkpoints") or []
        start = len(flat_points)
        for checkpoint in checkpoints:
            lat = _number(checkpoint.get("lat"), "Checkpoint latitude")
            lon = _number(checkpoint.get("lon"), "Checkpoint longitude")
            elapsed = _number(checkpoint.get("elapsed_seconds"), "Checkpoint elapsed time")
            flat_points.append((lat, lon))
            eta = departure + timedelta(seconds=elapsed)
            if eta > latest:
                latest = eta
        spans.append((start, len(flat_points)))
    window_end = max(latest, departure + timedelta(hours=48))
    series = fetch_series(
        flat_points,
        departure - timedelta(hours=2),
        window_end + timedelta(hours=2),
        fetch or _default_fetch(),
    )
    assessed = []
    ranked = []
    unavailable = 0
    for index, route in enumerate(routes):
        start, end = spans[index]
        result = assess_route(
            route_id=str(route.get("id") or index),
            index=index,
            duration_seconds=_number(route.get("duration_seconds") or 0, "Duration"),
            departure=departure,
            checkpoints=route.get("checkpoints") or [],
            series=series[start:end],
            load_lb=load_lb,
        )
        ranked.append(result.pop("ranked"))
        for checkpoint in result["checkpoints"]:
            if checkpoint["risk"] == "unknown":
                unavailable += 1
        assessed.append({"id": str(route.get("id") or index), **result})
    recommendation = recommend(ranked)
    warning = None
    if unavailable:
        warning = (
            f"{unavailable} checkpoint samples are outside the forecast or missing a weather field. "
            "Those miles are Unknown, not Low."
        )
    return {
        "routes": assessed,
        "recommendation": recommendation,
        "warning": warning,
        "criteria": [
            {
                "id": route.route_id,
                "severe_miles": route.severe_miles,
                "high_miles": route.high_miles,
                "average_risk": route.average_risk,
                "duration_seconds": route.duration_seconds,
                "eligible": route.eligible,
                "blockers": list(route.blockers),
            }
            for route in ranked
        ],
    }


def corridor_weather(payload: dict, fetch=None) -> dict:
    if not isinstance(payload, dict):
        raise PlanError("Request body must be a JSON object.")
    load_lb = _load(payload.get("load_lb"))
    timezone_name = str(payload.get("timezone") or "").strip()
    departure = parse_departure(str(payload.get("departure") or ""), timezone_name)
    raw_points = payload.get("points")
    if not isinstance(raw_points, list) or not raw_points:
        raise PlanError("The corridor needs sample points.")
    if len(raw_points) > 250:
        raise PlanError("Corridor sample is too large.")
    points = []
    for point in raw_points:
        points.append((_number(point.get("lat"), "Latitude"), _number(point.get("lon"), "Longitude")))
    series = fetch_series(
        points,
        departure - timedelta(hours=2),
        departure + timedelta(hours=50),
        fetch or _default_fetch(),
    )
    hours = None
    rendered = []
    unknown_hours = 0
    for (lat, lon), point_series in zip(points, series):
        classified = classify_clock_hours(point_series, departure, load_lb, hours=49)
        hours = classified["times"]
        if all(value == 0 for value in classified["risk"]):
            unknown_hours += 1
        rendered.append({"lat": lat, "lon": lon, **{key: classified[key] for key in ("risk", "wind_mph", "rain_in_hr", "snow_in_hr")}})
    warning = None
    if unknown_hours == len(rendered):
        warning = "No forecast is available for this departure window. The corridor is marked Unknown, not calm."
    return {
        "times": hours or [],
        "hour_count": 49,
        "risk_scale": RISK_SCALE,
        "points": rendered,
        "warning": warning,
        "note": "Each hour is departure plus that many clock hours, including load rules. It is not the truck's ETA.",
    }


def _default_fetch():
    from routing.services.http import http_json

    return http_json
