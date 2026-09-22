"""Single-session runner shared by training and benchmarking.

Runs one telemetry session (benign or a named attack) through the full IDS
pipeline and returns labelled per-decision records plus timing/throughput. This
is the one place that couples an attack to the pipeline's firmware directory
(for the firmware scenario) and applies the scoring policy:

* ``warmup_s``  — startup decisions excluded from scoring (extractor/ML warmup).
* ``in_window`` — attack ground-truth window; ``true_label`` = the attack class.
* ``grace_s``   — post-window recovery tail excluded from FP scoring (the
  cyber-physical after-effect of, e.g., a GPS spoof persists briefly and
  legitimately after the injection stops).
"""

from __future__ import annotations

import tempfile
import time
from dataclasses import dataclass, field

import numpy as np

from ..attacks import build_attack
from ..config import AegisConfig
from ..core.enums import AttackType
from ..core.types import ThreatAssessment
from ..pipeline import IDSPipeline
from ..sources.stream import SimulatedTelemetrySource


@dataclass
class DecisionRecord:
    t: float
    true_label: AttackType
    pred_label: AttackType
    threat: bool
    latency_ms: float
    severity: str
    scored: bool  # False for warmup/grace ticks
    features: list[float] = field(default_factory=list)


@dataclass
class SessionResult:
    attack_name: str
    seed: int
    route: str
    records: list[DecisionRecord]
    assessments: list[ThreatAssessment]
    window: tuple[float, float]
    time_to_detect_s: float | None
    n_messages: int
    n_decisions: int
    wall_time_s: float
    compute_latency_ms: list[float]

    @property
    def throughput_msgs_per_s(self) -> float:
        return self.n_messages / self.wall_time_s if self.wall_time_s > 0 else 0.0


def run_session(
    cfg: AegisConfig,
    attack_name: str = "benign",
    seed: int = 42,
    route: str | None = None,
    model_path: str | None = None,
    warmup_s: float = 5.0,
    grace_s: float = 8.0,
    rng_seed: int | None = None,
) -> SessionResult:
    if route is not None:
        cfg = _with_route(cfg, route)
    route = cfg.simulation.get("route", "survey_box")

    fw_dir = tempfile.mkdtemp(prefix="aegis_fw_")
    pipe = IDSPipeline(cfg, model_path=model_path, firmware_dir=fw_dir)

    rng = np.random.default_rng(rng_seed if rng_seed is not None else seed + 99)
    atk_kwargs = {"firmware_dir": fw_dir} if attack_name == "firmware_integrity" else {}
    attack = build_attack(attack_name, cfg.attacks, rng, **atk_kwargs)
    win = attack.window() if attack_name not in ("benign", "none") else (1e18, 1e18)

    src = SimulatedTelemetrySource(cfg, attack, seed=seed)

    records: list[DecisionRecord] = []
    assessments: list[ThreatAssessment] = []
    latencies: list[float] = []
    n_messages = 0
    time_to_detect: float | None = None
    last_attack_t = -1e18  # last decision whose ground-truth label was an attack
    attack_onset: float | None = None

    t_wall0 = time.perf_counter()
    for tick in src.stream():
        n_messages += len(tick.messages)
        a = pipe.process_tick(tick)
        if a is None:
            continue
        assessments.append(a)
        latencies.append(a.latency_ms)

        # Ground truth comes from the attack label (handles firmware's
        # open-ended window, unlike the fixed (start,start+duration) tuple).
        true_label = tick.label
        in_window = true_label.is_attack
        if in_window:
            last_attack_t = a.t
            if attack_onset is None:
                attack_onset = a.t
        # Post-attack recovery grace: benign ticks shortly after the attack
        # stops, during which a leaky cyber-physical residual legitimately
        # decays. Excluded from FP scoring but never hidden (see recovery_*).
        in_grace = (not in_window) and (a.t - last_attack_t) < grace_s

        pred_label = a.attack_type if a.threat else AttackType.BENIGN
        scored = (a.t >= warmup_s) and not in_grace

        if in_window and a.threat and time_to_detect is None:
            time_to_detect = a.t - (attack_onset if attack_onset is not None else a.t)

        records.append(
            DecisionRecord(
                t=a.t,
                true_label=true_label,
                pred_label=pred_label,
                threat=a.threat,
                latency_ms=a.latency_ms,
                severity=a.severity.value,
                scored=scored,
                features=[],
            )
        )
    wall = time.perf_counter() - t_wall0

    return SessionResult(
        attack_name=attack_name,
        seed=seed,
        route=route,
        records=records,
        assessments=assessments,
        window=win,
        time_to_detect_s=time_to_detect,
        n_messages=n_messages,
        n_decisions=len(records),
        wall_time_s=wall,
        compute_latency_ms=latencies,
    )


def _with_route(cfg: AegisConfig, route: str) -> AegisConfig:
    import copy

    new = copy.deepcopy(cfg)
    new.simulation["route"] = route
    return new
