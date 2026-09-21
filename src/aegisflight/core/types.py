"""Core dataclasses that flow through the AegisFlight pipeline.

Design notes
------------
* ``FlightState`` is the simulator's *ground truth*. The production IDS must
  never see it; only the benchmark harness may use it to score predictions.
* ``TelemetrySnapshot`` is what the IDS reconstructs from decoded MAVLink
  messages -- i.e. the *observed* (possibly attacked) world.
* We use plain ``@dataclass`` (not Pydantic) on the hot path for speed; the API
  layer converts to Pydantic models at its boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .enums import (
    AttackType,
    DetectorName,
    FlightPhase,
    IntegrityStatus,
    Severity,
)


@dataclass
class FlightState:
    """Ground-truth physical state of the vehicle at one simulator tick."""

    t: float  # seconds since session start
    lat: float
    lon: float
    alt_msl: float  # metres above mean sea level
    rel_alt: float  # metres above home
    # Velocity in local NED-ish ground frame (m/s)
    vx: float  # north
    vy: float  # east
    vz: float  # down (positive = descending)
    groundspeed: float
    vertical_speed: float  # positive up (m/s)
    # Body acceleration magnitude proxies (m/s^2)
    ax: float
    ay: float
    az: float
    # Attitude (radians)
    roll: float
    pitch: float
    yaw: float
    rollspeed: float
    pitchspeed: float
    yawspeed: float
    heading: float  # degrees 0..360
    throttle: float  # 0..100
    battery_voltage: float
    battery_remaining: float  # percent 0..100
    satellites: int
    gps_fix_type: int  # 0-1 none, 2 2D, 3 3D, 4 DGPS, 5 RTK float, 6 RTK fixed
    hdop: float
    baro_alt: float
    flight_mode: str
    armed: bool
    mission_seq: int
    phase: FlightPhase = FlightPhase.GROUND


@dataclass
class MessageEnvelope:
    """A single decoded MAVLink message plus link/transport metadata.

    ``fields`` holds the message payload as a plain dict (msg.to_dict() minus
    mavpackettype) so downstream code never depends on pymavlink object types.
    """

    recv_time: float  # monotonic-ish seconds, assigned by the ingestor
    sysid: int
    compid: int
    msgid: int
    msgname: str
    seq: int
    signed: bool
    byte_len: int
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class TelemetrySnapshot:
    """Observed telemetry as reconstructed by the IDS from MAVLink messages.

    All fields are Optional-ish; ``None`` means "not yet received". The IDS
    keeps the most recent value of each and stamps ``t`` from the latest
    position message.
    """

    t: float
    lat: float | None = None
    lon: float | None = None
    alt_msl: float | None = None
    rel_alt: float | None = None
    vx: float | None = None
    vy: float | None = None
    vz: float | None = None
    groundspeed: float | None = None
    vertical_speed: float | None = None
    heading: float | None = None
    roll: float | None = None
    pitch: float | None = None
    yaw: float | None = None
    rollspeed: float | None = None
    pitchspeed: float | None = None
    yawspeed: float | None = None
    throttle: float | None = None
    battery_voltage: float | None = None
    battery_remaining: float | None = None
    satellites: int | None = None
    gps_fix_type: int | None = None
    hdop: float | None = None
    baro_alt: float | None = None
    flight_mode: str | None = None
    armed: bool | None = None
    mission_seq: int | None = None
    # freshness: seconds since each subsystem last updated (filled by ingestor)
    gps_age: float = 0.0
    attitude_age: float = 0.0


@dataclass
class DetectorResult:
    """Output of a single detection layer for one decision tick."""

    detector: DetectorName
    score: float  # normalised 0..1 threat contribution
    triggered: bool
    evidence: list[str] = field(default_factory=list)
    # attack-type -> weight this detector assigns (unnormalised votes)
    attack_votes: dict[AttackType, float] = field(default_factory=dict)
    # raw named signals for transparency / dashboards
    signals: dict[str, float] = field(default_factory=dict)


@dataclass
class ThreatAssessment:
    """Fused decision for one decision tick."""

    t: float
    wall_time: float
    threat: bool
    threat_score: float  # 0..1
    severity: Severity
    attack_type: AttackType
    confidence: float  # 0..1 (a score, not a calibrated probability)
    secondary_indicators: list[AttackType] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    detector_scores: dict[str, float] = field(default_factory=dict)
    contributing_detectors: list[str] = field(default_factory=list)
    integrity_status: IntegrityStatus = IntegrityStatus.UNKNOWN
    latency_ms: float = 0.0
    # a compact snapshot of the telemetry that drove this decision
    telemetry: dict[str, Any] = field(default_factory=dict)
    is_alert: bool = False  # True only when this crosses the alert threshold + dedup

    def to_dict(self) -> dict[str, Any]:
        return {
            "t": round(self.t, 3),
            "wall_time": self.wall_time,
            "threat": self.threat,
            "threat_score": round(self.threat_score, 4),
            "severity": self.severity.value,
            "attack_type": self.attack_type.value,
            "confidence": round(self.confidence, 4),
            "secondary_indicators": [a.value for a in self.secondary_indicators],
            "evidence": self.evidence,
            "detector_scores": {k: round(v, 4) for k, v in self.detector_scores.items()},
            "contributing_detectors": self.contributing_detectors,
            "integrity_status": self.integrity_status.value,
            "latency_ms": round(self.latency_ms, 4),
            "telemetry": self.telemetry,
            "is_alert": self.is_alert,
        }
