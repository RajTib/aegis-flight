"""Benchmark harness — authoritative detection metrics from real runs.

Runs a deterministic grid of sessions (benign + each of the six attacks across
several seeds/routes), aggregates every scored decision into one confusion
matrix, and computes binary + per-attack + latency + throughput + resource
metrics. Writes ``results.json``, ``results.csv`` and ``summary.md`` to the
output directory. **No metric here is hand-written** — all derive from the runs.

Reproducibility: benchmark seeds are disjoint from the ML training seeds
(training uses 100+; benchmark uses 1..N), so the model is evaluated on flights
it never saw.
"""

from __future__ import annotations

import csv
import json
import platform
import time
from pathlib import Path

import numpy as np

from ..config import AegisConfig
from ..core.enums import AttackType
from ..core.geo import haversine_m
from ..metrics.resources import ResourceSampler
from ..metrics.scoring import evaluate
from .runner import run_session

SCENARIOS = [
    "benign",
    "gps_spoofing",
    "mavlink_anomaly",
    "command_injection",
    "telemetry_manipulation",
    "dos",
    "firmware_integrity",
]
ROUTES = ["survey_box", "out_and_back", "perimeter"]


def _distance_m(assessments) -> float:
    pts = [(a.telemetry.get("lat"), a.telemetry.get("lon")) for a in assessments]
    pts = [(la, lo) for la, lo in pts if la is not None and lo is not None]
    return sum(
        haversine_m(a[0], a[1], b[0], b[1]) for a, b in zip(pts, pts[1:], strict=False)
    )


def run_benchmark(
    cfg: AegisConfig,
    seeds: list[int] | None = None,
    model_path: str | None = "models/isoforest.joblib",
    out_dir: str | Path = "artifacts/benchmarks",
    grace_s: float = 5.0,
) -> dict:
    seeds = seeds or [1, 2, 3, 4, 5, 6]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if model_path and not Path(model_path).exists():
        model_path = None  # run rule+physics-only if the model isn't trained

    all_true: list[AttackType] = []
    all_pred: list[AttackType] = []
    detect_latencies: list[float] = []
    compute_latencies: list[float] = []
    per_attack_latency: dict[str, list[float]] = {}
    session_rows: list[dict] = []
    distances: list[float] = []
    per_scenario_pairs: dict[str, tuple[list, list]] = {}
    n_messages_total = 0
    n_decisions_total = 0

    sampler = ResourceSampler()
    sampler.start()
    t0 = time.perf_counter()

    for scenario in SCENARIOS:
        for i, seed in enumerate(seeds):
            route = ROUTES[i % len(ROUTES)]
            res = run_session(cfg, scenario, seed=seed, route=route,
                              model_path=model_path, grace_s=grace_s)
            sampler.sample()

            scored = [r for r in res.records if r.scored]
            all_true.extend(r.true_label for r in scored)
            all_pred.extend(r.pred_label for r in scored)
            ps = per_scenario_pairs.setdefault(scenario, ([], []))
            ps[0].extend(r.true_label for r in scored)
            ps[1].extend(r.pred_label for r in scored)
            compute_latencies.extend(res.compute_latency_ms)
            n_messages_total += res.n_messages
            n_decisions_total += res.n_decisions
            dist = _distance_m(res.assessments)
            distances.append(dist)

            ttd = res.time_to_detect_s
            if scenario not in ("benign", "none") and ttd is not None:
                detect_latencies.append(ttd)
                per_attack_latency.setdefault(scenario, []).append(ttd)

            # per-session binary stats (for CSV / transparency)
            ev = evaluate([r.true_label for r in scored], [r.pred_label for r in scored])
            session_rows.append({
                "scenario": scenario, "seed": seed, "route": route,
                "recall": ev.binary.recall, "fpr": ev.binary.fpr,
                "precision": ev.binary.precision, "n_scored": len(scored),
                "time_to_detect_s": ttd if ttd is not None else "",
                "distance_m": round(dist, 1),
                "throughput_msgs_per_s": round(res.throughput_msgs_per_s, 1),
                "mean_compute_latency_ms": round(float(np.mean(res.compute_latency_ms)), 4),
            })

    wall = time.perf_counter() - t0
    ev = evaluate(all_true, all_pred, latencies_ms=detect_latencies)
    result = ev.to_dict()

    comp = np.array(compute_latencies, dtype=float)
    result["compute_latency_ms"] = {
        "mean": round(float(comp.mean()), 4),
        "p50": round(float(np.percentile(comp, 50)), 4),
        "p95": round(float(np.percentile(comp, 95)), 4),
        "max": round(float(comp.max()), 4),
    }
    result["per_attack_detection_latency_s"] = {
        k: {"mean": round(float(np.mean(v)), 3), "max": round(float(np.max(v)), 3)}
        for k, v in per_attack_latency.items()
    }
    result["throughput"] = {
        "messages_processed": n_messages_total,
        "decisions": n_decisions_total,
        "wall_time_s": round(wall, 2),
        "messages_per_s": round(n_messages_total / wall, 1) if wall else 0.0,
    }
    result["distance_m"] = {
        "mean_per_session": round(float(np.mean(distances)), 1),
        "total": round(float(np.sum(distances)), 1),
    }
    result["resources"] = sampler.summary()
    per_scenario = {}
    for scen, (yt, yp) in per_scenario_pairs.items():
        se = evaluate(yt, yp)
        per_scenario[scen] = {
            "recall": se.binary.recall if scen != "benign" else float("nan"),
            "fpr": se.binary.fpr,
            "precision": se.binary.precision,
            "n_scored": len(yt),
        }
    result["per_scenario"] = per_scenario
    result["config"] = {
        "seeds": seeds,
        "routes": ROUTES,
        "grace_s": grace_s,
        "model_used": bool(model_path),
        "decision_rate_hz": cfg.detector.get("decision_rate_hz"),
        "python": platform.python_version(),
    }

    # -- write artifacts --
    (out / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    _write_csv(out / "results.csv", session_rows)
    (out / "summary.md").write_text(_summary_md(result), encoding="utf-8")
    return result


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def _fmt(x) -> str:
    return f"{x:.3f}" if isinstance(x, float) and x == x else str(x)


def _summary_md(r: dict) -> str:
    b = r["binary"]
    lines = [
        "# AegisFlight — Benchmark Summary",
        "",
        f"_Generated from {r['n_decisions']} scored decisions across "
        f"{len(r['config']['seeds'])} seeds × {len(SCENARIOS)} scenarios. "
        f"Model used: {r['config']['model_used']}._",
        "",
        "## Binary detection (attack vs benign)",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Accuracy | {_fmt(b['accuracy'])} |",
        f"| Precision | {_fmt(b['precision'])} |",
        f"| Recall (TPR) | {_fmt(b['recall_tpr'])} |",
        f"| False-positive rate | {_fmt(b['fpr'])} |",
        f"| F1 | {_fmt(b['f1'])} |",
        f"| TP / FP / TN / FN | {b['tp']} / {b['fp']} / {b['tn']} / {b['fn']} |",
        "",
        "## Per-attack detection",
        "",
        "| Attack | Precision | Recall | F1 | Support | Detection latency (s) |",
        "|---|---|---|---|---|---|",
    ]
    lat = r.get("per_attack_detection_latency_s", {})
    for atk, m in r["per_attack"].items():
        key = atk.lower()
        latm = lat.get(key, {})
        lat_str = f"{latm.get('mean', float('nan')):.2f}" if latm else "—"
        lines.append(
            f"| {atk} | {_fmt(m['precision'])} | {_fmt(m['recall'])} | "
            f"{_fmt(m['f1'])} | {m['support']} | {lat_str} |"
        )
    cl = r["detection_latency_s"]
    comp = r["compute_latency_ms"]
    res = r["resources"]
    th = r["throughput"]
    lines += [
        "",
        "## Latency, throughput & resources",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Detection latency mean / p95 (s) | {_fmt(cl['mean'])} / {_fmt(cl['p95'])} |",
        f"| Compute latency mean / p95 (ms) | {_fmt(comp['mean'])} / {_fmt(comp['p95'])} |",
        f"| Throughput (messages/s) | {th['messages_per_s']} |",
        f"| Mean distance / flight (m) | {r['distance_m']['mean_per_session']} |",
        f"| CPU mean / max (%) | {res['cpu_percent_mean']} / {res['cpu_percent_max']} |",
        f"| RSS mean / max (MB) | {res['rss_mb_mean']} / {res['rss_mb_max']} |",
        "",
        "_All figures produced by `python scripts/benchmark.py`; see `results.json`._",
    ]
    return "\n".join(lines)
