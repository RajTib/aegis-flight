"""Detector A — protocol / rule engine.

Stateless per-frame rules over MAVLink transport behaviour: aggregate message
rate, per-source sequence gaps, rogue system IDs, heartbeat / GPS liveness,
message signing, and command provenance. Each rule contributes a normalised
sub-score and a vote for the attack class it implies; the detector's score is
the strongest sub-score.
"""

from __future__ import annotations

from ..core.enums import AttackType, DetectorName
from ..core.types import DetectorResult
from ..features.extractor import FeatureFrame
from ..mavlink.codec import command_name_from_id
from .base import Detector, ramp


class ProtocolDetector(Detector):
    name = DetectorName.PROTOCOL

    def __init__(self, cfg: dict) -> None:
        p = cfg
        self.expected_sysids = set(p.get("expected_sysids", [1]))
        self.expected_gcs = set(p.get("expected_gcs_sysids", [255, 254]))
        self.autopilot_compid = int(p.get("autopilot_compid", 1))
        self.hb_timeout = float(p.get("heartbeat_timeout_s", 3.0))
        self.max_rate = float(p.get("max_msg_rate_hz", 400.0))
        self.nominal_rate = float(p.get("nominal_msg_rate_hz", 28.0))
        self.spike_factor = float(p.get("msg_rate_spike_factor", 3.0))
        self.max_seq_gap = float(p.get("max_seq_gap", 30))
        self.gps_dropout = float(p.get("gps_dropout_s", 2.0))
        self.sensitive = set(p.get("sensitive_commands", []))
        self.burst_max = int(p.get("command_burst_max", 4))
        self.require_signing = bool(p.get("require_signing", False))

    def process(self, frame: FeatureFrame) -> DetectorResult:
        evidence: list[str] = []
        votes: dict[AttackType, float] = {}
        signals: dict[str, float] = {}
        score = 0.0

        def bump(attack: AttackType, s: float) -> None:
            nonlocal score
            votes[attack] = max(votes.get(attack, 0.0), s)
            score = max(score, s)

        # ---- message-rate flood (DoS) ----
        rate = frame.msg_rate_hz
        spike = self.nominal_rate * self.spike_factor
        if rate >= self.max_rate:
            bump(AttackType.DOS, 1.0)
            evidence.append(f"message flood: {rate:.0f} msg/s ≥ hard limit {self.max_rate:.0f}")
        elif rate > spike:
            s = ramp(rate, spike, self.max_rate)
            bump(AttackType.DOS, max(0.6, s))
            evidence.append(
                f"message-rate spike: {rate:.0f} msg/s > {self.spike_factor:.0f}×nominal "
                f"({spike:.0f})"
            )
        signals["msg_rate_hz"] = rate

        # ---- sequence gaps (loss / scramble / flood) ----
        if frame.max_seq_gap > self.max_seq_gap:
            s = ramp(frame.max_seq_gap, self.max_seq_gap, self.max_seq_gap * 4)
            # attribute to DoS if the rate is also elevated, else a MAVLink anomaly
            attack = AttackType.DOS if rate > spike else AttackType.MAVLINK_ANOMALY
            bump(attack, max(0.55, s))
            evidence.append(f"sequence gap {frame.max_seq_gap} > {self.max_seq_gap:.0f}")
        signals["max_seq_gap"] = float(frame.max_seq_gap)

        # ---- rogue sources ----
        cmd_src = {(c.sysid, c.compid) for c in frame.commands_recent}
        rogue_telemetry = [
            (s, c)
            for (s, c) in frame.sources
            if s not in self.expected_sysids and s not in self.expected_gcs and (s, c) not in cmd_src
        ]
        if rogue_telemetry:
            bump(AttackType.MAVLINK_ANOMALY, 0.9)
            evidence.append(
                "rogue telemetry source(s): "
                + ", ".join(f"sys{s}/comp{c}" for s, c in rogue_telemetry)
            )
        signals["n_sources"] = float(frame.n_sources)

        # ---- liveness (heartbeat / GPS dropout -> DoS/blackout) ----
        if frame.heartbeat_age_s > self.hb_timeout:
            s = ramp(frame.heartbeat_age_s, self.hb_timeout, self.hb_timeout * 2)
            bump(AttackType.DOS, max(0.6, s))
            evidence.append(f"heartbeat stale {frame.heartbeat_age_s:.1f}s > {self.hb_timeout:.1f}s")
        if frame.gps_age_s > self.gps_dropout:
            s = ramp(frame.gps_age_s, self.gps_dropout, self.gps_dropout * 3)
            bump(AttackType.DOS, max(0.5, s))
            evidence.append(f"GPS dropout {frame.gps_age_s:.1f}s > {self.gps_dropout:.1f}s")

        # ---- command provenance (injection) ----
        unexpected = [
            c
            for c in frame.commands_recent
            if c.sysid not in self.expected_gcs
            and not (c.sysid in self.expected_sysids and c.compid == self.autopilot_compid)
        ]
        if unexpected:
            names = {command_name_from_id(c.command) for c in unexpected}
            sensitive_hit = names & self.sensitive
            s = 0.9 if sensitive_hit else 0.65
            if len(unexpected) > self.burst_max:
                s = max(s, 0.95)
            bump(AttackType.COMMAND_INJECTION, s)
            src = {(c.sysid, c.compid) for c in unexpected}
            ev = (
                f"{len(unexpected)} command(s) from unexpected source "
                + ", ".join(f"sys{a}/comp{b}" for a, b in src)
            )
            if sensitive_hit:
                ev += f"; sensitive: {', '.join(sorted(sensitive_hit))}"
            evidence.append(ev)
        signals["cmd_rate_hz"] = frame.cmd_rate_hz

        # ---- signing policy ----
        if self.require_signing and frame.signed_ratio < 1.0:
            bump(AttackType.MAVLINK_ANOMALY, 0.5)
            evidence.append(f"unsigned messages present (signed ratio {frame.signed_ratio:.2f})")

        return DetectorResult(
            detector=self.name,
            score=score,
            triggered=score >= 0.5,
            evidence=evidence,
            attack_votes=votes,
            signals=signals,
        )
