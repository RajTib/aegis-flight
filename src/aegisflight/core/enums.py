"""Enumerations shared across the AegisFlight IDS.

These enums are deliberately plain ``str`` subclasses so they serialise cleanly
to JSON, SQLite and the REST/WebSocket API without custom encoders.
"""

from __future__ import annotations

from enum import Enum


class AttackType(str, Enum):
    """Ground-truth / predicted attack categories.

    ``BENIGN`` is the "no attack" label. The remaining six map 1:1 onto the six
    representative attack scenarios named by the PUSHPAK challenge brief.
    """

    BENIGN = "BENIGN"
    GPS_SPOOFING = "GPS_SPOOFING"
    MAVLINK_ANOMALY = "MAVLINK_ANOMALY"
    COMMAND_INJECTION = "COMMAND_INJECTION"
    TELEMETRY_MANIPULATION = "TELEMETRY_MANIPULATION"
    DOS = "DOS"
    FIRMWARE_INTEGRITY = "FIRMWARE_INTEGRITY"

    @property
    def is_attack(self) -> bool:
        return self is not AttackType.BENIGN


class Severity(str, Enum):
    """Alert-state ladder used by the fusion engine.

    Ordered from calmest to most severe. ``rank`` gives a numeric ordering that
    the dashboard and fusion hysteresis logic rely on.
    """

    NORMAL = "NORMAL"
    WATCH = "WATCH"
    SUSPICIOUS = "SUSPICIOUS"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @property
    def rank(self) -> int:
        return _SEVERITY_RANK[self]

    @classmethod
    def from_rank(cls, rank: int) -> Severity:
        rank = max(0, min(rank, len(_SEVERITY_ORDER) - 1))
        return _SEVERITY_ORDER[rank]


_SEVERITY_ORDER = [
    Severity.NORMAL,
    Severity.WATCH,
    Severity.SUSPICIOUS,
    Severity.HIGH,
    Severity.CRITICAL,
]
_SEVERITY_RANK = {s: i for i, s in enumerate(_SEVERITY_ORDER)}


class DetectorName(str, Enum):
    """Stable identifiers for each detection layer (used in evidence & fusion)."""

    PROTOCOL = "protocol_rule"
    PHYSICS = "physics_consistency"
    ANOMALY = "ml_anomaly"
    INTEGRITY = "firmware_integrity"


class IntegrityStatus(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    UNKNOWN = "UNKNOWN"


class FlightPhase(str, Enum):
    GROUND = "GROUND"
    TAKEOFF = "TAKEOFF"
    CLIMB = "CLIMB"
    CRUISE = "CRUISE"
    TURN = "TURN"
    DESCENT = "DESCENT"
    LANDING = "LANDING"
