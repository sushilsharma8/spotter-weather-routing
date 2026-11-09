"""Attach forecast samples to checkpoints and roll the route up.

Weather is read at the checkpoint ETA, not at departure for every point.
Hourly values are linearly interpolated. Times outside the returned series
are missing. Missing is never coerced to zero or Low.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from routing.logic.ranking import RankedRoute, Segment, segments_from_checkpoints, summarize
from routing.logic.risk import (
    apply_load,
    classify_rain,
    classify_snow,
    classify_wind,
    combine,
    explain_checkpoint,
)


@dataclass(frozen=True)
class Series:
    times: tuple[datetime, ...]
    wind_mph: tuple[float | None, ...]
    rain_in_hr: tuple[float | None, ...]
    snow_in_hr: tuple[float | None, ...]
    error: str | None = None


def sample_series(series: Series, moment: datetime) -> tuple[float | None, float | None, float | None]:
    times = series.times
    if series.error or not times:
        return None, None, None
    if moment < times[0] or moment > times[-1]:
        return None, None, None
    # Binary search for the hour at or before `moment`.
    lo = 0
    hi = len(times) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if times[mid] <= moment:
            lo = mid
        else:
            hi = mid - 1
    if times[lo] == moment or lo == len(times) - 1:
        return series.wind_mph[lo], series.rain_in_hr[lo], series.snow_in_hr[lo]
    nxt = lo + 1
    span = (times[nxt] - times[lo]).total_seconds()
    if span <= 0:
        return series.wind_mph[lo], series.rain_in_hr[lo], series.snow_in_hr[lo]
    fraction = (moment - times[lo]).total_seconds() / span
    return (
        _blend(series.wind_mph[lo], series.wind_mph[nxt], fraction),
        _blend(series.rain_in_hr[lo], series.rain_in_hr[nxt], fraction),
        _blend(series.snow_in_hr[lo], series.snow_in_hr[nxt], fraction),
    )


def _blend(left: float | None, right: float | None, fraction: float) -> float | None:
    if left is None or right is None:
        return None
    return left + (right - left) * fraction


def _nonnegative(value: float | None) -> float | None:
    if value is None:
        return None
    if value < 0:
        return None
    return value


def classify_sample(
    wind_mph: float | None,
    rain_in_hr: float | None,
    snow_in_hr: float | None,
    load_lb: float,
) -> dict:
    wind_mph = _nonnegative(wind_mph)
    rain_in_hr = _nonnegative(rain_in_hr)
    snow_in_hr = _nonnegative(snow_in_hr)
    wind = classify_wind(wind_mph) if wind_mph is not None else None
    rain = classify_rain(rain_in_hr) if rain_in_hr is not None else None
    snow = classify_snow(snow_in_hr) if snow_in_hr is not None else None
    adjusted = apply_load(wind, wind_mph, load_lb) if wind is not None and wind_mph is not None else None
    combined = combine([adjusted, rain, snow])
    missing = []
    if wind is None:
        missing.append("wind")
    if rain is None:
        missing.append("rain")
    if snow is None:
        missing.append("snow")
    return {
        "wind_mph": wind_mph,
        "rain_in_hr": rain_in_hr,
        "snow_in_hr": snow_in_hr,
        "wind_risk": wind.label if wind else None,
        "rain_risk": rain.label if rain else None,
        "snow_risk": snow.label if snow else None,
        "load_adjusted_wind_risk": adjusted.label if adjusted else None,
        "risk": combined.label if combined else "unknown",
        "missing": missing,
        "detail": explain_checkpoint(
            wind_mph=wind_mph,
            rain_in_hr=rain_in_hr,
            snow_in_hr=snow_in_hr,
            load_lb=load_lb,
            wind=wind,
            wind_after_load=adjusted,
            rain=rain,
            snow=snow,
            combined=combined,
        ),
    }


def assess_route(
    *,
    route_id: str,
    index: int,
    duration_seconds: float,
    departure: datetime,
    checkpoints: list[dict],
    series: list[Series],
    load_lb: float,
) -> dict:
    if len(checkpoints) != len(series):
        raise ValueError("Each checkpoint needs its own weather series.")
    enriched = []
    risks: list[str | None] = []
    miles: list[float] = []
    for checkpoint, point_series in zip(checkpoints, series):
        elapsed = float(checkpoint["elapsed_seconds"])
        eta = departure + timedelta(seconds=elapsed)
        wind, rain, snow = sample_series(point_series, eta)
        classified = classify_sample(wind, rain, snow, load_lb)
        if point_series.error and not classified["missing"]:
            classified["missing"] = ["forecast"]
            classified["risk"] = "unknown"
        risks.append(None if classified["risk"] == "unknown" else classified["risk"])
        miles.append(float(checkpoint["mile"]))
        enriched.append(
            {
                **checkpoint,
                "eta": eta.isoformat(),
                "elapsed_seconds": elapsed,
                "forecast_error": point_series.error,
                **classified,
            }
        )
    segments = segments_from_checkpoints(miles, risks)
    summary = summarize(segments)
    ranked = RankedRoute(
        route_id=route_id,
        index=index,
        severe_miles=summary.severe_miles,
        high_miles=summary.high_miles,
        average_risk=summary.average_risk,
        duration_seconds=duration_seconds,
        eligible=summary.eligible,
        blockers=summary.blockers,
    )
    return {
        "checkpoints": enriched,
        "segments": [_segment_json(segment) for segment in segments],
        "summary": _summary_json(summary),
        "ranked": ranked,
    }


def classify_clock_hours(series: Series, departure: datetime, load_lb: float, hours: int = 49) -> dict:
    """Corridor samples at departure + 0..hours-1. This is a clock offset."""
    risks: list[int] = []
    wind_out: list[float | None] = []
    rain_out: list[float | None] = []
    snow_out: list[float | None] = []
    times: list[str] = []
    for hour in range(hours):
        moment = departure + timedelta(hours=hour)
        times.append(moment.isoformat())
        wind, rain, snow = sample_series(series, moment)
        classified = classify_sample(wind, rain, snow, load_lb)
        label = classified["risk"]
        risks.append(0 if label == "unknown" else {"low": 1, "moderate": 2, "high": 3, "severe": 4, "no_travel": 5}[label])
        wind_out.append(_round(classified["wind_mph"], 1))
        rain_out.append(_round(classified["rain_in_hr"], 3))
        snow_out.append(_round(classified["snow_in_hr"], 3))
    return {
        "times": times,
        "risk": risks,
        "wind_mph": wind_out,
        "rain_in_hr": rain_out,
        "snow_in_hr": snow_out,
    }


def _round(value: float | None, digits: int) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _segment_json(segment: Segment) -> dict:
    return {
        "from_index": segment.from_index,
        "to_index": segment.to_index,
        "miles": segment.miles,
        "risk": segment.risk or "unknown",
    }


def _summary_json(summary) -> dict:
    return {
        "total_miles": summary.total_miles,
        "low_miles": summary.low_miles,
        "moderate_miles": summary.moderate_miles,
        "high_miles": summary.high_miles,
        "severe_miles": summary.severe_miles,
        "no_travel_miles": summary.no_travel_miles,
        "unknown_miles": summary.unknown_miles,
        "average_risk": summary.average_risk,
        "eligible": summary.eligible,
        "blockers": list(summary.blockers),
    }


def ranked_from_summary(route_id: str, index: int, duration_seconds: float, summary) -> RankedRoute:
    return RankedRoute(
        route_id=route_id,
        index=index,
        severe_miles=summary.severe_miles,
        high_miles=summary.high_miles,
        average_risk=summary.average_risk,
        duration_seconds=duration_seconds,
        eligible=summary.eligible,
        blockers=summary.blockers,
    )
