"""Attack interface.

Every attack is a **safe, local simulation**: it perturbs either the telemetry
*values* (before MAVLink encoding) or the packet *stream* (after encoding), or —
for firmware tampering — a set of local files hashed by the integrity verifier.
Nothing here touches a real network, radio, or vehicle.

Two perturbation hooks keep value-attacks and stream-attacks cleanly separated:

* :meth:`perturb_state` runs on the clean ``FlightState`` *before* encoding —
  used by GPS spoofing and telemetry manipulation.
* :meth:`perturb_packets` runs on the encoded ``RawPacket`` list *after*
  encoding — used by MAVLink anomalies, command injection, and DoS. It may
  drop, duplicate, delay, re-id, or inject packets (via the encoder in the
  context).

The ground-truth :meth:`label` (attack window) is used **only** by the
benchmark harness to score detections — never by the detectors themselves.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..core.enums import AttackType, IntegrityStatus
from ..core.types import FlightState
from ..mavlink.codec import MavlinkEncoder, RawPacket


@dataclass
class AttackContext:
    """Everything a stream-perturbation needs to synthesise/modify packets."""

    t: float
    tick: int
    encoder: MavlinkEncoder
    rng: np.random.Generator
    state: FlightState  # clean ground truth this tick (for impersonation)


class Attack:
    """Base class; subclasses override the hooks they need."""

    attack_type: AttackType = AttackType.BENIGN

    def __init__(self, cfg: dict, rng: np.random.Generator) -> None:
        self.cfg = cfg or {}
        self.rng = rng
        self.start_s = float(self.cfg.get("start_s", 0.0))
        self.duration_s = float(self.cfg.get("duration_s", 0.0))
        self.mode = str(self.cfg.get("mode", ""))

    # -- timing ------------------------------------------------------------- #

    def active(self, t: float) -> bool:
        return self.start_s <= t < self.start_s + self.duration_s

    def elapsed(self, t: float) -> float:
        return max(0.0, t - self.start_s)

    def label(self, t: float) -> AttackType:
        return self.attack_type if self.active(t) else AttackType.BENIGN

    def window(self) -> tuple[float, float]:
        return self.start_s, self.start_s + self.duration_s

    # -- perturbation hooks (default = identity) ---------------------------- #

    def before_encode(self, t: float, tick: int, encoder: MavlinkEncoder) -> None:
        """Hook that runs *before* the vehicle's messages are encoded.

        Lets an attack tamper with encoder state (e.g. jump the per-source
        sequence counter for a sequence-scramble anomaly) so the resulting
        frames are still correctly CRC'd but sequence-anomalous.
        """
        return None

    def perturb_state(self, t: float, state: FlightState) -> FlightState:
        return state

    def perturb_packets(
        self, t: float, packets: list[RawPacket], ctx: AttackContext
    ) -> list[RawPacket]:
        return packets

    def integrity_status(self, t: float) -> IntegrityStatus:
        return IntegrityStatus.VALID


class NoAttack(Attack):
    """The benign scenario: no perturbation, label always BENIGN."""

    attack_type = AttackType.BENIGN

    def __init__(self, rng: np.random.Generator | None = None) -> None:
        super().__init__({}, rng or np.random.default_rng(0))

    def active(self, t: float) -> bool:
        return False
