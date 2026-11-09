from routing.logic.ranking import RankedRoute, recommend, segments_from_checkpoints, summarize


def _summary_from(pairs):
    miles = [0.0]
    risks = []
    for mile, risk in pairs:
        risks.append(risk)
        if mile != 0:
            miles.append(mile)
    if miles[-1] != pairs[-1][0]:
        miles.append(pairs[-1][0])
    # pairs are (mile, risk) including 0.
    miles = [mile for mile, _risk in pairs]
    risks = [risk for _mile, risk in pairs]
    segments = segments_from_checkpoints(miles, risks)
    return segments, summarize(segments)


def test_endpoint_max_assigns_miles_and_partitions():
    segments, summary = _summary_from([(0, "low"), (25, "severe"), (50, "low")])
    assert [segment.risk for segment in segments] == ["severe", "severe"]
    assert summary.severe_miles == 50
    assert summary.low_miles == 0
    assert summary.total_miles == 50
    assert summary.average_risk == 4
    assert (
        summary.low_miles
        + summary.moderate_miles
        + summary.high_miles
        + summary.severe_miles
        + summary.no_travel_miles
        + summary.unknown_miles
        == summary.total_miles
    )


def test_unknown_is_not_counted_as_low_and_blocks_the_route():
    _segments, summary = _summary_from([(0, "low"), (25, None), (50, "low")])
    assert summary.unknown_miles == 50
    assert summary.low_miles == 0
    assert summary.average_risk is None
    assert summary.eligible is False
    assert summary.blockers


def test_lexicographic_ranking_and_blocked_routes():
    def route(name, index, severe, high, average, duration, eligible=True, blockers=()):
        return RankedRoute(name, index, severe, high, average, duration, eligible, blockers)

    routes = [
        route("A", 0, 0, 20, 1.6, 10_000),
        route("B", 1, 10, 0, 1.3, 8_000),
        route("C", 2, 0, 20, 1.6, 9_000),
        route("D", 3, 0, 0, 1.1, 1_000, eligible=False, blockers=("5.0 miles are No Travel",)),
    ]
    # A beats B on severe miles. C ties A on severe and high and average, then wins on time.
    # D is faster and calmer but blocked, so it cannot win.
    result = recommend(routes)
    assert result["route_id"] == "C"
    assert "D" not in result["eligible_ids"]
    assert any("No Travel" in reason for reason in result["reasons"])

    only_time = [
        route("A", 0, 0, 10, 1.5, 9_000),
        route("B", 1, 0, 10, 1.5, 8_000),
    ]
    assert recommend(only_time)["route_id"] == "B"

    average_breaks_tie = [
        route("A", 0, 0, 10, 1.8, 8_000),
        route("B", 1, 0, 10, 1.5, 9_000),
    ]
    assert recommend(average_breaks_tie)["route_id"] == "B"

    high_breaks_tie = [
        route("A", 0, 5, 30, 1.2, 5_000),
        route("B", 1, 5, 10, 2.0, 9_000),
    ]
    assert recommend(high_breaks_tie)["route_id"] == "B"


def test_complete_tie_keeps_the_earlier_route_and_all_blocked_recommends_none():
    tied = [
        RankedRoute("B", 1, 0, 10, 1.5, 8000, True, ()),
        RankedRoute("A", 0, 0, 10, 1.5, 8000, True, ()),
    ]
    result = recommend(tied)
    assert result["route_id"] == "A"
    assert any("Tied" in reason for reason in result["reasons"])
    blocked = [
        RankedRoute("A", 0, 1, 0, 5, 100, False, ("No Travel",)),
        RankedRoute("B", 1, 0, 0, None, 100, False, ("missing",)),
    ]
    assert recommend(blocked) is None
