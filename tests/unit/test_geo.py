"""Unit tests for the geodesy helpers."""

import math

from aegisflight.core.geo import bearing_deg, haversine_m, offset_latlon, wrap_deg_180


def test_haversine_zero():
    assert haversine_m(19.0, 72.0, 19.0, 72.0) == 0.0


def test_offset_then_haversine_roundtrip():
    lat, lon = 19.1334, 72.9133
    lat2, lon2 = offset_latlon(lat, lon, 100.0, 0.0)  # 100 m north
    d = haversine_m(lat, lon, lat2, lon2)
    assert abs(d - 100.0) < 0.5


def test_offset_east():
    lat, lon = 19.1334, 72.9133
    lat2, lon2 = offset_latlon(lat, lon, 0.0, 250.0)
    assert abs(haversine_m(lat, lon, lat2, lon2) - 250.0) < 1.0
    assert abs(bearing_deg(lat, lon, lat2, lon2) - 90.0) < 1.0


def test_bearing_north():
    lat, lon = 19.0, 72.0
    lat2, lon2 = offset_latlon(lat, lon, 100.0, 0.0)
    assert abs(bearing_deg(lat, lon, lat2, lon2) - 0.0) < 1.0


def test_wrap_deg():
    assert wrap_deg_180(190.0) == -170.0
    assert wrap_deg_180(-190.0) == 170.0
    assert wrap_deg_180(0.0) == 0.0
    assert math.isclose(wrap_deg_180(180.0), 180.0)
