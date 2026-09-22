"""Simulator: determinism, physical plausibility, landing."""

import math

from aegisflight.config import load_config
from aegisflight.simulator import FlightSimulator, SimulatorConfig


def _states(route="survey_box"):
    cfg = load_config()
    cfg.simulation["route"] = route
    return FlightSimulator(SimulatorConfig.from_config(cfg.simulation)).run_list()


def test_tick_count():
    cfg = load_config()
    st = FlightSimulator(SimulatorConfig.from_config(cfg.simulation)).run_list()
    assert len(st) == int(cfg.simulation["duration_s"] * cfg.simulation["sample_rate_hz"])


def test_determinism():
    a = _states()
    b = _states()
    assert all(abs(x.lat - y.lat) < 1e-12 and abs(x.groundspeed - y.groundspeed) < 1e-12
               for x, y in zip(a, b, strict=True))


def test_reaches_cruise_and_lands():
    st = _states()
    assert abs(max(s.rel_alt for s in st) - 60.0) < 1.0
    assert st[-1].rel_alt < 1.0          # landed
    assert st[-1].armed is False


def test_speed_within_bounds():
    st = _states()
    assert max(s.groundspeed for s in st) < 14.0  # cruise 12 + margin


def test_all_routes_land():
    for route in ("survey_box", "out_and_back", "perimeter"):
        st = _states(route)
        assert st[-1].rel_alt < 1.5, route


def test_position_velocity_consistency():
    # dead-reckoning the true velocity reproduces the true position track.
    st = _states()
    s0, s1 = st[500], st[501]
    dt = s1.t - s0.t
    dn = math.radians(s1.lat - s0.lat) * 6_371_000.0
    assert abs(dn - s0.vx * dt) < 0.5  # within integration/jitter tolerance


def test_battery_monotonic_ish():
    st = _states()
    assert st[0].battery_remaining > st[-1].battery_remaining
    assert st[-1].battery_remaining > 25.0  # reserve
