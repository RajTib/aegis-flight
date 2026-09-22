#!/usr/bin/env python
"""Scripted, headless AegisFlight demonstration.

Runs the six attack scenarios (plus a benign baseline) through the full IDS
pipeline and prints a narrated, deterministic timeline of detections + evidence.
Useful for a demo without the dashboard, and as a reproducible smoke test.

    python scripts/run_demo.py            # all scenarios
    python scripts/run_demo.py --attack gps_spoofing

Reproduces the same detections the live dashboard shows (`aegis serve`).
"""

from __future__ import annotations

import argparse
import contextlib
import sys

from aegisflight.benchmark.runner import run_session
from aegisflight.config import load_config

SCENARIOS = [
    "benign", "gps_spoofing", "mavlink_anomaly", "command_injection",
    "telemetry_manipulation", "dos", "firmware_integrity",
]


def demo_one(cfg, name: str) -> None:
    print("\n" + "=" * 70)
    print(f"SCENARIO: {name.upper()}   (safe local simulation)")
    print("=" * 70)
    res = run_session(cfg, name, seed=3, model_path="models/isoforest.joblib")
    alerts = [a for a in res.assessments if a.is_alert]
    if name != "benign":
        w0, w1 = res.window
        print(f"  attack window: t={w0:.0f}-{w1 if w1 < 1e17 else 'end'}s   "
              f"time-to-detect: {res.time_to_detect_s}s")
    print(f"  decisions={res.n_decisions}  alerts={len(alerts)}  "
          f"mean compute latency={sum(res.compute_latency_ms)/len(res.compute_latency_ms):.2f} ms")
    if not alerts:
        print("  → no alerts (nominal flight)" if name == "benign"
              else "  → (no alert raised)")
        return
    first = alerts[0]
    print(f"  → FIRST ALERT @ t={first.t:.1f}s: {first.severity.value} "
          f"{first.attack_type.value} (score {first.threat_score:.2f}, "
          f"conf {first.confidence:.2f})")
    for e in first.evidence[:3]:
        print(f"        • {e}")


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="AegisFlight scripted demo")
    ap.add_argument("--attack", default=None, help="run only this scenario")
    args = ap.parse_args()

    cfg = load_config()
    print("AegisFlight — UAV Intrusion Detection System (Stage-1 PoC)")
    print("All flight data and attacks below are LOCAL SIMULATIONS.")
    for name in ([args.attack] if args.attack else SCENARIOS):
        demo_one(cfg, name)
    print("\nDone. Launch the live dashboard with:  aegis serve")


if __name__ == "__main__":
    main()
