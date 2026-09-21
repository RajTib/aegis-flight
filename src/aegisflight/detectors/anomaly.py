"""Detector C — lightweight ML anomaly detector (Isolation Forest).

Trained on **benign-only** feature vectors (see ``scripts/train_model.py``),
so it flags any telemetry that departs from learned normal flight without ever
seeing an attack during training. The saved bundle carries the scaler, the
model, the exact feature order, benign score statistics for normalisation, and
the sklearn version — inference reconstructs the identical feature schema.

If no model is present the detector degrades gracefully to a no-op (score 0),
so the rest of the pipeline runs before the model is trained.
"""

from __future__ import annotations

import math
from pathlib import Path

import joblib

from ..core.enums import AttackType, DetectorName
from ..core.types import DetectorResult
from ..features.extractor import ML_FEATURES, FeatureFrame
from .base import Detector

# Which ML feature, when most anomalous, implies which attack class.
FEATURE_ATTACK_MAP: dict[str, AttackType] = {
    "msg_rate_hz": AttackType.DOS,
    "interarrival_jitter_ms": AttackType.DOS,
    "max_seq_gap": AttackType.DOS,
    "pos_residual_m": AttackType.GPS_SPOOFING,
    "gps_vfr_speed_diff_ms": AttackType.TELEMETRY_MANIPULATION,
    "gps_baro_alt_diff_m": AttackType.TELEMETRY_MANIPULATION,
    "alt_rate_ms": AttackType.TELEMETRY_MANIPULATION,
    "accel_ms2": AttackType.GPS_SPOOFING,
    "battery_v_rate_abs": AttackType.TELEMETRY_MANIPULATION,
    "yaw_course_diff_deg": AttackType.TELEMETRY_MANIPULATION,
    "cmd_rate_hz": AttackType.COMMAND_INJECTION,
    "loss_ratio": AttackType.DOS,
}


class AnomalyDetector(Detector):
    name = DetectorName.ANOMALY

    def __init__(self, cfg: dict, model_path: str | Path | None = None) -> None:
        self.threshold = float(cfg.get("score_threshold", 0.62))
        self.warmup_ticks = int(cfg.get("warmup_ticks", 20))
        path = Path(model_path or cfg.get("model_path", "models/isoforest.joblib"))
        self.model_path = path
        self.bundle: dict | None = None
        self._ticks = 0
        if path.exists():
            try:
                self.bundle = joblib.load(path)
            except Exception:  # noqa: BLE001 - corrupt/incompatible model => degrade
                self.bundle = None

    @property
    def available(self) -> bool:
        return self.bundle is not None

    def process(self, frame: FeatureFrame) -> DetectorResult:
        self._ticks += 1
        signals: dict[str, float] = {}
        if self.bundle is None or self._ticks < self.warmup_ticks:
            return DetectorResult(
                detector=self.name, score=0.0, triggered=False,
                evidence=[], attack_votes={}, signals=signals,
            )

        scaler = self.bundle["scaler"]
        model = self.bundle["model"]
        thr = self.bundle["score_thr"]
        scale = self.bundle["score_scale"]

        vec = [[float(getattr(frame, n)) for n in ML_FEATURES]]
        xs = scaler.transform(vec)
        anomaly = float(-model.score_samples(xs)[0])  # higher => more anomalous
        norm = 1.0 / (1.0 + math.exp(-(anomaly - thr) / max(1e-6, scale)))
        signals["anomaly_raw"] = anomaly
        signals["anomaly_score"] = norm

        # Attribute to the most-deviating standardised feature.
        z = xs[0]
        idx = max(range(len(z)), key=lambda i: abs(z[i]))
        top_feat = ML_FEATURES[idx]
        attack = FEATURE_ATTACK_MAP.get(top_feat, AttackType.GPS_SPOOFING)

        triggered = norm >= self.threshold
        evidence = []
        votes: dict[AttackType, float] = {}
        if triggered:
            evidence.append(
                f"ML anomaly score {norm:.2f} ≥ {self.threshold:.2f} "
                f"(driver: {top_feat}, z={z[idx]:+.1f})"
            )
            votes[attack] = norm
        return DetectorResult(
            detector=self.name,
            score=norm,
            triggered=triggered,
            evidence=evidence,
            attack_votes=votes,
            signals=signals,
        )
