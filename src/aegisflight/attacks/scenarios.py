"""The six PUSHPAK attack scenarios, as safe local simulations.

Each maps 1:1 onto an :class:`AttackType`. Value attacks override
:meth:`perturb_state`; stream attacks override :meth:`perturb_packets` (and
sometimes :meth:`before_encode`); firmware tampering drives
:meth:`integrity_status` against a real SHA-256 manifest.
"""

from __future__ import annotations

import math
import tempfile
from dataclasses import replace
from pathlib import Path

from ..core.enums import AttackType, IntegrityStatus
from ..core.geo import offset_latlon
from ..integrity.verifier import FirmwareVerifier
from ..mavlink.codec import RawPacket
from .base import Attack, AttackContext


# --------------------------------------------------------------------------- #
# 1. GPS spoofing (value attack)
# --------------------------------------------------------------------------- #
class GpsSpoofingAttack(Attack):
    attack_type = AttackType.GPS_SPOOFING

    def __init__(self, cfg, rng):
        super().__init__(cfg, rng)
        self.offset_m = float(cfg.get("offset_m", 120.0))
        self.bearing = math.radians(float(cfg.get("bearing_deg", 90.0)))
        self.drift_rate = float(cfg.get("drift_rate_ms", 6.0))
        self._frozen: tuple[float, float] | None = None

    def perturb_state(self, t, state):
        if not self.active(t):
            return state
        if self.mode == "replay_freeze":
            if self._frozen is None:
                self._frozen = (state.lat, state.lon)
            return replace(state, lat=self._frozen[0], lon=self._frozen[1])
        if self.mode == "sudden_offset":
            dist = self.offset_m
        else:  # gradual_drift
            dist = self.drift_rate * self.elapsed(t)
        north = dist * math.cos(self.bearing)
        east = dist * math.sin(self.bearing)
        lat, lon = offset_latlon(state.lat, state.lon, north, east)
        return replace(state, lat=lat, lon=lon)


# --------------------------------------------------------------------------- #
# 2. Telemetry manipulation (value attack)
# --------------------------------------------------------------------------- #
class TelemetryManipulationAttack(Attack):
    attack_type = AttackType.TELEMETRY_MANIPULATION

    def __init__(self, cfg, rng):
        super().__init__(cfg, rng)
        self.alt_bias = float(cfg.get("altitude_bias_m", 35.0))
        self.speed_bias = float(cfg.get("speed_bias_ms", 9.0))
        self.batt_jump = float(cfg.get("battery_jump_pct", 30.0))
        self._frozen_att: tuple[float, float, float] | None = None

    def perturb_state(self, t, state):
        if not self.active(t):
            return state
        if self.mode == "altitude_bias":
            # Bias the GPS/EKF altitude but not the baro channel -> mismatch.
            return replace(
                state, alt_msl=state.alt_msl + self.alt_bias, rel_alt=state.rel_alt + self.alt_bias
            )
        if self.mode == "speed_mismatch":
            # Report an inflated groundspeed while GPS velocity stays truthful.
            return replace(state, groundspeed=state.groundspeed + self.speed_bias)
        if self.mode == "battery_jump":
            # Erratic battery telemetry: large, alternating tick-to-tick swings.
            tick = int(round(t * 10))
            sign = 1.0 if tick % 2 == 0 else -1.0
            dv = sign * (self.batt_jump / 100.0) * 6.0  # up to ~1.8 V swing
            return replace(
                state,
                battery_voltage=state.battery_voltage + dv,
                battery_remaining=max(0.0, state.battery_remaining - self.batt_jump * (tick % 2)),
            )
        if self.mode == "frozen_attitude":
            if self._frozen_att is None:
                self._frozen_att = (state.roll, state.pitch, state.yaw)
            r, p, y = self._frozen_att
            return replace(state, roll=r, pitch=p, yaw=y)
        return state


# --------------------------------------------------------------------------- #
# 3. MAVLink anomaly (stream attack)
# --------------------------------------------------------------------------- #
class MavlinkAnomalyAttack(Attack):
    attack_type = AttackType.MAVLINK_ANOMALY

    def __init__(self, cfg, rng):
        super().__init__(cfg, rng)
        self.rogue_sysid = int(cfg.get("rogue_sysid", 42))
        self.rogue_compid = int(cfg.get("rogue_compid", 1))
        self.rate_multiplier = float(cfg.get("rate_multiplier", 5.0))
        self.loss_prob = float(cfg.get("loss_prob", 0.5))

    def before_encode(self, t, tick, encoder):
        if self.active(t) and self.mode == "seq_scramble":
            # Jump the vehicle's sequence counter to a random base each tick,
            # producing large (but correctly-CRC'd) sequence gaps.
            encoder.seq_by_src[(encoder.sysid, encoder.compid)] = int(self.rng.integers(0, 256))

    def perturb_packets(self, t, packets, ctx: AttackContext):
        if not self.active(t):
            return packets
        if self.mode == "rogue_sysid":
            rogue = ctx.encoder.encode_as(
                ctx.state, self.rogue_sysid, self.rogue_compid,
                ("HEARTBEAT", "GLOBAL_POSITION_INT"), send_time=t,
            )
            return packets + rogue
        if self.mode == "rate_spike":
            extra = max(0, int(self.rate_multiplier) - 1)
            return packets + [RawPacket(p.send_time, p.data) for _ in range(extra) for p in packets]
        if self.mode == "packet_loss":
            return [p for p in packets if self.rng.random() > self.loss_prob]
        # seq_scramble handled in before_encode
        return packets


# --------------------------------------------------------------------------- #
# 4. Command injection (stream attack)
# --------------------------------------------------------------------------- #
class CommandInjectionAttack(Attack):
    """Rogue commands.

    ``gcs_replay`` re-sends a previously legitimate ``MAV_CMD_DO_SET_MODE``
    *from the legitimate GCS identity* (sysid 255 / compid 190). Without
    MAVLink-2 message signing nothing on the wire distinguishes it from the real
    operator, so it is deliberately included as a **known-gap** case: the
    provenance rule cannot fire on it by design.
    """

    attack_type = AttackType.COMMAND_INJECTION

    def __init__(self, cfg, rng):
        super().__init__(cfg, rng)
        self.src_sysid = int(cfg.get("source_sysid", 66))
        self.src_compid = int(cfg.get("source_compid", 200))
        self.command = str(cfg.get("command", "MAV_CMD_COMPONENT_ARM_DISARM"))
        self.burst = int(cfg.get("burst", 6))
        self.replay_sysid = int(cfg.get("replay_sysid", 255))
        self.replay_compid = int(cfg.get("replay_compid", 190))

    def perturb_packets(self, t, packets, ctx: AttackContext):
        if not self.active(t):
            return packets
        # Inject at ~2 Hz so a burst exceeds command_burst_max within its window.
        if ctx.tick % 5 != 0:
            return packets
        injected: list[RawPacket] = []
        if self.mode == "arm_disarm_burst":
            for i in range(self.burst):
                injected.append(ctx.encoder.encode_command_long(
                    t, "MAV_CMD_COMPONENT_ARM_DISARM",
                    sysid=self.src_sysid, compid=self.src_compid,
                    params=(float(i % 2),),  # alternate arm(1)/disarm(0)
                ))
        elif self.mode == "gcs_replay":
            # One replayed legit-GCS mode command every 2 s (tick % 20), not a burst.
            if ctx.tick % 20 != 0:
                return packets
            injected.append(ctx.encoder.encode_command_long(
                t, "MAV_CMD_DO_SET_MODE",
                sysid=self.replay_sysid, compid=self.replay_compid, params=(1.0, 6.0),  # -> RTL
            ))
        elif self.mode == "mode_flip":
            injected.append(ctx.encoder.encode_command_long(
                t, "MAV_CMD_DO_SET_MODE",
                sysid=self.src_sysid, compid=self.src_compid, params=(1.0, 9.0),  # -> LAND
            ))
        else:  # rogue_command
            injected.append(ctx.encoder.encode_command_long(
                t, self.command, sysid=self.src_sysid, compid=self.src_compid, params=(1.0,),
            ))
        return packets + injected


# --------------------------------------------------------------------------- #
# 5. Denial of service (stream attack)
# --------------------------------------------------------------------------- #
class DosAttack(Attack):
    """Link / channel denial.

    ``gnss_jamming`` models RF denial of the GNSS channel (not the telemetry
    link): the receiver loses its fix (fix_type 1, 0-3 satellites, HDOP 99.99)
    while the autopilot keeps streaming its dead-reckoned GLOBAL_POSITION_INT.
    It is scored under the DOS class (denial of the navigation channel); a
    dedicated GPS_JAMMING class would need enum/dashboard changes (future work).
    """

    attack_type = AttackType.DOS

    def __init__(self, cfg, rng):
        super().__init__(cfg, rng)
        self.flood_multiplier = float(cfg.get("flood_multiplier", 12.0))
        self.blackout_prob = float(cfg.get("blackout_prob", 0.9))
        self.latency_ms = float(cfg.get("latency_ms", 400.0))

    def perturb_state(self, t, state):
        if not self.active(t) or self.mode != "gnss_jamming":
            return state
        return replace(state, gps_fix_type=1, satellites=int(self.rng.integers(0, 4)), hdop=99.99)

    def perturb_packets(self, t, packets, ctx: AttackContext):
        if not self.active(t):
            return packets
        if self.mode == "gnss_jamming":
            return packets  # value attack only, see perturb_state
        if self.mode == "flood":
            extra = max(1, int(self.flood_multiplier) - 1)
            flood = [RawPacket(p.send_time, p.data) for _ in range(extra) for p in packets]
            return packets + flood
        if self.mode == "blackout":
            return [p for p in packets if self.rng.random() > self.blackout_prob]
        if self.mode == "latency":
            # Jittered delay -> erratic inter-arrival + stale telemetry.
            return [
                RawPacket(p.send_time + self.rng.uniform(0.2, 1.0) * self.latency_ms / 1000.0, p.data)
                for p in packets
            ]
        return packets


# --------------------------------------------------------------------------- #
# 6. Firmware integrity (file tampering; drives the SHA-256 verifier)
# --------------------------------------------------------------------------- #
class FirmwareIntegrityAttack(Attack):
    attack_type = AttackType.FIRMWARE_INTEGRITY

    def __init__(self, cfg, rng, firmware_dir: Path | str | None = None):
        super().__init__(cfg, rng)
        self.tamper_component = str(cfg.get("tamper_component", "ekf3_params.bin"))
        if firmware_dir is None:
            firmware_dir = Path(tempfile.mkdtemp(prefix="aegis_fw_"))
        self.verifier = FirmwareVerifier(firmware_dir)
        # Only lay down the pristine fixture + manifest if the directory the IDS
        # verifier watches hasn't already been provisioned (shared filesystem).
        self.verifier.ensure_fixture()
        self._tampered = False
        self._cached_status: IntegrityStatus | None = None

    def active(self, t):
        # No duration in config -> integrity stays compromised until session end.
        return t >= self.start_s

    def integrity_status(self, t) -> IntegrityStatus:
        if t < self.start_s:
            return IntegrityStatus.VALID
        if not self._tampered:
            self.verifier.tamper(self.tamper_component)
            self._tampered = True
            self._cached_status = self.verifier.verify().status  # real SHA-256 check
        return self._cached_status or IntegrityStatus.INVALID

    def report(self):
        return self.verifier.verify()
