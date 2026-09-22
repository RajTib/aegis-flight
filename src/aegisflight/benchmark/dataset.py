"""Benign feature-dataset generation for ML training.

Produces feature vectors (the exact ``ML_FEATURES`` schema) from **benign-only**
flights, varying route, cruise speed, cruise altitude, sensor-noise scale and
random seed so the Isolation Forest learns a broad notion of "normal". Vectors
are tagged with a ``session_id`` so training/validation/test can be split by
*flight*, never by individual telemetry rows (prevents leakage: rows from one
flight are highly autocorrelated).

Feature vectors are collected straight from the :class:`FeatureExtractor` (not
the scoring pipeline) so the schema is exactly what the anomaly detector sees at
inference time.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

import numpy as np

from ..config import AegisConfig
from ..features.extractor import ML_FEATURES, FeatureExtractor
from ..sources.stream import SimulatedTelemetrySource

ROUTES = ("survey_box", "out_and_back", "perimeter")


@dataclass
class BenignDataset:
    X: np.ndarray  # (n_samples, n_features)
    session_ids: np.ndarray  # (n_samples,) integer session index
    feature_names: tuple[str, ...]
    session_meta: list[dict]

    def split_by_session(
        self, train_frac: float = 0.6, val_frac: float = 0.2, seed: int = 0
    ) -> dict[str, np.ndarray]:
        """Split indices by session id (no flight appears in two splits)."""
        sessions = np.unique(self.session_ids)
        rng = np.random.default_rng(seed)
        rng.shuffle(sessions)
        n = len(sessions)
        n_tr = max(1, int(n * train_frac))
        n_va = max(1, int(n * val_frac))
        tr, va, te = sessions[:n_tr], sessions[n_tr : n_tr + n_va], sessions[n_tr + n_va :]

        def mask(sel):
            return np.isin(self.session_ids, sel)

        return {
            "train": self.X[mask(tr)],
            "val": self.X[mask(va)],
            "test": self.X[mask(te)],
            "train_sessions": tr,
            "val_sessions": va,
            "test_sessions": te,
        }


def _vary_config(base: AegisConfig, route: str, speed: float, alt: float, noise_scale: float,
                 seed: int) -> AegisConfig:
    cfg = copy.deepcopy(base)
    cfg.simulation["route"] = route
    cfg.simulation["cruise_speed_ms"] = speed
    cfg.simulation["cruise_alt_m"] = alt
    cfg.simulation["seed"] = seed
    noise = cfg.simulation.get("noise", {})
    cfg.simulation["noise"] = {k: v * noise_scale for k, v in noise.items()}
    return cfg


def collect_benign_dataset(
    base: AegisConfig,
    n_sessions: int = 20,
    warmup_s: float = 5.0,
    seed: int = 100,
) -> BenignDataset:
    """Run ``n_sessions`` varied benign flights and collect ML feature vectors."""
    rng = np.random.default_rng(seed)
    base_rate = float(base.simulation.get("sample_rate_hz", 10.0))
    dec_rate = float(base.detector.get("decision_rate_hz", 5.0))
    every = max(1, int(round(base_rate / dec_rate)))

    X: list[list[float]] = []
    sids: list[int] = []
    meta: list[dict] = []

    for s in range(n_sessions):
        route = ROUTES[s % len(ROUTES)]
        speed = float(rng.uniform(9.0, 15.0))
        alt = float(rng.uniform(40.0, 80.0))
        noise_scale = float(rng.uniform(0.8, 1.4))
        sess_seed = int(seed + 1 + s)
        cfg = _vary_config(base, route, speed, alt, noise_scale, sess_seed)

        src = SimulatedTelemetrySource(cfg, attack=None, seed=sess_seed)
        fe = FeatureExtractor(
            cmd_window_s=base.detector["protocol"].get("command_burst_window_s", 2.0)
        )
        count = 0
        for tick in src.stream():
            for m in tick.messages:
                fe.update(m)
            if tick.tick % every != 0:
                continue
            frame = fe.extract(tick.t)
            fe.clear_window_counts()
            if tick.t < warmup_s:
                continue
            X.append([float(getattr(frame, n)) for n in ML_FEATURES])
            sids.append(s)
            count += 1
        meta.append(
            {"session": s, "route": route, "speed": round(speed, 2),
             "alt": round(alt, 2), "noise_scale": round(noise_scale, 3),
             "seed": sess_seed, "samples": count}
        )

    return BenignDataset(
        X=np.array(X, dtype=float),
        session_ids=np.array(sids, dtype=int),
        feature_names=tuple(ML_FEATURES),
        session_meta=meta,
    )
