import pytest

from routing.logic.risk import (
    apply_load,
    classify_rain,
    classify_snow,
    classify_wind,
    combine,
)


@pytest.mark.parametrize(
    ("mph", "label"),
    [
        (0, "low"),
        (24.999, "low"),
        (25 - 1e-6, "low"),
        (25, "moderate"),
        (25 + 1e-6, "moderate"),
        (34, "moderate"),
        (34.5, "moderate"),
        (34.999, "moderate"),
        (35 - 1e-6, "moderate"),
        (35, "high"),
        (44, "high"),
        (44.5, "high"),
        (45 - 1e-6, "high"),
        (45, "severe"),
        (54, "severe"),
        (54.5, "severe"),
        (55 - 1e-6, "severe"),
        (55, "no_travel"),
        (55 + 1e-6, "no_travel"),
        (80, "no_travel"),
    ],
)
def test_wind_thresholds_and_continuous_gaps(mph, label):
    assert classify_wind(mph).label == label


@pytest.mark.parametrize(
    ("inches", "label"),
    [
        (0, "low"),
        (0.10 - 1e-6, "low"),
        (0.099, "low"),
        (0.10, "moderate"),
        (0.10 + 1e-6, "moderate"),
        (0.249, "moderate"),
        (0.25 - 1e-6, "moderate"),
        (0.25, "high"),
        (0.25 + 1e-6, "high"),
        (0.499, "high"),
        (0.50 - 1e-6, "high"),
        (0.50, "severe"),
        (0.50 + 1e-6, "severe"),
        (1, "severe"),
        (1.0, "severe"),
        (1 - 1e-6, "severe"),
        (1 + 1e-6, "no_travel"),
        (1.001, "no_travel"),
        (2, "no_travel"),
    ],
)
def test_rain_thresholds_including_overlap_and_exact_one_inch(inches, label):
    assert classify_rain(inches).label == label


@pytest.mark.parametrize(
    ("inches", "label"),
    [
        (0, "low"),
        (0.5 - 1e-6, "low"),
        (0.499, "low"),
        (0.5, "moderate"),
        (0.999, "moderate"),
        (1 - 1e-6, "moderate"),
        (1, "high"),
        (1.0, "high"),
        (1.999, "high"),
        (2 - 1e-6, "high"),
        (2, "severe"),
        (2.0, "severe"),
        (3 - 1e-6, "severe"),
        (3, "severe"),
        (3.0, "severe"),
        (3 + 1e-6, "no_travel"),
        (3.001, "no_travel"),
        (4, "no_travel"),
    ],
)
def test_snow_thresholds_including_exact_three_inches(inches, label):
    assert classify_snow(inches).label == label


def _adjusted(mph, load):
    wind = classify_wind(mph)
    return apply_load(wind, mph, load).label


def test_load_boundaries_are_strict_and_follow_continuous_wind_bands():
    assert _adjusted(45, 30_000) == "severe"
    assert _adjusted(45, 30_000.01) == "no_travel"
    assert _adjusted(54.999, 30_000) == "severe"
    assert _adjusted(54.999, 30_000.01) == "no_travel"
    assert _adjusted(54.5, 30_000) == "severe"
    assert _adjusted(54.5, 30_001) == "no_travel"
    assert _adjusted(35, 40_000) == "high"
    assert _adjusted(35, 40_000.01) == "severe"
    assert _adjusted(44.999, 40_000) == "high"
    assert _adjusted(44.999, 40_000.01) == "severe"
    assert _adjusted(44.5, 50_000) == "severe"
    assert _adjusted(34.999, 80_000) == "moderate"
    assert _adjusted(25, 80_000) == "moderate"
    assert _adjusted(45, 40_000.01) == "no_travel"
    assert _adjusted(55, 0) == "no_travel"
    assert _adjusted(55, 30_000) == "no_travel"
    assert _adjusted(55, 40_000) == "no_travel"
    assert _adjusted(80, 1) == "no_travel"


def test_combined_risk_is_the_max_and_missing_is_not_low():
    low = classify_wind(10)
    high = classify_rain(0.3)
    severe = classify_snow(2.5)
    assert combine([low, high, severe]).label == "severe"
    assert combine([classify_wind(60), low]).label == "no_travel"
    assert combine([low, None, low]) is None
    assert combine([None]) is None


def test_exact_outer_precipitation_stays_severe_when_combined():
    assert combine([classify_wind(0), classify_rain(1.0), classify_snow(0)]).label == "severe"
    assert combine([classify_wind(0), classify_rain(0), classify_snow(3.0)]).label == "severe"
    assert combine([classify_wind(0), classify_rain(1.001), classify_snow(0)]).label == "no_travel"
