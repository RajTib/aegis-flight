#!/usr/bin/env python
"""Run the extended synthetic benchmark (v2). The baseline benchmark
(``scripts/benchmark.py`` -> ``artifacts/benchmarks/``) is NOT modified.

Usage:
    python scripts/benchmark_extended.py [--workers 8] [--seeds-per-mode 4]
                                         [--out artifacts/benchmarks_extended]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from aegisflight.benchmark.extended import run_extended
from aegisflight.benchmark.extended_report import write_summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("artifacts/benchmarks_extended"))
    ap.add_argument("--model", default="models/isoforest.joblib")
    ap.add_argument("--no-model", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seeds-per-mode", type=int, default=4)
    ap.add_argument("--benign", type=int, default=12)
    ap.add_argument("--combo-seeds", type=int, default=3)
    ap.add_argument("--link", type=int, default=6)
    a = ap.parse_args()
    run_extended(a.out, None if a.no_model else a.model, a.workers,
                 seeds_per_mode=a.seeds_per_mode, n_benign=a.benign,
                 combo_seeds=a.combo_seeds, n_link=a.link)
    print("wrote", write_summary(a.out))


if __name__ == "__main__":
    main()
