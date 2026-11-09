"""Segment rolls-ups and lexicographic route recommendation.

Assumptions, not source rules:
* Segment risk is the higher risk of its endpoints. Unknown contaminates it.
* Category miles partition the route. Average risk is the distance-weighted
  mean of Low=1, Moderate=2, High=3, Severe=4, No Travel=5.
* Unknown miles make the average unavailable and the route ineligible.
* Any No Travel miles make the route ineligible.
* Ineligible routes stay visible and are never chosen.
* If none are eligible, the recommendation is none.
* Ties closer than 0.0001 miles, 1e-6 risk, or 0.5 seconds fall through.
  A complete tie keeps the earlier route.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from routing.logic.risk import LABEL_SCORE

MILE_TIE = 1e-4
RISK_TIE = 1e-6
TIME_TIE = 0.5


@dataclass(frozen=True)
class Segment:
    from_index: int
    to_index: int
    miles: float
    risk: str | None


@dataclass(frozen=True)
class Summary:
    total_miles: float
    low_miles: float
    moderate_miles: float
    high_miles: float
    severe_miles: float
    no_travel_miles: float
    unknown_miles: float
    average_risk: float | None
    eligible: bool
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class RankedRoute:
    route_id: str
    index: int
    severe_miles: float
    high_miles: float
    average_risk: float | None
    duration_seconds: float
    eligible: bool
    blockers: tuple[str, ...]


def segments_from_checkpoints(miles: list[float], risks: list[str | None]) -> list[Segment]:
    if len(miles) != len(risks):
        raise ValueError("Checkpoint miles and risks must align.")
    from routing.logic.risk import max_severity

    segments: list[Segment] = []
    for index in range(len(miles) - 1):
        segments.append(
            Segment(
                from_index=index,
                to_index=index + 1,
                miles=miles[index + 1] - miles[index],
                risk=max_severity(risks[index], risks[index + 1]),
            )
        )
    return segments


def summarize(segments: list[Segment]) -> Summary:
    buckets = {
        "low": 0.0,
        "moderate": 0.0,
        "high": 0.0,
        "severe": 0.0,
        "no_travel": 0.0,
    }
    unknown = 0.0
    for segment in segments:
        if segment.risk is None:
            unknown += segment.miles
        else:
            buckets[segment.risk] += segment.miles
    total = math.fsum([*buckets.values(), unknown])
    if unknown > 1e-6 or total <= 0:
        average = None
    else:
        weighted = math.fsum(LABEL_SCORE[name] * miles for name, miles in buckets.items())
        average = weighted / total
    blockers: list[str] = []
    if buckets["no_travel"] > 1e-6:
        blockers.append(f"{buckets['no_travel']:.1f} miles are No Travel")
    if unknown > 1e-6:
        blockers.append(
            f"{unknown:.1f} miles have no usable forecast and were not treated as Low"
        )
    eligible = not blockers and total > 0 and average is not None
    return Summary(
        total_miles=total,
        low_miles=buckets["low"],
        moderate_miles=buckets["moderate"],
        high_miles=buckets["high"],
        severe_miles=buckets["severe"],
        no_travel_miles=buckets["no_travel"],
        unknown_miles=unknown,
        average_risk=average,
        eligible=eligible,
        blockers=tuple(blockers),
    )


def _differs(left: float, right: float, epsilon: float) -> bool:
    return abs(left - right) > epsilon


def recommend(routes: list[RankedRoute]) -> dict | None:
    eligible = [route for route in routes if route.eligible and route.average_risk is not None]
    if not eligible:
        return None
    ordered = sorted(
        eligible,
        key=lambda route: (
            round(route.severe_miles, 4),
            round(route.high_miles, 4),
            round(route.average_risk or 0.0, 6),
            round(route.duration_seconds, 1),
            route.index,
        ),
    )
    winner = ordered[0]
    reasons = _reasons(winner, ordered[1:], routes)
    return {
        "route_id": winner.route_id,
        "reasons": reasons,
        "eligible_ids": [route.route_id for route in ordered],
    }


def _reasons(winner: RankedRoute, others: list[RankedRoute], everyone: list[RankedRoute]) -> list[str]:
    reasons: list[str] = []
    blocked = [route for route in everyone if not route.eligible]
    if not others:
        if blocked:
            names = ", ".join(route.route_id for route in blocked)
            reasons.append(f"Only eligible route. {names} excluded from ranking.")
        else:
            reasons.append("Only route returned, and it is eligible.")
    for other in others:
        phrase, left, right, unit = _first_gap(winner, other)
        if phrase == "tie":
            reasons.append(
                f"Tied with {other.route_id} on severe miles, high miles, average risk, and travel time. "
                f"Kept {winner.route_id} because it was listed earlier."
            )
            continue
        reasons.append(
            f"{phrase} than {other.route_id}: {left:.1f} vs {right:.1f} {unit}."
            if unit != "score"
            else f"{phrase} than {other.route_id}: {left:.2f} vs {right:.2f}."
        )
    for route in blocked:
        detail = "; ".join(route.blockers) if route.blockers else "ineligible"
        reasons.append(f"{route.route_id} is not ranked ({detail}).")
    return reasons


def _first_gap(winner: RankedRoute, other: RankedRoute) -> tuple[str, float, float, str]:
    assert winner.average_risk is not None and other.average_risk is not None
    checks = (
        ("Fewer severe miles", winner.severe_miles, other.severe_miles, MILE_TIE, "mi"),
        ("Fewer high miles", winner.high_miles, other.high_miles, MILE_TIE, "mi"),
        ("Lower average risk", winner.average_risk, other.average_risk, RISK_TIE, "score"),
        ("Shorter travel time", winner.duration_seconds / 60.0, other.duration_seconds / 60.0, TIME_TIE / 60.0, "min"),
    )
    for phrase, left, right, epsilon, unit in checks:
        if _differs(left, right, epsilon):
            return phrase, left, right, unit
    return "tie", 0.0, 0.0, ""
