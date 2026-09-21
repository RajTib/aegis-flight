"""Deterministic UAV flight simulator.

Produces a stream of :class:`~aegisflight.core.types.FlightState` ground-truth
samples for a small multirotor executing an autonomous mission (takeoff →
survey → return-to-launch → land). The model is a coordinated-turn point-mass
kinematic integrator: it is intentionally lightweight, but self-consistent, so
that a dead-reckoning detector fed the *true* velocity can reproduce the *true*
position to within integration error. That property is what makes GPS-spoofing
and telemetry-manipulation attacks detectable downstream.

Design contract
---------------
* ``FlightState`` emitted here is **clean ground truth**. Sensor noise is added
  later, at the MAVLink-encoding boundary (:mod:`aegisflight.mavlink`), and
  attacks perturb the *observed* stream — never this ground truth. The
  benchmark harness scores detector output against attack windows using this
  clean timeline as the reference.
* The simulator is fully deterministic given ``seed``; two runs with the same
  config produce identical timelines. RNG here is used only for tiny,
  reproducible "wind"/control jitter, not for the sensor noise model.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..core.enums import FlightPhase
from ..core.geo import offset_latlon
from ..core.types import FlightState

G = 9.80665  # gravitational acceleration, m/s^2


@dataclass(frozen=True)
class SimulatorConfig:
    """Resolved simulator parameters (parsed from the ``simulation`` config)."""

    seed: int = 42
    sample_rate_hz: float = 10.0
    duration_s: float = 120.0
    home_lat: float = 19.1334
    home_lon: float = 72.9133
    home_alt_msl: float = 12.0
    cruise_alt_m: float = 60.0
    cruise_speed_ms: float = 12.0
    route: str = "survey_box"
    battery_capacity_v: float = 25.2

    # Flight-profile shaping (sensible fixed values; not usually tuned).
    climb_rate_ms: float = 4.0
    descent_rate_ms: float = 3.0
    max_accel_ms2: float = 3.0
    max_yaw_rate_rad_s: float = 0.6
    waypoint_radius_m: float = 6.0

    @classmethod
    def from_config(cls, sim: dict[str, Any]) -> SimulatorConfig:
        home = sim.get("home", {})
        return cls(
            seed=int(sim.get("seed", 42)),
            sample_rate_hz=float(sim.get("sample_rate_hz", 10.0)),
            duration_s=float(sim.get("duration_s", 120.0)),
            home_lat=float(home.get("lat", 19.1334)),
            home_lon=float(home.get("lon", 72.9133)),
            home_alt_msl=float(home.get("alt_msl", 12.0)),
            cruise_alt_m=float(sim.get("cruise_alt_m", 60.0)),
            cruise_speed_ms=float(sim.get("cruise_speed_ms", 12.0)),
            route=str(sim.get("route", "survey_box")),
            battery_capacity_v=float(sim.get("battery_capacity_v", 25.2)),
        )

    @property
    def dt(self) -> float:
        return 1.0 / self.sample_rate_hz

    @property
    def n_ticks(self) -> int:
        return int(round(self.duration_s * self.sample_rate_hz))


def _route_waypoints(route: str, cruise_alt: float) -> list[tuple[float, float, float]]:
    """Return mission waypoints as (north_m, east_m, rel_alt_m) from home.

    Waypoints cover the *cruise* portion only; takeoff, RTL and landing are
    synthesised by the state machine around them.
    """
    a = cruise_alt
    if route == "out_and_back":
        return [(0, 0, a), (300, 0, a), (300, 0, a), (0, 0, a)]
    if route == "perimeter":
        return [(0, 0, a), (200, 0, a), (200, 150, a), (0, 150, a), (0, 0, a)]
    # default: survey_box — a lawnmower / boustrophedon coverage pattern
    wps: list[tuple[float, float, float]] = [(0, 0, a)]
    sweeps = 4
    length, spacing = 180.0, 45.0
    for i in range(sweeps):
        e = i * spacing
        if i % 2 == 0:
            wps.append((length, e, a))
            wps.append((length, e + spacing, a))
        else:
            wps.append((0.0, e, a))
            wps.append((0.0, e + spacing, a))
    return wps


class FlightSimulator:
    """Generates a deterministic ground-truth flight timeline.

    Usage::

        sim = FlightSimulator(SimulatorConfig.from_config(cfg.simulation))
        for state in sim.run():
            ...  # state is a clean FlightState
    """

    def __init__(self, config: SimulatorConfig) -> None:
        self.cfg = config
        self.rng = np.random.default_rng(config.seed)
        self.waypoints = _route_waypoints(config.route, config.cruise_alt_m)

    # -- internal helpers --------------------------------------------------- #

    def _battery(self, frac: float, throttle: float) -> tuple[float, float]:
        """Return (voltage, remaining_pct) for elapsed fraction ``frac``.

        A 6S LiPo sags from ~4.2 V/cell to ~3.6 V/cell across the discharge.
        Throttle adds a small transient sag so the physics detector sees a
        smooth, plausible curve (attacks introduce implausible jumps).
        """
        cells = 6
        v_full, v_empty = 4.2 * cells, 3.55 * cells
        # Reserve: only discharge to ~35% over the mission.
        used = min(0.65, frac * 0.65)
        base = v_full - (v_full - v_empty) * (used / 0.65)
        sag = 0.004 * (throttle - 50.0)  # volts of transient sag under load
        remaining = 100.0 - used * 100.0
        return base - sag, remaining

    # -- main generator ----------------------------------------------------- #

    def run(self) -> Iterator[FlightState]:
        cfg = self.cfg
        dt = cfg.dt
        n = cfg.n_ticks

        # Phase timing. Reserve enough time to fly home from the farthest
        # waypoint (RTL) *and* descend, so the mission actually lands on time.
        t_takeoff = cfg.cruise_alt_m / cfg.climb_rate_ms          # climb to cruise
        t_land = cfg.cruise_alt_m / cfg.descent_rate_ms           # descend to ground
        max_wp_dist = max((math.hypot(n, e) for n, e, _ in self.waypoints), default=0.0)
        rtl_reserve = max_wp_dist / max(1.0, cfg.cruise_speed_ms) + 4.0
        t_cruise_end = cfg.duration_s - t_land - rtl_reserve

        # Kinematic state (local NE frame, metres; heading rad from north).
        pos_n = pos_e = 0.0
        alt = 0.0
        speed = 0.0
        heading = 0.0
        wp_idx = 1  # index into self.waypoints (0 is home)
        prev_vx = prev_vy = prev_vz = 0.0
        prev_roll = prev_pitch = 0.0
        landing = False  # latched once the final descent begins

        for k in range(n):
            t = k * dt
            frac = t / cfg.duration_s

            # ---- determine phase & targets ------------------------------- #
            if t < t_takeoff:
                phase = FlightPhase.TAKEOFF if t < t_takeoff * 0.4 else FlightPhase.CLIMB
                mode = "TAKEOFF"
                target_alt = cfg.cruise_alt_m
                target_speed = 0.0
                tgt_n, tgt_e = 0.0, 0.0
            elif t > t_cruise_end or landing:
                # Return-to-launch, then a latched vertical landing. Latching
                # prevents an orbit limit-cycle: once we commit to landing we
                # descend where we are rather than re-chasing the home point.
                dist_home = math.hypot(pos_n, pos_e)
                if not landing and dist_home > cfg.waypoint_radius_m and alt > 1.0:
                    phase, mode = FlightPhase.CRUISE, "RTL"
                    target_alt, target_speed = cfg.cruise_alt_m, cfg.cruise_speed_ms
                    tgt_n, tgt_e = 0.0, 0.0
                else:
                    landing = True
                    phase, mode = FlightPhase.LANDING, "LAND"
                    target_alt, target_speed = 0.0, 0.0
                    tgt_n, tgt_e = pos_n, pos_e  # hold heading; decelerate & descend
            else:
                mode = "AUTO"
                tgt_n, tgt_e, tgt_alt = self.waypoints[wp_idx]
                target_alt = tgt_alt
                target_speed = cfg.cruise_speed_ms
                d = math.hypot(tgt_n - pos_n, tgt_e - pos_e)
                if d < cfg.waypoint_radius_m:
                    wp_idx += 1
                    if wp_idx >= len(self.waypoints):
                        wp_idx = 1  # loiter by re-flying the survey pattern
                phase = FlightPhase.CRUISE

            # ---- heading control ----------------------------------------- #
            desired_heading = heading
            if target_speed > 0.1 and (abs(tgt_n - pos_n) > 0.1 or abs(tgt_e - pos_e) > 0.1):
                desired_heading = math.atan2(tgt_e - pos_e, tgt_n - pos_n)
            dpsi = math.atan2(
                math.sin(desired_heading - heading), math.cos(desired_heading - heading)
            )
            max_dpsi = cfg.max_yaw_rate_rad_s * dt
            turning = abs(dpsi) > max_dpsi * 1.001
            dpsi = max(-max_dpsi, min(max_dpsi, dpsi))
            heading = (heading + dpsi) % (2 * math.pi)
            yawspeed = dpsi / dt
            if turning and phase == FlightPhase.CRUISE:
                phase = FlightPhase.TURN

            # ---- speed control ------------------------------------------- #
            accel = max(-cfg.max_accel_ms2, min(cfg.max_accel_ms2, (target_speed - speed) / dt))
            speed = max(0.0, speed + accel * dt)
            # tiny reproducible control jitter (wind), <1% of cruise
            speed += float(self.rng.normal(0.0, 0.02))
            speed = max(0.0, speed)

            # ---- integrate horizontal position --------------------------- #
            vx = speed * math.cos(heading)   # north
            vy = speed * math.sin(heading)   # east
            pos_n += vx * dt
            pos_e += vy * dt

            # ---- vertical control ---------------------------------------- #
            if alt < target_alt - 0.05:
                vz_up = min(cfg.climb_rate_ms, (target_alt - alt) / dt)
            elif alt > target_alt + 0.05:
                vz_up = -min(cfg.descent_rate_ms, (alt - target_alt) / dt)
            else:
                vz_up = 0.0
            alt = max(0.0, alt + vz_up * dt)
            vertical_speed = vz_up
            vz = -vz_up  # NED down-positive

            # ---- accelerations (finite difference) ----------------------- #
            ax = (vx - prev_vx) / dt
            ay = (vy - prev_vy) / dt
            az = (vz - prev_vz) / dt
            prev_vx, prev_vy, prev_vz = vx, vy, vz

            # ---- attitude ------------------------------------------------- #
            # Coordinated-turn bank angle: roll = atan(v * yawrate / g).
            roll = math.atan2(speed * yawspeed, G)
            # Pitch: nose down slightly to accelerate forward + climb component.
            pitch = math.atan2(vertical_speed, max(1.0, speed)) - 0.03 * accel
            yaw = math.atan2(math.sin(heading), math.cos(heading))
            rollspeed = (roll - prev_roll) / dt
            pitchspeed = (pitch - prev_pitch) / dt
            prev_roll, prev_pitch = roll, pitch

            # ---- throttle & battery -------------------------------------- #
            if vertical_speed > 0.2:
                throttle = 68.0
            elif vertical_speed < -0.2:
                throttle = 38.0
            elif speed > 1.0:
                throttle = 54.0
            else:
                throttle = 50.0
            voltage, remaining = self._battery(frac, throttle)

            # Armed for the whole sortie; disarm once landed.
            armed = not (mode == "LAND" and alt < 0.3)
            if not armed:
                phase = FlightPhase.GROUND

            # ---- geodetic conversion ------------------------------------- #
            lat, lon = offset_latlon(cfg.home_lat, cfg.home_lon, pos_n, pos_e)
            alt_msl = cfg.home_alt_msl + alt
            heading_deg = math.degrees(heading) % 360.0

            yield FlightState(
                t=t,
                lat=lat,
                lon=lon,
                alt_msl=alt_msl,
                rel_alt=alt,
                vx=vx,
                vy=vy,
                vz=vz,
                groundspeed=speed,
                vertical_speed=vertical_speed,
                ax=ax,
                ay=ay,
                az=az,
                roll=roll,
                pitch=pitch,
                yaw=yaw,
                rollspeed=rollspeed,
                pitchspeed=pitchspeed,
                yawspeed=yawspeed,
                heading=heading_deg,
                throttle=throttle,
                battery_voltage=voltage,
                battery_remaining=remaining,
                satellites=14,
                gps_fix_type=3,
                hdop=0.8,
                baro_alt=alt_msl,  # true; sensor noise/bias added at encode time
                flight_mode=mode,
                armed=armed,
                mission_seq=wp_idx,
                phase=phase,
            )

    def run_list(self) -> list[FlightState]:
        return list(self.run())
