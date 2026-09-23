"""Safe, local attack simulations for the six PUSHPAK scenarios."""

from __future__ import annotations

import numpy as np

from ..core.enums import AttackType
from .base import Attack, AttackContext, NoAttack
from .composite import CompositeAttack
from .scenarios import (
    CommandInjectionAttack,
    DosAttack,
    FirmwareIntegrityAttack,
    GpsSpoofingAttack,
    MavlinkAnomalyAttack,
    TelemetryManipulationAttack,
)

# Config-key / CLI name -> (Attack class, AttackType)
ATTACK_REGISTRY: dict[str, type[Attack]] = {
    "gps_spoofing": GpsSpoofingAttack,
    "mavlink_anomaly": MavlinkAnomalyAttack,
    "command_injection": CommandInjectionAttack,
    "telemetry_manipulation": TelemetryManipulationAttack,
    "dos": DosAttack,
    "firmware_integrity": FirmwareIntegrityAttack,
}

# Map AttackType -> config key for reverse lookups.
TYPE_TO_KEY: dict[AttackType, str] = {
    AttackType.GPS_SPOOFING: "gps_spoofing",
    AttackType.MAVLINK_ANOMALY: "mavlink_anomaly",
    AttackType.COMMAND_INJECTION: "command_injection",
    AttackType.TELEMETRY_MANIPULATION: "telemetry_manipulation",
    AttackType.DOS: "dos",
    AttackType.FIRMWARE_INTEGRITY: "firmware_integrity",
}


def build_attack(
    name: str,
    attacks_cfg: dict,
    rng: np.random.Generator | None = None,
    **kwargs,
) -> Attack:
    """Instantiate an attack by config key (or ``"benign"``/``"none"``).

    ``"a+b"`` builds a :class:`CompositeAttack` of ``a`` and ``b`` (simultaneous
    attacks); ``firmware_dir`` is passed only to the firmware component.
    """
    rng = rng or np.random.default_rng(1234)
    if name in ("benign", "none", "", None):
        return NoAttack(rng)
    if "+" in name:
        parts = [p.strip() for p in name.split("+") if p.strip()]
        comps = [build_attack(p, attacks_cfg, rng,
                              **(kwargs if p == "firmware_integrity" else {})) for p in parts]
        return CompositeAttack(comps, rng)
    if name not in ATTACK_REGISTRY:
        raise KeyError(f"unknown attack '{name}'; choices: {sorted(ATTACK_REGISTRY)}")
    cls = ATTACK_REGISTRY[name]
    cfg = attacks_cfg.get(name, {})
    return cls(cfg, rng, **kwargs)


__all__ = [
    "Attack",
    "AttackContext",
    "NoAttack",
    "CompositeAttack",
    "GpsSpoofingAttack",
    "MavlinkAnomalyAttack",
    "CommandInjectionAttack",
    "TelemetryManipulationAttack",
    "DosAttack",
    "FirmwareIntegrityAttack",
    "ATTACK_REGISTRY",
    "TYPE_TO_KEY",
    "build_attack",
]
