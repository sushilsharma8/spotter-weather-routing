import pytest

from routing.logic.units import (
    kmh_to_mph,
    meters_to_miles,
    mm_to_inches,
    rain_to_inches_per_hour,
    snow_cm_to_inches,
    snow_depth_to_inches_per_hour,
    wind_to_mph,
)


def test_miles_and_wind_conversions():
    assert meters_to_miles(1609.344) == pytest.approx(1)
    assert kmh_to_mph(100) == pytest.approx(62.13711922)
    assert wind_to_mph(10, "mp/h") == 10
    assert wind_to_mph(10, "mph") == 10
    assert wind_to_mph(100, "km/h") == pytest.approx(kmh_to_mph(100))
    assert wind_to_mph(1, "m/s") == pytest.approx(2.23693629)


def test_rain_millimeters_are_inches_of_water():
    assert mm_to_inches(25.4) == pytest.approx(1)
    assert rain_to_inches_per_hour(2.54, "mm") == pytest.approx(0.1)
    assert rain_to_inches_per_hour(0.2, "inch") == pytest.approx(0.2)


def test_snow_depth_is_not_water_equivalent():
    assert snow_cm_to_inches(2.54) == pytest.approx(1)
    assert snow_depth_to_inches_per_hour(2.54, "cm") == pytest.approx(1)
    assert snow_depth_to_inches_per_hour(1.5, "inch") == pytest.approx(1.5)
    depth_inches = snow_cm_to_inches(1.0)
    water_inches = mm_to_inches(1.0)
    assert depth_inches == pytest.approx(1 / 2.54)
    assert water_inches == pytest.approx(1 / 25.4)
    # 1 cm of snow depth is a different quantity from 1 mm of liquid water.
    assert depth_inches > water_inches * 5


def test_unknown_unit_is_rejected():
    with pytest.raises(ValueError):
        wind_to_mph(10, "furlongs/fortnight")
    with pytest.raises(ValueError):
        snow_depth_to_inches_per_hour(1, "kg")
