import json

import pytest
from django.test import RequestFactory

from routing.services.planner import plan_trip
from routing.views import assess, health, plan


@pytest.fixture
def factory():
    return RequestFactory()


def test_health_reports_django(factory):
    response = health(factory.get("/api/health"))
    payload = json.loads(response.content)
    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["backend"] == "django"


def test_plan_rejects_bad_spacing_and_offset_departure(factory):
    body = {
        "origin": "Chicago, IL",
        "destination": "Detroit, MI",
        "departure": "2026-11-10T08:00Z",
        "timezone": "America/Chicago",
        "load_lb": 25000,
        "spacing_miles": 15,
    }
    request = factory.post("/api/plan", data=json.dumps(body), content_type="application/json")
    response = plan(request)
    assert response.status_code == 400
    assert "spacing" in json.loads(response.content)["error"].lower() or "offset" in json.loads(response.content)["error"].lower()


def test_plan_and_assess_pipeline_with_fake_services(factory):
    from tests.test_routes import _line, _trip

    trips = [
        _trip(_line(41.5, -88.0, 4, 20), seconds=5000, road="I 94"),
        _trip(_line(42.6, -88.0, 4, 20), seconds=7000, road="I 80"),
        _trip(_line(40.4, -88.0, 4, 20), seconds=6500, road="US 30"),
    ]

    def fake(url, method="GET", payload=None, timeout=25):
        if "valhalla" in url:
            return {"trip": trips[0], "alternates": [{"trip": trips[1]}, {"trip": trips[2]}]}
        if "open-meteo" in url:
            return _forecast(url)
        raise AssertionError(url)

    planned = plan_trip(
        {
            "origin": {"label": "Start", "lat": 41.5, "lon": -88.0},
            "destination": {"label": "End", "lat": 41.5, "lon": -86.5},
            "departure": "2026-11-10T08:00",
            "timezone": "America/Chicago",
            "load_lb": 32000,
            "spacing_miles": 25,
        },
        fetch=fake,
    )
    assert planned["route_count"] == 3
    assert planned["routes"][0]["profile"] == "auto"
    assert planned["routes"][0]["truck_restrictions"] is False
    for route in planned["routes"]:
        checkpoints = route["checkpoints"]
        segment_sum = checkpoints[-1]["mile"] - checkpoints[0]["mile"]
        assert segment_sum == pytest.approx(route["distance_miles"])
        assert checkpoints[-1]["elapsed_seconds"] == pytest.approx(route["duration_seconds"])
        assert checkpoints[-1]["is_destination"] is True
        assert checkpoints[0]["elapsed_seconds"] == 0

    request = factory.post(
        "/api/assess",
        data=json.dumps(
            {
                "load_lb": 32000,
                "timezone": "America/Chicago",
                "departure": "2026-11-10T08:00",
                "routes": [
                    {
                        "id": route["id"],
                        "duration_seconds": route["duration_seconds"],
                        "checkpoints": route["checkpoints"],
                    }
                    for route in planned["routes"]
                ],
            }
        ),
        content_type="application/json",
    )
    # The view uses the real weather client. Call the service instead so the
    # fake forecast stays in-process, then check the view's validation path.
    from routing.services.planner import assess_trip

    assessed = assess_trip(
        json.loads(request.body),
        fetch=fake,
    )
    assert assessed["recommendation"]["route_id"] in {"A", "B", "C"}
    for route in assessed["routes"]:
        summary = route["summary"]
        total = (
            summary["low_miles"]
            + summary["moderate_miles"]
            + summary["high_miles"]
            + summary["severe_miles"]
            + summary["no_travel_miles"]
            + summary["unknown_miles"]
        )
        assert total == pytest.approx(summary["total_miles"])
        # 08:00 America/Chicago is 14:00 UTC, so the sample is that hour, not 00:00.
        assert route["checkpoints"][0]["wind_mph"] == 14
        assert route["checkpoints"][-1]["wind_mph"] != route["checkpoints"][0]["wind_mph"]
        assert route["checkpoints"][-1]["elapsed_seconds"] > 0
    response = assess(factory.post("/api/assess", data="{}", content_type="application/json"))
    assert response.status_code == 400


def _forecast(url: str):
    from urllib.parse import parse_qs, urlsplit

    query = parse_qs(urlsplit(url).query)
    lats = query["latitude"][0].split(",")
    count = len(lats)
    hours = [f"2026-11-10T{hour:02d}:00" for hour in range(24)]
    row = {
        "hourly_units": {"wind_speed_10m": "mp/h", "rain": "inch", "snowfall": "inch"},
        "hourly": {
            "time": hours,
            "wind_speed_10m": [10 + (index % 5) for index in range(24)],
            "rain": [0.0] * 24,
            "snowfall": [0.0] * 24,
        },
    }
    if count == 1:
        return row
    return [row for _ in lats]
