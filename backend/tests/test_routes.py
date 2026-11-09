import pytest

from routing.logic.geo import destination, encode_polyline
from routing.services.geocode import Place, choose_matches
from routing.logic.route_model import NormalizedRoute, dedupe_routes, is_distinct
from routing.services.routes import collect_routes, parse_osrm_route, parse_valhalla_trip


def _line(lat, lon, steps, miles):
    coords = [(lon, lat)]
    for _ in range(steps):
        lon, lat = destination(coords[-1][0], coords[-1][1], 90, miles * 1609.344)
        coords.append((lon, lat))
    return coords


def _trip(coords, seconds=3600, length=None, road="I 94"):
    shape = encode_polyline(coords, precision=6)
    return {
        "summary": {
            "time": seconds,
            "length": length if length is not None else 100,
            "has_toll": False,
            "has_highway": True,
        },
        "legs": [
            {
                "shape": shape,
                "summary": {"time": seconds, "length": length if length is not None else 100},
                "maneuvers": [
                    {
                        "begin_shape_index": 0,
                        "end_shape_index": len(coords) - 1,
                        "time": seconds,
                        "length": length if length is not None else 100,
                        "street_names": [road],
                    }
                ],
            }
        ],
    }


def test_valhalla_time_is_preserved_and_osrm_annotations_are_scaled():
    coords = _line(41.0, -90.0, 4, 10)
    route = parse_valhalla_trip(_trip(coords, seconds=4000, road="I 94"), "primary")
    assert route.road_name == "I 94"
    assert route.duration_seconds == 4000
    assert sum(route.edge_seconds) == pytest.approx(4000)
    assert abs(route.distance_miles - 40) < 0.05
    osrm = parse_osrm_route(
        {
            "duration": 80,
            "distance": 1609.344 * 2,
            "geometry": {"coordinates": [[-90, 41], [-89.9, 41], [-89.8, 41]]},
            "legs": [{"annotation": {"distance": [1000, 3000], "duration": [10, 30]}}],
        },
        "alternate",
    )
    assert osrm.timing == "engine-annotation"
    assert sum(osrm.edge_seconds) == pytest.approx(80)
    assert osrm.edge_seconds[1] > osrm.edge_seconds[0] * 2
    fallback = parse_osrm_route(
        {
            "duration": 50,
            "distance": 1000,
            "geometry": {"coordinates": [[-90, 41], [-89.9, 41], [-89.8, 41]]},
            "legs": [{"annotation": {"distance": [1000], "duration": [10]}}],
        },
        "alternate",
    )
    assert fallback.timing == "distance-proportional-fallback"
    assert sum(fallback.edge_seconds) == pytest.approx(50)


def test_duplicate_geometry_is_not_kept_as_another_route():
    coords = _line(41.0, -87.0, 6, 8)
    shifted = _line(42.2, -87.0, 6, 8)
    primary = parse_valhalla_trip(_trip(coords), "primary")
    clone = parse_valhalla_trip(_trip(coords), "alternate")
    other = parse_valhalla_trip(_trip(shifted, road="I 80"), "alternate")
    kept = dedupe_routes([primary, clone, other])
    assert len(kept) == 2
    assert is_distinct(other, [primary])
    assert not is_distinct(clone, [primary])


def test_geocoder_prefers_cities_over_points_of_interest():
    city = Place("Chicago, Illinois", 41.8, -87.6, "Chicago", rank=0)
    campus = Place("The University of Chicago, Chicago, Illinois", 41.7, -87.6, "Chicago", rank=5)
    chosen = choose_matches([campus, city, campus], limit=5)
    assert [place.label for place in chosen] == ["Chicago, Illinois"]


def test_collect_routes_returns_three_engine_alternatives_without_inventing_a_fourth():
    trips = [
        _trip(_line(41.0, -90.0, 5, 12), road="I 94"),
        _trip(_line(42.3, -90.0, 5, 12), road="I 80"),
        _trip(_line(39.7, -90.0, 5, 12), road="US 30"),
    ]
    calls = []

    def fake(url, method="GET", payload=None, timeout=25):
        calls.append((url, method, None if payload is None else len(payload.get("locations", []))))
        if "valhalla" in url and payload and len(payload["locations"]) == 2:
            return {"trip": trips[0], "alternates": [{"trip": trips[1]}, {"trip": trips[2]}]}
        raise AssertionError(f"unexpected routing call {url}")

    routes, notes, errors = collect_routes((41.0, -90.0), (41.0, -88.5), fetch=fake)
    assert len(routes) == 3
    assert {route.road_name for route in routes} == {"I 94", "I 80", "US 30"}
    assert len(calls) == 1
    assert any("car driving profile" in note for note in notes)
    assert errors == []
