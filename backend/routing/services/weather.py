"""Open-Meteo hourly forecasts.

The free endpoint needs no key. Calls are batched, cached, and limited to a
few concurrent requests. Snowfall is read as snow depth. Rain is liquid rain.
Values outside the returned hours stay missing.
"""

from __future__ import annotations

import re
import threading
import time
from datetime import datetime, timedelta, timezone

from routing.logic.assess import Series
from routing.logic.units import rain_to_inches_per_hour, snow_depth_to_inches_per_hour, wind_to_mph
from routing.services.http import HttpError, http_json

OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
_RANGE_RE = re.compile(r"from (\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})")
_CACHE: dict[str, tuple[float, dict | list]] = {}
_LOCK = threading.Lock()
_TTL_SECONDS = 20 * 60


def _cached_get(url: str, fetch) -> dict | list:
    now = time.time()
    with _LOCK:
        hit = _CACHE.get(url)
        if hit and hit[0] > now:
            return hit[1]
    payload = fetch(url, timeout=25)
    if isinstance(payload, dict) and payload.get("error"):
        return payload
    with _LOCK:
        _CACHE[url] = (now + _TTL_SECONDS, payload)
        if len(_CACHE) > 240:
            oldest = sorted(_CACHE.items(), key=lambda item: item[1][0])[:40]
            for key, _value in oldest:
                _CACHE.pop(key, None)
    return payload


def clear_cache() -> None:
    with _LOCK:
        _CACHE.clear()


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def parse_open_meteo(payload: dict) -> Series:
    if payload.get("error"):
        reason = str(payload.get("reason") or "Open-Meteo returned an error.")
        return Series((), (), (), (), error=reason)
    hourly = payload.get("hourly") or {}
    units = payload.get("hourly_units") or {}
    times_raw = hourly.get("time") or []
    try:
        wind_unit = units["wind_speed_10m"]
        rain_unit = units["rain"]
        snow_unit = units["snowfall"]
        winds = []
        rains = []
        snows = []
        times = []
        for index, stamp in enumerate(times_raw):
            times.append(_parse_time(stamp))
            winds.append(_convert(hourly.get("wind_speed_10m"), index, wind_unit, wind_to_mph))
            rains.append(_convert(hourly.get("rain"), index, rain_unit, rain_to_inches_per_hour))
            snows.append(_convert(hourly.get("snowfall"), index, snow_unit, snow_depth_to_inches_per_hour))
    except (KeyError, ValueError, TypeError) as exc:
        return Series((), (), (), (), error=f"Weather units could not be read ({exc}).")
    return Series(tuple(times), tuple(winds), tuple(rains), tuple(snows))


def _convert(values, index: int, unit: str, converter) -> float | None:
    if values is None or index >= len(values):
        return None
    value = values[index]
    if value is None:
        return None
    return float(converter(float(value), unit))


def _dates(start: datetime, end: datetime) -> tuple[str, str]:
    start_day = start.astimezone(timezone.utc).date()
    end_day = end.astimezone(timezone.utc).date()
    if end_day < start_day:
        end_day = start_day
    if (end_day - start_day).days > 7:
        end_day = start_day + timedelta(days=7)
    return start_day.isoformat(), end_day.isoformat()


def _build_url(points: list[tuple[float, float]], start_date: str, end_date: str) -> str:
    lats = ",".join(f"{lat:.4f}" for lat, _lon in points)
    lons = ",".join(f"{lon:.4f}" for _lat, lon in points)
    return (
        f"{OPEN_METEO}?latitude={lats}&longitude={lons}"
        "&hourly=wind_speed_10m,rain,snowfall"
        "&wind_speed_unit=mph&precipitation_unit=inch&timezone=UTC"
        f"&start_date={start_date}&end_date={end_date}"
    )


def _clamp_from_error(payload: dict, start_date: str, end_date: str) -> tuple[str, str] | None:
    reason = str(payload.get("reason") or "")
    match = _RANGE_RE.search(reason)
    if not match:
        return None
    allowed_start, allowed_end = match.group(1), match.group(2)
    clamped_start = max(start_date, allowed_start)
    clamped_end = min(end_date, allowed_end)
    if clamped_start > clamped_end:
        return None
    if clamped_start == start_date and clamped_end == end_date:
        return None
    return clamped_start, clamped_end


def fetch_series(
    points: list[tuple[float, float]],
    start: datetime,
    end: datetime,
    fetch=http_json,
) -> list[Series]:
    """Return one series per input point. Failures are per-point errors, not zeros."""
    if not points:
        return []
    start_date, end_date = _dates(start, end)
    unique: list[tuple[float, float]] = []
    index_of: dict[tuple[float, float], int] = {}
    mapping: list[int] = []
    for lat, lon in points:
        key = (round(lat, 2), round(lon, 2))
        if key not in index_of:
            index_of[key] = len(unique)
            unique.append((key[0], key[1]))
        mapping.append(index_of[key])

    found: dict[int, Series] = {}

    def pull(batch_indexes: list[int], window: tuple[str, str]) -> None:
        batch_points = [unique[index] for index in batch_indexes]
        url = _build_url(batch_points, window[0], window[1])
        try:
            payload = _cached_get(url, fetch)
        except (HttpError, TimeoutError, OSError) as exc:
            error = Series((), (), (), (), error=str(exc))
            for index in batch_indexes:
                found[index] = error
            return
        if isinstance(payload, dict) and payload.get("error"):
            clamped = _clamp_from_error(payload, window[0], window[1])
            if clamped is not None:
                pull(batch_indexes, clamped)
                return
            error = Series((), (), (), (), error=str(payload.get("reason") or "Forecast unavailable."))
            for index in batch_indexes:
                found[index] = error
            return
        rows = payload if isinstance(payload, list) else [payload]
        if len(rows) != len(batch_indexes):
            error = Series((), (), (), (), error="Weather service returned an unexpected batch.")
            for index in batch_indexes:
                found[index] = error
            return
        for index, row in zip(batch_indexes, rows):
            found[index] = parse_open_meteo(row if isinstance(row, dict) else {"error": True, "reason": "Bad row"})

    batches = [list(range(start_i, min(start_i + 40, len(unique)))) for start_i in range(0, len(unique), 40)]
    # Bounded concurrency. A thread pool import stays local so tests can pass a fake fetch.
    from concurrent.futures import ThreadPoolExecutor

    workers = min(3, max(1, len(batches)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(lambda batch: pull(batch, (start_date, end_date)), batches))

    empty = Series((), (), (), (), error="Forecast was not returned for this point.")
    return [found.get(mapped, empty) for mapped in mapping]
