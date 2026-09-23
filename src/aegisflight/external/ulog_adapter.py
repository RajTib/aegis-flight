"""PX4 ULog -> AegisFlight ``MessageEnvelope`` replay (navigation channels only).

A ULog is the *on-board* log, not the MAVLink link, so it can only reproduce
the **navigation / sensor-consistency** part of what the IDS sees. Network
features (message rate, inter-arrival jitter, sequence gaps, loss, command
rate) are NOT derivable from a ULog and are excluded from every comparison
(see ``docs/EXTERNAL_DATA.md``, category C/D).

Two explicit channel mappings are provided because the choice changes what
the physics checks mean:

``px4_telemetry`` (M1)
    What a PX4 vehicle actually streams over MAVLink (PX4 source:
    ``src/modules/mavlink/streams/GLOBAL_POSITION_INT.hpp`` / ``VFR_HUD.hpp``):
    GLOBAL_POSITION_INT lat/lon/alt = EKF global position, vx/vy = EKF local
    velocity; VFR_HUD.groundspeed = |EKF velocity|, VFR_HUD.alt = EKF altitude.
    Both "independent" channels therefore come from the same estimator.
``independent_sensors`` (M2)
    The assumption the AegisFlight simulator makes: position/velocity from the
    GNSS receiver (``vehicle_gps_position``/``sensor_gps``), groundspeed from the
    EKF, altitude from the barometer (``vehicle_air_data.baro_alt_meter``).
``independent_sensors_biascorr`` (M2b)
    As M2 but the barometer's pressure-altitude offset is removed *causally*
    using the median (baro - GNSS altitude) over the first 20 s of the log.

Envelopes are emitted only when a source topic has a *new* sample inside the
decision interval (no fabricated duplicate fixes); values are never
interpolated. Estimator outputs flagged invalid by PX4 (``xy_valid``,
``v_xy_valid``, ``z_valid``, ``z_global``) are **not** emitted -- invalid
estimates can contain garbage (hundreds of m/s were observed in one public log).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..core.types import MessageEnvelope

MAPPINGS = ("px4_telemetry", "independent_sensors", "independent_sensors_biascorr")

_TOPICS = [
    "vehicle_global_position",
    "vehicle_local_position",
    "vehicle_gps_position",
    "sensor_gps",
    "vehicle_air_data",
    "vehicle_attitude",
    "vehicle_land_detected",
]


@dataclass
class ULogFlight:
    path: str
    info: dict
    params: dict
    series: dict[str, dict[str, np.ndarray]] = field(default_factory=dict)

    @property
    def hardware(self) -> str:
        return str(self.info.get("ver_hw", ""))

    @property
    def is_simulation(self) -> bool:
        """True for SITL builds or HITL (``SYS_HITL`` != 0)."""
        return "SITL" in self.hardware or int(self.params.get("SYS_HITL", 0) or 0) != 0

    def has(self, topic: str) -> bool:
        return topic in self.series and len(self.series[topic]["t"]) > 0


def load_ulog(path: str | Path) -> ULogFlight:
    from pyulog import ULog  # optional dependency ("external" extra)

    u = ULog(str(path), message_name_filter_list=_TOPICS)
    series: dict[str, dict[str, np.ndarray]] = {}
    for d in u.data_list:
        if d.multi_id != 0 or d.name in series:
            continue
        cols = {k: np.asarray(v) for k, v in d.data.items()}
        cols["t"] = (cols["timestamp"].astype(np.float64) - float(u.start_timestamp)) / 1e6
        series[d.name] = cols
    return ULogFlight(path=str(path), info=dict(u.msg_info_dict),
                      params=dict(u.initial_parameters), series=series)


# --------------------------------------------------------------------------- #
# field helpers (handle PX4 message-definition changes across versions)
# --------------------------------------------------------------------------- #

def _gnss(fl: ULogFlight) -> dict[str, np.ndarray] | None:
    for topic in ("vehicle_gps_position", "sensor_gps"):
        if not fl.has(topic):
            continue
        s = fl.series[topic]
        if "latitude_deg" in s:
            lat, lon, alt = s["latitude_deg"], s["longitude_deg"], s["altitude_msl_m"]
        elif "lat" in s:
            lat, lon, alt = s["lat"] / 1e7, s["lon"] / 1e7, s["alt"] / 1e3
        else:
            continue
        return {"t": s["t"], "lat": lat.astype(float), "lon": lon.astype(float),
                "alt": alt.astype(float),
                "vn": s.get("vel_n_m_s", np.full(len(lat), np.nan)).astype(float),
                "ve": s.get("vel_e_m_s", np.full(len(lat), np.nan)).astype(float),
                "fix": s.get("fix_type", np.full(len(lat), 3)).astype(int)}
    return None


def _yaw(fl: ULogFlight) -> dict[str, np.ndarray] | None:
    if not fl.has("vehicle_attitude"):
        return None
    s = fl.series["vehicle_attitude"]
    q0, q1, q2, q3 = (s[f"q[{i}]"].astype(float) for i in range(4))
    yaw = np.arctan2(2 * (q0 * q3 + q1 * q2), 1 - 2 * (q2 * q2 + q3 * q3))
    roll = np.arctan2(2 * (q0 * q1 + q2 * q3), 1 - 2 * (q1 * q1 + q2 * q2))
    pitch = np.arcsin(np.clip(2 * (q0 * q2 - q3 * q1), -1, 1))
    return {"t": s["t"], "yaw": yaw, "roll": roll, "pitch": pitch}


def airborne_mask(fl: ULogFlight, t: np.ndarray) -> np.ndarray:
    """Zero-order-hold ``landed == False`` from vehicle_land_detected (else all False)."""
    if not fl.has("vehicle_land_detected"):
        return np.zeros(len(t), dtype=bool)
    s = fl.series["vehicle_land_detected"]
    idx = np.searchsorted(s["t"], t, side="right") - 1
    ok = idx >= 0
    landed = np.ones(len(t), dtype=bool)
    landed[ok] = s["landed"][idx[ok]].astype(bool)
    return ~landed


def missing_requirements(fl: ULogFlight, mapping: str) -> list[str]:
    need = ["vehicle_local_position", "vehicle_attitude", "vehicle_land_detected"]
    if mapping == "px4_telemetry":
        need.append("vehicle_global_position")
    else:
        need.append("vehicle_air_data")
    miss = [n for n in need if not fl.has(n)]
    if mapping != "px4_telemetry" and _gnss(fl) is None:
        miss.append("vehicle_gps_position|sensor_gps")
    return miss


# --------------------------------------------------------------------------- #
# envelope synthesis
# --------------------------------------------------------------------------- #

class _Seq:
    def __init__(self) -> None:
        self.n = 0

    def __call__(self) -> int:
        self.n = (self.n + 1) % 256
        return self.n


def _env(t: float, name: str, fields: dict, seq: _Seq) -> MessageEnvelope:
    return MessageEnvelope(recv_time=float(t), sysid=1, compid=1, msgid=0, msgname=name,
                           seq=seq(), signed=False, byte_len=0, fields=fields)


def _new_idx(ts: np.ndarray, t0: float, t1: float) -> int | None:
    """Index of the latest sample with t0 < ts <= t1, else None (no new data)."""
    i = int(np.searchsorted(ts, t1, side="right")) - 1
    if i < 0 or ts[i] <= t0:
        return None
    return i


def _flag(series: dict, name: str, i: int) -> bool:
    """PX4 validity flag (True when the field is absent, i.e. older logs)."""
    return bool(series[name][i]) if name in series else True


def _hold(ts: np.ndarray, t: float) -> int | None:
    i = int(np.searchsorted(ts, t, side="right")) - 1
    return i if i >= 0 else None


def replay_ticks(fl: ULogFlight, mapping: str, dt: float = 0.2):
    """Yield ``(t, [MessageEnvelope, ...])`` every ``dt`` seconds of log time."""
    if mapping not in MAPPINGS:
        raise ValueError(f"unknown mapping {mapping!r}; choose from {MAPPINGS}")
    lpos = fl.series["vehicle_local_position"]
    att = _yaw(fl)
    gnss = _gnss(fl)
    gpos = fl.series.get("vehicle_global_position")
    air = fl.series.get("vehicle_air_data")
    seq = _Seq()

    baro_off = 0.0
    if mapping == "independent_sensors_biascorr" and gnss is not None and air is not None:
        t_end = gnss["t"][0] + 20.0
        sel = gnss["t"] <= t_end
        ia = np.clip(np.searchsorted(air["t"], gnss["t"][sel]), 0, len(air["t"]) - 1)
        diffs = air["baro_alt_meter"][ia].astype(float) - gnss["alt"][sel]
        baro_off = float(np.nanmedian(diffs)) if len(diffs) else 0.0

    t_start = float(lpos["t"][0])
    t_stop = float(lpos["t"][-1])
    t = t_start + dt
    while t <= t_stop:
        msgs: list[MessageEnvelope] = []
        il = _hold(lpos["t"], t)
        if il is None:
            t += dt
            continue
        vx, vy, vz = (float(lpos[k][il]) for k in ("vx", "vy", "vz"))
        vel_ok = _flag(lpos, "v_xy_valid", il) and _flag(lpos, "xy_valid", il)
        # ---- position channel ----
        if mapping == "px4_telemetry":
            ig = _new_idx(gpos["t"], t - dt, t)
            if ig is not None and vel_ok:
                lat, lon, alt = (float(gpos[k][ig]) for k in ("lat", "lon", "alt"))
                msgs.append(_env(t, "GLOBAL_POSITION_INT", {
                    "lat": int(lat * 1e7), "lon": int(lon * 1e7), "alt": int(alt * 1000),
                    "relative_alt": int(-float(lpos["z"][il]) * 1000),
                    "vx": int(vx * 100), "vy": int(vy * 100), "vz": int(vz * 100)}, seq))
        else:
            ig = _new_idx(gnss["t"], t - dt, t)
            if ig is not None and gnss["fix"][ig] >= 3 and not math.isnan(gnss["vn"][ig]):
                msgs.append(_env(t, "GLOBAL_POSITION_INT", {
                    "lat": int(gnss["lat"][ig] * 1e7), "lon": int(gnss["lon"][ig] * 1e7),
                    "alt": int(gnss["alt"][ig] * 1000),
                    "relative_alt": int(-float(lpos["z"][il]) * 1000),
                    "vx": int(gnss["vn"][ig] * 100), "vy": int(gnss["ve"][ig] * 100),
                    "vz": int(vz * 100)}, seq))
        # ---- groundspeed / altitude channel (VFR_HUD) ----
        if mapping == "px4_telemetry":
            ref_alt = float(lpos["ref_alt"][il]) if "ref_alt" in lpos else float("nan")
            if not (_flag(lpos, "z_valid", il) and _flag(lpos, "z_global", il)):
                ref_alt = float("nan")
            if math.isnan(ref_alt) and gpos is not None:
                ih = _hold(gpos["t"], t)
                vfr_alt = float(gpos["alt"][ih]) if ih is not None else float("nan")
            else:
                vfr_alt = -float(lpos["z"][il]) + ref_alt
        else:
            ia = _hold(air["t"], t)
            vfr_alt = float(air["baro_alt_meter"][ia]) - baro_off if ia is not None else float("nan")
        if not math.isnan(vfr_alt) and vel_ok:
            msgs.append(_env(t, "VFR_HUD", {
                "groundspeed": math.hypot(vx, vy), "heading": 0, "throttle": 0,
                "alt": vfr_alt, "climb": -vz}, seq))
        # ---- attitude ----
        if att is not None:
            ia2 = _hold(att["t"], t)
            if ia2 is not None:
                msgs.append(_env(t, "ATTITUDE", {
                    "roll": float(att["roll"][ia2]), "pitch": float(att["pitch"][ia2]),
                    "yaw": float(att["yaw"][ia2]), "rollspeed": 0.0, "pitchspeed": 0.0,
                    "yawspeed": 0.0}, seq))
        yield t, msgs
        t += dt
