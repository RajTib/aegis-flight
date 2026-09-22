#!/usr/bin/env python
"""Run the AegisFlight detection benchmark and write artifacts + figures.

Usage:
    python scripts/benchmark.py [--seeds 1 2 3 4 5 6] [--out artifacts/benchmarks]
                                [--no-model] [--no-figures] [--grace 5]

Outputs (in --out):
    results.json          full metrics (authoritative)
    results.csv           per-session rows
    summary.md            human-readable summary table
    *.png                 confusion matrix, per-attack recall, FPR, latency,
                          resource usage, threat timeline

Every number is computed from real runs; nothing is hand-written.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from aegisflight.benchmark.harness import run_benchmark
from aegisflight.config import load_config


def main() -> None:
    ap = argparse.ArgumentParser(description="AegisFlight benchmark")
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5, 6])
    ap.add_argument("--out", type=Path, default=Path("artifacts/benchmarks"))
    ap.add_argument("--model", type=str, default="models/isoforest.joblib")
    ap.add_argument("--no-model", action="store_true", help="run rule+physics only")
    ap.add_argument("--no-figures", action="store_true")
    ap.add_argument("--grace", type=float, default=5.0)
    args = ap.parse_args()

    cfg = load_config()
    model_path = None if args.no_model else args.model
    print(f"Running benchmark: seeds={args.seeds} model={'off' if args.no_model else model_path}")
    result = run_benchmark(cfg, seeds=args.seeds, model_path=model_path,
                           out_dir=args.out, grace_s=args.grace)

    b = result["binary"]
    print("\n=== Binary detection ===")
    print(f"  accuracy={b['accuracy']}  precision={b['precision']}  "
          f"recall={b['recall_tpr']}  FPR={b['fpr']}  F1={b['f1']}")
    print("=== Per-attack recall ===")
    for atk, m in result["per_attack"].items():
        print(f"  {atk:24} recall={m['recall']}  precision={m['precision']}  support={m['support']}")
    print("=== Latency / throughput ===")
    print(f"  detection latency mean={result['detection_latency_s']['mean']:.2f}s  "
          f"compute p95={result['compute_latency_ms']['p95']:.3f}ms  "
          f"throughput={result['throughput']['messages_per_s']:.0f} msg/s")

    if not args.no_figures:
        from aegisflight.benchmark import plots
        print("\nGenerating figures…")
        for p in plots.generate_all(cfg, result, Path("artifacts/figures")):
            print(f"  {p}")

    print(f"\nArtifacts written to {args.out}/ (results.json, results.csv, summary.md)")


if __name__ == "__main__":
    main()
