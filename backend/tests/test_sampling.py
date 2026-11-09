from datetime import timedelta, timezone

import pytest

from routing.logic.geo import decode_polyline, destination, encode_polyline
from routing.logic.sampling import checkpoint_miles, place_checkpoints, scale_durations
from routing.services.planner import parse_departure


def _north_line(edge_miles, edge_seconds):
    coords = [(-90.0, 40.0)]
    for miles in edge_miles:
        lon, lat = destination(coords[-1][0], coords[-1][1], 0, miles * 1609.344)
        coords.append((lon, lat))
    return coords


def test_spacing_includes_destination_remainder_and_exact_multiples():
    assert checkpoint_miles(80, 25) == pytest.approx([0, 25, 50, 75, 80])
    assert checkpoint_miles(80, 50) == pytest.approx([0, 50, 80])
    assert checkpoint_miles(80, 10) == pytest.approx([0, 10, 20, 30, 40, 50, 60, 70, 80])
    assert checkpoint_miles(50, 50) == pytest.approx([0, 50])
    assert checkpoint_miles(12, 50) == pytest.approx([0, 12])
    assert checkpoint_miles(50.02, 50) == pytest.approx([0, 50.02])


def test_eta_follows_edge_duration_not_distance_fraction():
    # Ten 10-mile edges. The first five are slow, the last five are fast.
    slow = 1440.0  # 10 miles at 25 mph
    fast = 360.0  # 10 miles at 100 mph
    edge_miles = [10.0] * 10
    edge_seconds = [slow] * 5 + [fast] * 5
    coords = _north_line(edge_miles, edge_seconds)
    points = place_checkpoints(coords, edge_miles, edge_seconds, 25)
    by_mile = {round(point.mile, 3): point for point in points}
    assert by_mile[0].elapsed_seconds == 0
    assert by_mile[50].elapsed_seconds == pytest.approx(5 * slow)
    # A distance-based ETA would put mile 50 at half of 9000 seconds.
    assert by_mile[50].elapsed_seconds != pytest.approx(4500)
    assert by_mile[75].elapsed_seconds == pytest.approx(5 * slow + 2.5 * fast)
    assert by_mile[100].elapsed_seconds == pytest.approx(5 * slow + 5 * fast)
    assert by_mile[100].is_destination
    assert by_mile[0].is_origin
    assert sum(point.mile == 100 for point in points) == 1


def test_segment_miles_partition_the_route():
    edge_miles = [10.0] * 8
    edge_seconds = [600.0] * 8
    coords = _north_line(edge_miles, edge_seconds)
    for spacing in (10, 25, 50):
        points = place_checkpoints(coords, edge_miles, edge_seconds, spacing)
        segment_miles = [points[i + 1].mile - points[i].mile for i in range(len(points) - 1)]
        assert sum(segment_miles) == pytest.approx(80)
        assert points[-1].mile == pytest.approx(80)
        assert points[-1].elapsed_seconds == pytest.approx(4800)


def test_duration_scale_preserves_relative_timing():
    scaled = scale_durations([10, 30], 80)
    assert scaled == pytest.approx([20, 60])
    assert sum(scale_durations([2028.9], 2140.2)) == pytest.approx(2140.2)


def test_polyline_roundtrip_and_known_precision_5_vector():
    encoded = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
    coords = decode_polyline(encoded, precision=5)
    assert coords[0][1] == pytest.approx(38.5, abs=1e-4)
    assert coords[0][0] == pytest.approx(-120.2, abs=1e-3)
    original = [(-87.6298, 41.8781), (-87.5, 42.0), (-83.0458, 42.3314)]
    restored = decode_polyline(encode_polyline(original, precision=6), precision=6)
    for (lon, lat), (rlon, rlat) in zip(original, restored):
        assert rlon == pytest.approx(lon, abs=1e-5)
        assert rlat == pytest.approx(lat, abs=1e-5)


def test_departure_timezone_is_the_selected_zone_not_utc():
    departure = parse_departure("2026-11-10T08:00", "America/Chicago")
    assert departure.utcoffset() == timedelta(hours=-6)
    assert departure.astimezone(timezone.utc).isoformat() == "2026-11-10T14:00:00+00:00"
    eta = departure + timedelta(seconds=5400)
    assert eta.isoformat() == "2026-11-10T09:30:00-06:00"


def test_daylight_saving_gap_is_rejected():
    with pytest.raises(Exception, match="does not exist"):
        parse_departure("2026-03-08T02:30", "America/Chicago")
