"""Real routing through public Valhalla and OSRM car profiles.

These engines do not enforce truck height, weight, or restricted-road rules.
Geometry and driving time come from the engine. If fewer than three distinct
routes come back, additional options are requested through the same engines
using intermediate via points. Nothing is drawn by hand, and duplicates are
not relabeled as extra routes.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from routing.logic.geo import decode_polyline, destination, haversine_miles
from routing.logic.route_model import NormalizedRoute, dedupe_routes, geometry_miles, is_distinct
from routing.logic.sampling import scale_durations
from routing.services.http import HttpError, http_json

VALHALLA_URL = "https://valhalla1.openstreetmap.de/route"
OSRM_HOSTS = (
    "https://router.project-osrm.org",
    "https://routing.openstreetmap.de/routed-car",
)


class RoutingFailure(Exception):
    pass


def _dominant_road(maneuvers: list[dict]) -> str | None:
    totals: dict[str, float] = {}
    for maneuver in maneuvers:
        length = float(maneuver.get("length") or 0)
        for name in maneuver.get("street_names") or []:
            if not name:
                continue
            totals[str(name)] = totals.get(str(name), 0.0) + length
    if not totals:
        return None
    return max(totals, key=totals.get)


def _edges_from_maneuvers(coords: list[tuple[float, float]], maneuvers: list[dict], total_seconds: float):
    miles = geometry_miles(coords)
    seconds = [0.0] * len(miles)
    if not maneuvers or not miles:
        return miles, scale_durations([mile for mile in miles], total_seconds), "distance-proportional-fallback"
    for maneuver in maneuvers:
        begin = int(maneuver.get("begin_shape_index") or 0)
        end = int(maneuver.get("end_shape_index") or begin)
        begin = max(0, min(begin, len(miles)))
        end = max(begin, min(end, len(miles)))
        span = miles[begin:end]
        span_sum = sum(span)
        allotted = max(0.0, float(maneuver.get("time") or 0))
        if not span:
            continue
        if span_sum <= 1e-9:
            seconds[begin] += allotted
            continue
        for offset, edge_miles in enumerate(span):
            seconds[begin + offset] += allotted * (edge_miles / span_sum)
    return miles, scale_durations(seconds, total_seconds), "engine-maneuver"


def parse_valhalla_trip(trip: dict, kind: str, via: dict | None = None) -> NormalizedRoute:
    coords: list[tuple[float, float]] = []
    miles: list[float] = []
    seconds: list[float] = []
    maneuvers: list[dict] = []
    timing = "engine-maneuver"
    for leg in trip.get("legs") or []:
        leg_coords = decode_polyline(leg.get("shape") or "", precision=6)
        if len(leg_coords) < 2:
            continue
        leg_summary = leg.get("summary") or {}
        leg_miles, leg_seconds, leg_timing = _edges_from_maneuvers(
            leg_coords,
            leg.get("maneuvers") or [],
            float(leg_summary.get("time") or trip.get("summary", {}).get("time") or 0),
        )
        timing = leg_timing
        if coords:
            join_distance = haversine_miles(coords[-1][0], coords[-1][1], leg_coords[0][0], leg_coords[0][1])
            if join_distance < 0.03:
                leg_coords = leg_coords[1:]
            else:
                # Keep a connecting edge if the legs do not meet.
                gap = join_distance
                miles.append(gap)
                seconds.append(0.0)
        coords.extend(leg_coords)
        miles.extend(leg_miles)
        seconds.extend(leg_seconds)
        maneuvers.extend(leg.get("maneuvers") or [])
    if len(coords) < 2 or len(miles) != len(coords) - 1:
        raise RoutingFailure("Valhalla returned a route without usable geometry.")
    summary = trip.get("summary") or {}
    engine_seconds = float(summary.get("time") or sum(seconds) or 0)
    seconds = scale_durations(seconds, engine_seconds)
    return NormalizedRoute(
        provider="valhalla",
        kind=kind,
        profile="auto",
        road_name=_dominant_road(maneuvers),
        coords=coords,
        edge_miles=miles,
        edge_seconds=seconds,
        duration_seconds=engine_seconds,
        engine_distance_miles=float(summary.get("length") or sum(miles)),
        has_toll=summary.get("has_toll"),
        has_highway=summary.get("has_highway"),
        via=via,
        timing=timing,
    )


def parse_osrm_route(route: dict, kind: str, via: dict | None = None) -> NormalizedRoute:
    geometry = (route.get("geometry") or {}).get("coordinates") or []
    coords = [(float(pair[0]), float(pair[1])) for pair in geometry if isinstance(pair, (list, tuple)) and len(pair) >= 2]
    annotation_miles: list[float] = []
    annotation_seconds: list[float] = []
    for leg in route.get("legs") or []:
        annotation = leg.get("annotation") or {}
        distances = annotation.get("distance") or []
        durations = annotation.get("duration") or []
        annotation_miles.extend(float(item) / 1609.344 for item in distances)
        annotation_seconds.extend(float(item) for item in durations)
    if len(coords) < 2:
        raise RoutingFailure("OSRM returned a route without usable geometry.")
    miles = geometry_miles(coords)
    engine_seconds = float(route.get("duration") or 0)
    if len(annotation_seconds) == len(miles):
        seconds = scale_durations(annotation_seconds, engine_seconds)
        timing = "engine-annotation"
    else:
        seconds = scale_durations(miles, engine_seconds)
        timing = "distance-proportional-fallback"
    road = None
    return NormalizedRoute(
        provider="osrm",
        kind=kind,
        profile="driving",
        road_name=road,
        coords=coords,
        edge_miles=miles,
        edge_seconds=seconds,
        duration_seconds=engine_seconds,
        engine_distance_miles=float(route.get("distance") or 0) / 1609.344,
        via=via,
        timing=timing,
    )


def _valhalla_locations(points: list[tuple[str, float, float]]) -> list[dict]:
    locations = []
    for kind, lon, lat in points:
        locations.append({"lon": lon, "lat": lat, "type": kind})
    return locations


def fetch_valhalla(origin: tuple[float, float], destination: tuple[float, float], fetch=http_json) -> list[NormalizedRoute]:
    payload = {
        "locations": _valhalla_locations(
            [
                ("break", origin[1], origin[0]),
                ("break", destination[1], destination[0]),
            ]
        ),
        "costing": "auto",
        "alternates": 2,
        "units": "miles",
    }
    body = fetch(VALHALLA_URL, method="POST", payload=payload, timeout=25)
    if not isinstance(body, dict):
        raise RoutingFailure("Valhalla returned an unexpected response.")
    if body.get("error") or body.get("error_code"):
        raise RoutingFailure(str(body.get("error") or body.get("message") or "Valhalla could not route."))
    trip = body.get("trip")
    if not isinstance(trip, dict):
        raise RoutingFailure("Valhalla did not return a trip.")
    routes = [parse_valhalla_trip(trip, "primary")]
    for alternate in body.get("alternates") or []:
        alt_trip = alternate.get("trip") if isinstance(alternate, dict) else None
        if isinstance(alt_trip, dict):
            routes.append(parse_valhalla_trip(alt_trip, "alternate"))
    return routes


def _osrm_path(host: str, points: list[tuple[float, float]], alternatives: bool) -> str:
    # points are (lat, lon)
    encoded = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)
    flag = "true" if alternatives else "false"
    return (
        f"{host}/route/v1/driving/{encoded}"
        f"?overview=full&geometries=geojson&alternatives={flag}&annotations=duration,distance&steps=false"
    )


def fetch_osrm(origin: tuple[float, float], destination: tuple[float, float], fetch=http_json) -> list[NormalizedRoute]:
    errors: list[str] = []
    for host in OSRM_HOSTS:
        url = _osrm_path(host, [origin, destination], alternatives=True)
        try:
            body = fetch(url, timeout=25)
        except (HttpError, TimeoutError, OSError) as exc:
            errors.append(str(exc))
            continue
        if not isinstance(body, dict) or body.get("code") not in (None, "Ok"):
            errors.append(str(body.get("message") or body.get("code") or "OSRM error") if isinstance(body, dict) else "OSRM error")
            continue
        routes = []
        for index, route in enumerate(body.get("routes") or []):
            kind = "primary" if index == 0 else "alternate"
            routes.append(parse_osrm_route(route, kind))
        if routes:
            return routes
    raise RoutingFailure("OSRM could not route. " + " ".join(errors))


def _via_points(route: NormalizedRoute) -> list[dict]:
    total = route.distance_miles
    if total < 30:
        return []
    offset_miles = max(8.0, min(25.0, total * 0.12))
    miles = route.cumulative_miles()
    vias = []
    for fraction, side in ((0.35, -1), (0.35, 1), (0.62, -1), (0.62, 1)):
        target = total * fraction
        lon, lat, bearing = _along(route.coords, miles, target)
        via_lon, via_lat = destination(lon, lat, bearing + 90 * side, offset_miles * 1609.344)
        vias.append({"lat": via_lat, "lon": via_lon, "fraction": fraction, "side": "left" if side < 0 else "right"})
    return vias


def _along(coords, miles, target):
    from routing.logic.geo import bearing_deg, interpolate

    if target <= 0:
        bearing = bearing_deg(coords[0][0], coords[0][1], coords[1][0], coords[1][1])
        return coords[0][0], coords[0][1], bearing
    index = 1
    while index < len(miles) - 1 and miles[index] < target:
        index += 1
    span = miles[index] - miles[index - 1]
    fraction = 0.0 if span <= 1e-9 else (target - miles[index - 1]) / span
    lon, lat = interpolate(coords[index - 1][0], coords[index - 1][1], coords[index][0], coords[index][1], fraction)
    bearing = bearing_deg(coords[index - 1][0], coords[index - 1][1], coords[index][0], coords[index][1])
    return lon, lat, bearing


def _fetch_via(origin, destination, via: dict, fetch) -> NormalizedRoute | None:
    payload = {
        "locations": _valhalla_locations(
            [
                ("break", origin[1], origin[0]),
                ("through", via["lon"], via["lat"]),
                ("break", destination[1], destination[0]),
            ]
        ),
        "costing": "auto",
        "alternates": 0,
        "units": "miles",
    }
    try:
        body = fetch(VALHALLA_URL, method="POST", payload=payload, timeout=22)
    except (HttpError, TimeoutError, OSError):
        body = None
    if isinstance(body, dict) and isinstance(body.get("trip"), dict) and not body.get("error"):
        try:
            route = parse_valhalla_trip(body["trip"], "via", via=via)
            return route
        except RoutingFailure:
            pass
    url = _osrm_path(OSRM_HOSTS[0], [origin, (via["lat"], via["lon"]), destination], alternatives=False)
    try:
        osrm = fetch(url, timeout=22)
    except (HttpError, TimeoutError, OSError):
        return None
    if not isinstance(osrm, dict) or not osrm.get("routes"):
        return None
    try:
        return parse_osrm_route(osrm["routes"][0], "via", via=via)
    except RoutingFailure:
        return None


def _acceptable(candidate: NormalizedRoute, primary: NormalizedRoute) -> bool:
    if primary.duration_seconds <= 0 or primary.distance_miles <= 0:
        return True
    if candidate.duration_seconds > primary.duration_seconds * 1.85:
        return False
    if candidate.distance_miles > primary.distance_miles * 1.9:
        return False
    return True


def collect_routes(origin: tuple[float, float], destination: tuple[float, float], fetch=http_json):
    """Return up to three distinct engine routes, notes, and provider errors.

    `origin` and `destination` are (lat, lon).
    """
    notes: list[str] = []
    errors: list[str] = []
    routes: list[NormalizedRoute] = []
    try:
        routes.extend(fetch_valhalla(origin, destination, fetch))
    except (RoutingFailure, HttpError, TimeoutError, OSError, ValueError) as exc:
        errors.append(f"Valhalla: {exc}")
    routes = dedupe_routes(routes)
    if len(routes) < 3:
        try:
            for route in fetch_osrm(origin, destination, fetch):
                if is_distinct(route, routes):
                    routes.append(route)
        except (RoutingFailure, HttpError, TimeoutError, OSError, ValueError) as exc:
            errors.append(f"OSRM: {exc}")
        routes = dedupe_routes(routes)
    if routes and len(routes) < 3:
        vias = _via_points(routes[0])
        if vias:
            with ThreadPoolExecutor(max_workers=min(4, len(vias))) as pool:
                found = list(pool.map(lambda via: _fetch_via(origin, destination, via, fetch), vias))
            for route in found:
                if route is None or len(routes) >= 3:
                    continue
                if _acceptable(route, routes[0]) and is_distinct(route, routes):
                    routes.append(route)
            notes.append(
                "Where the engines returned fewer than three alternatives, extra options were "
                "requested from the same engines through an intermediate via point. The geometry "
                "is still the engine's."
            )
    if not routes:
        detail = " ".join(errors) or "No routing engine returned a road path."
        raise RoutingFailure(detail)
    routes = routes[:3]
    if len(routes) < 3:
        notes.append(
            f"Only {len(routes)} distinct driving route"
            f"{'' if len(routes) == 1 else 's'} came back. No geometry was invented to fill the gap."
        )
    notes.append(
        "Routes use a car driving profile (Valhalla auto or OSRM driving). "
        "They do not enforce truck height, weight, hazmat, or road restrictions and are not certified truck routes. "
        "Travel time is the engine's driving duration, not an hours-of-service schedule."
    )
    return routes, notes, errors
