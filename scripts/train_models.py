#!/usr/bin/env python
"""Train the Isolation Forest anomaly detector on benign-only flight data.

Usage:
    python scripts/train_models.py [--sessions 24] [--out models/isoforest.joblib]

Pipeline:
    collect benign sessions (varied route/speed/alt/noise/seed)
      -> split BY SESSION (train/val/test; no flight in two splits)
      -> StandardScaler + IsolationForest on train
      -> calibrate benign score normalisation on val
      -> save bundle (scaler, model, feature schema, calibration, metadata)
      -> sanity-check inference on benign vs a couple of attacks

Benign-only training + session-level split means the model never sees an attack
and never sees autocorrelated rows from a test flight during training.
"""

from __future__ import annotations

import argparse
import platform
import time
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from aegisflight.attacks import build_attack
from aegisflight.benchmark.dataset import collect_benign_dataset
from aegisflight.config import load_config
from aegisflight.detectors.anomaly import combined_anomaly_raw
from aegisflight.features.extractor import ML_FEATURES, FeatureExtractor
from aegisflight.sources.stream import SimulatedTelemetrySource


def _attack_mean_score(cfg, name, bundle) -> float:
    """Mean normalised anomaly score over an attack window (sanity check)."""
    thr, scale = bundle["score_thr"], bundle["score_scale"]
    rng = np.random.default_rng(7)
    atk = build_attack(name, cfg.attacks, rng)
    src = SimulatedTelemetrySource(cfg, atk, seed=42)
    fe = FeatureExtractor(cmd_window_s=cfg.detector["protocol"].get("command_burst_window_s", 2.0))
    every = max(1, int(round(cfg.simulation["sample_rate_hz"] / cfg.detector["decision_rate_hz"])))
    scores = []
    for tick in src.stream():
        for m in tick.messages:
            fe.update(m)
        if tick.tick % every:
            continue
        frame = fe.extract(tick.t)
        fe.clear_window_counts()
        if not atk.active(tick.t):
            continue
        vec = np.array([[float(getattr(frame, n)) for n in ML_FEATURES]])
        raw = float(combined_anomaly_raw(bundle, vec)[0])
        scores.append(1.0 / (1.0 + np.exp(-(raw - thr) / max(1e-6, scale))))
    return float(np.mean(scores)) if scores else float("nan")


def main() -> None:
    ap = argparse.ArgumentParser(description="Train AegisFlight Isolation Forest")
    ap.add_argument("--sessions", type=int, default=24, help="benign sessions to generate")
    ap.add_argument("--out", type=Path, default=Path("models/isoforest.joblib"))
    ap.add_argument("--seed", type=int, default=100)
    args = ap.parse_args()

    cfg = load_config()
    acfg = cfg.detector["anomaly"]
    t0 = time.perf_counter()

    print(f"[1/5] Generating {args.sessions} benign sessions (varied conditions)…")
    ds = collect_benign_dataset(cfg, n_sessions=args.sessions, seed=args.seed)
    print(f"      collected {ds.X.shape[0]} feature vectors "
          f"({ds.X.shape[1]} features) from {len(ds.session_meta)} flights")

    print("[2/5] Splitting BY SESSION (train/val/test)…")
    split = ds.split_by_session(train_frac=0.6, val_frac=0.2, seed=args.seed)
    Xtr, Xva, Xte = split["train"], split["val"], split["test"]
    print(f"      train={len(Xtr)} val={len(Xva)} test={len(Xte)} "
          f"(flights {list(split['train_sessions'])}/{list(split['val_sessions'])}/"
          f"{list(split['test_sessions'])})")

    print("[3/5] Fitting StandardScaler + IsolationForest ensemble (benign-only)…")
    scaler = StandardScaler().fit(Xtr)
    model = IsolationForest(
        n_estimators=int(acfg.get("n_estimators", 200)),
        contamination=float(acfg.get("contamination", 0.02)),
        random_state=args.seed,
        n_jobs=-1,
    ).fit(scaler.transform(Xtr))

    # Per-component benign statistics (from train) so the two ensemble signals
    # are standardised onto a comparable scale.
    Xtr_s = scaler.transform(Xtr)
    iso_tr = -model.score_samples(Xtr_s)
    maha_tr = np.linalg.norm(Xtr_s, axis=1)
    bundle = {
        "model": model,
        "scaler": scaler,
        "feature_names": list(ML_FEATURES),
        "iso_mean": float(iso_tr.mean()), "iso_std": float(iso_tr.std() or 1e-3),
        "maha_mean": float(maha_tr.mean()), "maha_std": float(maha_tr.std() or 1e-3),
    }

    print("[4/5] Calibrating combined benign score normalisation on validation split…")
    va_raw = combined_anomaly_raw(bundle, Xva)
    score_thr = float(va_raw.mean() + 3.0 * va_raw.std())
    score_scale = float(max(va_raw.std(), 1e-3))
    bundle["score_thr"] = score_thr
    bundle["score_scale"] = score_scale
    te_raw = combined_anomaly_raw(bundle, Xte)
    te_norm = 1.0 / (1.0 + np.exp(-(te_raw - score_thr) / score_scale))
    benign_test_alarm = float((te_norm >= float(acfg.get("score_threshold", 0.62))).mean())
    print(f"      benign val combined-raw mean={va_raw.mean():.4f} std={va_raw.std():.4f}")
    print(f"      score_thr={score_thr:.4f} score_scale={score_scale:.4f}")
    print(f"      benign TEST alarm rate @{acfg.get('score_threshold', 0.62)} = "
          f"{benign_test_alarm:.3f}")

    bundle["metadata"] = {
            "created": datetime.now(UTC).isoformat(),
            "sklearn_version": sklearn.__version__,
            "numpy_version": np.__version__,
            "python_version": platform.python_version(),
            "n_sessions": args.sessions,
            "n_train_vectors": int(len(Xtr)),
            "seed": args.seed,
            "n_estimators": int(acfg.get("n_estimators", 200)),
            "contamination": float(acfg.get("contamination", 0.02)),
            "benign_test_alarm_rate": benign_test_alarm,
            "train_sessions": [int(s) for s in split["train_sessions"]],
            "val_sessions": [int(s) for s in split["val_sessions"]],
            "test_sessions": [int(s) for s in split["test_sessions"]],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, args.out)
    print(f"[5/5] Saved model -> {args.out}")

    print("\nSanity check — mean normalised anomaly score in attack windows:")
    for name in ("gps_spoofing", "telemetry_manipulation", "mavlink_anomaly",
                 "command_injection", "dos"):
        print(f"    {name:24} {_attack_mean_score(cfg, name, bundle):.3f}")
    print(f"\nDone in {time.perf_counter() - t0:.1f}s")


if __name__ == "__main__":
    main()
