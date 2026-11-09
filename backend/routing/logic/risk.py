"""Weather and load risk.

These bands follow the assessment thresholds. Where the source text is
ambiguous, the choices below are implementation assumptions, not source rules:

* Wind gaps are closed without rounding: [25, 35), [35, 45), [45, 55), >= 55.
* Overlapping inner rain/snow endpoints take the higher-risk band.
* Rain of exactly 1.00 in/hr and snow of exactly 3.0 in/hr stay Severe.
* Load cuts are strict greater-than 30,000 lb and 40,000 lb.
* Combined risk is the maximum component. Missing data is unknown, never Low.
"""

from __future__ import annotations

from enum import IntEnum


class Severity(IntEnum):
    LOW = 1
    MODERATE = 2
    HIGH = 3
    SEVERE = 4
    NO_TRAVEL = 5

    @property
    def label(self) -> str:
        return _LABELS[self]


_LABELS = {
    Severity.LOW: "low",
    Severity.MODERATE: "moderate",
    Severity.HIGH: "high",
    Severity.SEVERE: "severe",
    Severity.NO_TRAVEL: "no_travel",
}

LABEL_SCORE = {label: int(level) for level, label in _LABELS.items()}
SCORE_LABEL = {int(level): label for level, label in _LABELS.items()}


def classify_wind(mph: float) -> Severity:
    if mph < 25:
        return Severity.LOW
    if mph < 35:
        return Severity.MODERATE
    if mph < 45:
        return Severity.HIGH
    if mph < 55:
        return Severity.SEVERE
    return Severity.NO_TRAVEL


def classify_rain(inches_per_hour: float) -> Severity:
    if inches_per_hour < 0.10:
        return Severity.LOW
    if inches_per_hour < 0.25:
        return Severity.MODERATE
    if inches_per_hour < 0.50:
        return Severity.HIGH
    if inches_per_hour <= 1.00:
        return Severity.SEVERE
    return Severity.NO_TRAVEL


def classify_snow(inches_per_hour: float) -> Severity:
    if inches_per_hour < 0.5:
        return Severity.LOW
    if inches_per_hour < 1.0:
        return Severity.MODERATE
    if inches_per_hour < 2.0:
        return Severity.HIGH
    if inches_per_hour <= 3.0:
        return Severity.SEVERE
    return Severity.NO_TRAVEL


def apply_load(wind: Severity, wind_mph: float, load_lb: float) -> Severity:
    """Load overrides apply to the continuous wind bands, with strict > cuts."""
    if wind_mph >= 55 or wind is Severity.NO_TRAVEL:
        return Severity.NO_TRAVEL
    if 45 <= wind_mph < 55 and load_lb > 30_000:
        return Severity.NO_TRAVEL
    if 35 <= wind_mph < 45 and load_lb > 40_000:
        return Severity.SEVERE
    return wind


def combine(parts: list[Severity | None]) -> Severity | None:
    """Maximum component severity. Any missing component makes the result unknown."""
    if any(part is None for part in parts):
        return None
    winner = parts[0]
    assert winner is not None
    for part in parts[1:]:
        assert part is not None
        if part > winner:
            winner = part
    return winner


def max_severity(left: str | None, right: str | None) -> str | None:
    """Higher of two checkpoint labels. Unknown contaminates the segment."""
    if left is None or right is None or left == "unknown" or right == "unknown":
        return None
    return left if LABEL_SCORE[left] >= LABEL_SCORE[right] else right


def explain_checkpoint(
    *,
    wind_mph: float | None,
    rain_in_hr: float | None,
    snow_in_hr: float | None,
    load_lb: float,
    wind: Severity | None,
    wind_after_load: Severity | None,
    rain: Severity | None,
    snow: Severity | None,
    combined: Severity | None,
) -> str:
    bits: list[str] = []
    if wind_mph is None or wind is None:
        bits.append("Wind is missing, so it is not treated as Low.")
    else:
        text = f"Wind {wind_mph:.1f} mph is {wind.label}"
        if wind_after_load is not None and wind_after_load is not wind:
            text += f"; load {load_lb:,.0f} lb raises it to {wind_after_load.label}"
        bits.append(text + ".")
    if rain_in_hr is None or rain is None:
        bits.append("Rain is missing, so it is not treated as Low.")
    else:
        bits.append(f"Rain {rain_in_hr:.3f} in/hr is {rain.label}.")
    if snow_in_hr is None or snow is None:
        bits.append("Snow depth is missing, so it is not treated as Low.")
    else:
        bits.append(f"Snow depth {snow_in_hr:.3f} in/hr is {snow.label}.")
    if combined is None:
        bits.append("Combined risk is unavailable.")
    else:
        bits.append(f"Combined risk is {combined.label}, the highest component.")
    return " ".join(bits)
