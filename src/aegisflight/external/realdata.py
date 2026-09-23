"""Scoring helpers for external (real-flight) data.

Two experiment types, both analysis-only:

* :func:`score_ulog_flight` -- PX4 ULog navigation replay: the *same*
  :class:`FeatureExtractor` and :class:`PhysicsDetector` code as production,
  plus an explicitly-labelled "ML navigation probe" (network features held at
  their benign training mean because a ULog cannot provide them).
* :func:`score_tlog_flight` -- MAVLink ``.tlog`` replay through the *full*
  :class:`IDSPipeline` (protocol + physics + ML + fusion), unchanged.

Neither path trains or re-thresholds anything.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable

import numpy as np

from ..config import AegisConfig
from ..core.enums import AttackType
from ..detectors.anomaly import combined_anomaly_raw
from ..detectors.physics import PhysicsDetector
from ..features.extractor import ML_FEATURES, FeatureExtractor
from ..pipeline import IDSPipeline
from ..sources.stream import TelemetryTick

NAV_FEATURES = ("pos_residual_m", "gps_vfr_speed_diff_ms", "gps_baro_alt_diff_m",
                "alt_rate_ms", "accel_ms2", "yaw_course_diff_deg")
NETWORK_FEATURES = ("msg_rate_hz", "interarrival_jitter_ms", "max_seq_gap",
                    "cmd_rate_hz", "loss_ratio")

# Physics-detector thresholds each nav feature is compared against (config keys).
NAV_THRESHOLD_KEYS = {
    "pos_residual_m": "gps_pos_residual_m",
    "gps_vfr_speed_diff_ms": "gps_speed_consistency_ms",
    "gps_baro_alt_diff_m": "alt_consistency_m",
    "alt_rate_ms": "alt_jump_ms",
    "accel_ms2": "max_accel_ms2",
}
YAW_COURSE_THRESHOLD_DEG = 25.0  # hard-coded in PhysicsDetector


def ml_norm(bundle: dict, vec: np.ndarray) -> float:
    raw = float(combined_anomaly_raw(bundle, vec.reshape(1, -1))[0])
    return 1.0 / (1.0 + math.exp(-(raw - bundle["score_thr"]) / max(1e-6, bundle["score_scale"])))


def nav_probe_vector(bundle: dict, frame) -> np.ndarray:
    """ML vector with NETWORK features replaced by their benign training mean (z = 0)."""
    vec = np.array([float(getattr(frame, n)) for n in ML_FEATURES])
    mean = bundle["scaler"].mean_
    for i, n in enumerate(ML_FEATURES):
        if n in NETWORK_FEATURES:
            vec[i] = mean[i]
    return vec


def score_ulog_flight(ticks: Iterable, airborne: Callable[[float], bool], cfg: AegisConfig,
                      bundle: dict | None) -> list[dict]:
    """Run extractor + physics (+ ML nav probe) over ``(t, msgs)`` ticks."""
    fe = FeatureExtractor(cmd_window_s=cfg.detector["protocol"].get("command_burst_window_s", 2.0))
    phys = PhysicsDetector(cfg.detector["physics"])
    rows: list[dict] = []
    for t, msgs in ticks:
        for m in msgs:
            fe.update(m)
        frame = fe.extract(t)
        fe.clear_window_counts()
        r = phys.process(frame)
        row = {"t": t, "airborne": bool(airborne(t)),
               "physics_score": r.score, "physics_triggered": r.triggered,
               "physics_evidence": list(r.evidence)}
        for n in NAV_FEATURES:
            row[n] = float(getattr(frame, n))
        row["groundspeed_ms"] = math.hypot(frame.snapshot.vx or 0.0, frame.snapshot.vy or 0.0)
        row["gps_age_s"] = float(frame.gps_age_s)
        if bundle is not None:
            row["ml_nav_probe"] = ml_norm(bundle, nav_probe_vector(bundle, frame))
        rows.append(row)
    return rows


def score_tlog_flight(ticks: Iterable[TelemetryTick], cfg: AegisConfig,
                      model_path: str | None) -> list[dict]:
    """Full, unchanged IDSPipeline over replayed MAVLink ticks."""
    pipe = IDSPipeline(cfg, model_path=model_path, firmware_dir=None)
    rows: list[dict] = []
    for tick in ticks:
        a = pipe.process_tick(tick)
        if a is None:
            continue
        f = pipe.last_frame
        row = {"t": a.t, "true": tick.label.value, "threat": a.threat,
               "pred": a.attack_type.value if a.threat else AttackType.BENIGN.value,
               "threat_score": a.threat_score, "evidence": list(a.evidence),
               **{f"det_{k}": v for k, v in a.detector_scores.items()}}
        for n in ML_FEATURES:
            row[n] = float(getattr(f, n))
        row["rel_alt"] = f.snapshot.rel_alt
        row["n_sources"] = f.n_sources
        row["sources"] = sorted(f"{s}/{c}" for s, c in f.sources)
        rows.append(row)
    return rows


def summarise(rows: list[dict], cols: Iterable[str]) -> dict[str, dict[str, float]]:
    out = {}
    for c in cols:
        v = np.array([r[c] for r in rows], dtype=float)
        v = v[np.isfinite(v)]
        if not len(v):
            out[c] = {"n": 0}
            continue
        out[c] = {"n": int(len(v)), "p50": float(np.percentile(v, 50)),
                  "p95": float(np.percentile(v, 95)), "p99": float(np.percentile(v, 99)),
                  "max": float(v.max()), "mean": float(v.mean())}
    return out


def sim_reference_ticks(cfg: AegisConfig, seed: int, route: str, speed: float, alt: float,
                        noise_scale: float, decision_every: int = 2):
    """Simulated benign flight as ``(t, msgs, airborne)`` at decision cadence.

    Mirrors ``benchmark.dataset._vary_config`` so the reference distribution is
    produced the same way as the ML training data, but with *different* seeds.
    """
    from ..benchmark.dataset import _vary_config
    from ..sources.stream import SimulatedTelemetrySource

    vcfg = _vary_config(cfg, route, speed, alt, noise_scale, seed)
    src = SimulatedTelemetrySource(vcfg, attack=None, seed=seed)
    buf = []
    for tick in src.stream():
        buf.extend(tick.messages)
        if tick.tick % decision_every:
            continue
        st = tick.truth_state
        yield tick.t, buf, bool(st.armed and st.rel_alt > 0.5)
        buf = []


def flight_metrics(rows: list[dict], physics_cfg: dict) -> dict:
    """Per-flight airborne alarm/exceedance rates for the ULog/sim nav replay.

    Only *usable* ticks count: airborne and a position message received within
    the last second (``gps_age_s < 1``) -- ticks with no valid position source
    would otherwise dilute the rates with all-zero features.
    """
    all_air = [r for r in rows if r["airborne"]]
    air = [r for r in all_air if r.get("gps_age_s", 0.0) < 1.0]
    n = len(air)
    if n == 0:
        return {"n_airborne_ticks": 0, "n_airborne_ticks_stale": len(all_air)}
    m: dict = {"n_airborne_ticks": n, "n_airborne_ticks_stale": len(all_air) - n,
               "airborne_s": n * 0.2}
    m["physics_trigger_rate"] = sum(r["physics_triggered"] for r in air) / n
    for feat, key in NAV_THRESHOLD_KEYS.items():
        thr = float(physics_cfg[key])
        vals = [abs(r[feat]) for r in air]
        m[f"exceed_{feat}"] = sum(v > thr for v in vals) / n
    yc = [r for r in air if r["groundspeed_ms"] > 2.0]
    m["exceed_yaw_course_diff_deg"] = (
        sum(r["yaw_course_diff_deg"] > YAW_COURSE_THRESHOLD_DEG for r in yc) / len(yc) if yc else 0.0)
    if "ml_nav_probe" in air[0]:
        m["ml_probe_alarm_rate"] = sum(r["ml_nav_probe"] >= 0.62 for r in air) / n
        m["ml_probe_lone_threat_rate"] = sum(r["ml_nav_probe"] >= 0.9563 for r in air) / n
    # which physics rules fired (evidence prefixes)
    rules: dict[str, int] = {}
    for r in air:
        if r["physics_triggered"]:
            for e in r["physics_evidence"]:
                key = e.split(" ")[0] + " " + e.split(" ")[1] if " " in e else e
                rules[key] = rules.get(key, 0) + 1
    m["physics_rules_fired"] = rules
    return m
