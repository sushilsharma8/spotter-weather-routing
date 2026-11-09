"""Unit conversions.

Snow is converted as snow depth, never as liquid water equivalent.
Open-Meteo `snowfall` is a depth (cm by default). `precipitation` is water
equivalent and must not be used as a snow-depth intensity.
"""

from __future__ import annotations

METERS_PER_MILE = 1609.344
MM_PER_INCH = 25.4
CM_PER_INCH = 2.54


def kmh_to_mph(kmh: float) -> float:
    return kmh * (1000.0 / METERS_PER_MILE)


def ms_to_mph(meters_per_second: float) -> float:
    return meters_per_second * (3600.0 / METERS_PER_MILE)


def mm_to_inches(mm: float) -> float:
    return mm / MM_PER_INCH


def snow_cm_to_inches(cm: float) -> float:
    """Snow-depth centimeters to inches. Not a water-equivalent conversion."""
    return cm / CM_PER_INCH


def meters_to_miles(meters: float) -> float:
    return meters / METERS_PER_MILE


def miles_to_meters(miles: float) -> float:
    return miles * METERS_PER_MILE


def wind_to_mph(value: float, unit: str) -> float:
    key = unit.strip().lower().replace(" ", "")
    if key in {"mp/h", "mph"}:
        return value
    if key in {"km/h", "kmh"}:
        return kmh_to_mph(value)
    if key in {"m/s", "ms"}:
        return ms_to_mph(value)
    raise ValueError(f"Unexpected wind unit: {unit}")


def rain_to_inches_per_hour(value: float, unit: str) -> float:
    key = unit.strip().lower()
    if key == "inch":
        return value
    if key == "mm":
        return mm_to_inches(value)
    raise ValueError(f"Unexpected rain unit: {unit}")


def snow_depth_to_inches_per_hour(value: float, unit: str) -> float:
    """Hourly snow-depth amount to inches per hour.

    A centimeter of snow depth is 1/2.54 inch of depth. It is not treated as
    a centimeter of water, and it is not divided by a 10:1 snow ratio.
    """
    key = unit.strip().lower()
    if key == "inch":
        return value
    if key == "cm":
        return snow_cm_to_inches(value)
    if key == "mm":
        return mm_to_inches(value)
    raise ValueError(f"Unexpected snowfall unit: {unit}")
