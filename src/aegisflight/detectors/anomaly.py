"""Detector C — lightweight ML anomaly detector (benign-trained).

An **ensemble** of two benign-only anomaly signals over the ``ML_FEATURES``
vector, combined by taking the stronger of the two:

1. **Isolation Forest** — captures subtle *multivariate, in-distribution*
   anomalies (e.g. an unusual combination of otherwise-normal values).
2. **Robust Mahalanobis / scaled-norm** — the L2 norm of the standardised
   feature vector. Isolation Forest cannot extrapolate past its training range,
   so it is blind to features that spike far outside benign (msg-rate floods,
   sequence gaps). The scaled-norm grows without bound for such out-of-range
   values and covers that blind spot. Near-constant benign features get a
   variance floor so any nonzero value registers.

Both are trained on benign flights only (see ``scripts/train_models.py``); the
bundle carries the scaler, model, feature schema, per-component benign
statistics, the calibrated score threshold/scale, and the sklearn version.
Missing/incompatible model => the detector degrades to a no-op (score 0).
"""

from __future__ import annotations

import math
from pathlib import Path

import joblib
import numpy as np

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

# Variance floor (in scaled units) so near-constant benign features still
# contribute to the Mahalanobis norm when they take a nonzero attack value.
_VAR_FLOOR = 1.0


def combined_anomaly_raw(bundle: dict, X: np.ndarray) -> np.ndarray:
    """Combined benign-anomaly signal per row (shared by training & inference).

    Returns ``max(iso_z, maha_z)`` where each component is standardised by its
    benign train statistics, so the two are on a comparable scale.
    """
    scaler = bundle["scaler"]
    model = bundle["model"]
    Xs = scaler.transform(X)

    iso = -model.score_samples(Xs)  # higher => more anomalous
    iso_z = (iso - bundle["iso_mean"]) / max(1e-9, bundle["iso_std"])

    maha = np.linalg.norm(Xs, axis=1)  # scaled features are z-scores
    maha_z = (maha - bundle["maha_mean"]) / max(1e-9, bundle["maha_std"])

    return np.maximum(iso_z, maha_z)


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

        thr = self.bundle["score_thr"]
        scale = self.bundle["score_scale"]
        vec = np.array([[float(getattr(frame, n)) for n in ML_FEATURES]])
        raw = float(combined_anomaly_raw(self.bundle, vec)[0])
        norm = 1.0 / (1.0 + math.exp(-(raw - thr) / max(1e-6, scale)))
        signals["anomaly_raw"] = raw
        signals["anomaly_score"] = norm

        # Attribute to the most-deviating standardised feature.
        z = self.bundle["scaler"].transform(vec)[0]
        idx = int(np.argmax(np.abs(z)))
        top_feat = ML_FEATURES[idx]
        attack = FEATURE_ATTACK_MAP.get(top_feat, AttackType.GPS_SPOOFING)

        triggered = norm >= self.threshold
        evidence: list[str] = []
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
