from datetime import datetime, timedelta, timezone

from routing.logic.assess import Series, assess_route, classify_clock_hours, sample_series
from routing.services.weather import parse_open_meteo


def _departure():
    return datetime(2026, 11, 10, 8, 0, tzinfo=timezone(timedelta(hours=-6)))


def _series(start, winds, rains, snows):
    times = tuple(start + timedelta(hours=index) for index in range(len(winds)))
    return Series(times, tuple(winds), tuple(rains), tuple(snows))


def test_weather_is_sampled_at_eta_and_interpolated():
    departure = _departure()
    start = departure.astimezone(timezone.utc)
    origin = {
        "mile": 0,
        "lat": 40,
        "lon": -90,
        "elapsed_seconds": 0,
        "is_origin": True,
        "is_destination": False,
        "index": 0,
    }
    middle = {
        "mile": 50,
        "lat": 41,
        "lon": -90,
        "elapsed_seconds": 3600,
        "is_origin": False,
        "is_destination": False,
        "index": 1,
    }
    end = {
        "mile": 80,
        "lat": 42,
        "lon": -90,
        "elapsed_seconds": 7200,
        "is_origin": False,
        "is_destination": True,
        "index": 2,
    }
    changing = _series(start, [10.0, 30.0, 50.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0])
    result = assess_route(
        route_id="A",
        index=0,
        duration_seconds=7200,
        departure=departure,
        checkpoints=[origin, middle, end],
        series=[changing, changing, changing],
        load_lb=25_000,
    )
    winds = [point["wind_mph"] for point in result["checkpoints"]]
    assert winds[0] == 10  # departure hour
    assert winds[1] == 30  # one driving hour later, not the departure sample
    assert winds[2] == 50
    assert result["checkpoints"][1]["eta"].startswith("2026-11-10T09:00:00-06:00")
    # max(low, moderate) then max(moderate, severe)
    assert [segment["risk"] for segment in result["segments"]] == ["moderate", "severe"]
    assert result["summary"]["moderate_miles"] == 50
    assert result["summary"]["severe_miles"] == 30
    assert result["summary"]["low_miles"] == 0


def test_linear_interpolation_and_no_extrapolation():
    start = datetime(2026, 11, 10, 14, tzinfo=timezone.utc)
    series = _series(start, [0.0, 10.0], [0.0, 1.0], [0.0, 4.0])
    mid = start + timedelta(minutes=30)
    wind, rain, snow = sample_series(series, mid)
    assert wind == 5
    assert rain == 0.5
    assert snow == 2
    assert sample_series(series, start - timedelta(seconds=1)) == (None, None, None)
    assert sample_series(series, start + timedelta(hours=1, seconds=1)) == (None, None, None)
    gappy = Series(series.times, (0.0, None), (0.0, 0.0), (0.0, 0.0))
    assert sample_series(gappy, mid)[0] is None


def test_missing_forecast_does_not_become_low_miles():
    departure = _departure()
    empty = Series((), (), (), (), error="outside horizon")
    result = assess_route(
        route_id="A",
        index=0,
        duration_seconds=100,
        departure=departure,
        checkpoints=[
            {"index": 0, "mile": 0, "lat": 1, "lon": 2, "elapsed_seconds": 0, "is_origin": True, "is_destination": False},
            {"index": 1, "mile": 40, "lat": 2, "lon": 3, "elapsed_seconds": 100, "is_origin": False, "is_destination": True},
        ],
        series=[empty, empty],
        load_lb=10,
    )
    assert result["summary"]["unknown_miles"] == 40
    assert result["summary"]["low_miles"] == 0
    assert result["summary"]["eligible"] is False
    assert result["checkpoints"][0]["risk"] == "unknown"


def test_slider_hours_change_underlying_values_and_can_be_unknown():
    departure = _departure()
    start = departure.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    # Departure is 08:00, which aligns with an hour, so hour 0 is the first value
    # and hour 6 is a later forecast value.
    winds = [5 + index for index in range(10)]
    series = _series(start, winds, [0.0] * 10, [0.0] * 10)
    corridor = classify_clock_hours(series, departure, 25_000, hours=49)
    assert corridor["wind_mph"][0] == 5
    assert corridor["wind_mph"][6] == 11
    assert corridor["risk"][0] == 1
    assert corridor["wind_mph"][20] is None
    assert corridor["risk"][20] == 0


def test_open_meteo_parser_keeps_snow_depth_and_nulls():
    imperial = parse_open_meteo(
        {
            "hourly_units": {"wind_speed_10m": "mp/h", "rain": "inch", "snowfall": "inch"},
            "hourly": {
                "time": ["2026-11-10T00:00", "2026-11-10T01:00"],
                "wind_speed_10m": [12.5, None],
                "rain": [0.2, 0.0],
                "snowfall": [1.5, 0.0],
                "precipitation": [9.9, 9.9],
            },
        }
    )
    assert imperial.wind_mph[0] == 12.5
    assert imperial.wind_mph[1] is None
    assert imperial.rain_in_hr[0] == 0.2
    assert imperial.snow_in_hr[0] == 1.5
    metric = parse_open_meteo(
        {
            "hourly_units": {"wind_speed_10m": "km/h", "rain": "mm", "snowfall": "cm"},
            "hourly": {
                "time": ["2026-11-10T00:00"],
                "wind_speed_10m": [100],
                "rain": [25.4],
                "snowfall": [2.54],
            },
        }
    )
    assert metric.wind_mph[0] == pytest_approx(62.13711922)
    assert metric.rain_in_hr[0] == pytest_approx(1)
    assert metric.snow_in_hr[0] == pytest_approx(1)


def pytest_approx(value):
    import pytest

    return pytest.approx(value)
