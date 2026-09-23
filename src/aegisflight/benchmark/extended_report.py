"""Render ``summary.md`` for the extended benchmark from ``results.json``."""

from __future__ import annotations

import json
from pathlib import Path


def _p(x) -> str:
    return "—" if x is None else f"{100 * float(x):.2f} %"


def _n(x, nd=2) -> str:
    return "—" if x is None else f"{float(x):.{nd}f}"


def _bin_row(name: str, b: dict) -> str:
    return (f"| {name} | {b['n']} | {b['tp']} / {b['fp']} / {b['tn']} / {b['fn']} | "
            f"{_n(b['accuracy'], 4)} | {_n(b['precision'], 4)} | {_n(b['recall'], 4)} | "
            f"{_n(b['fpr'], 4)} | {_n(b['f1'], 4)} |")


def render(r: dict, baseline: dict | None = None) -> str:
    c = r["config"]
    L = ["# AegisFlight — Extended synthetic benchmark v2 (generated)", "",
         f"_{r['n_sessions']} sessions, model used: {c['model_used']}, wall {c['wall_time_s']} s. "
         "Every session has its own trajectory seed, route, speed, altitude and noise scale; every "
         "implemented attack mode is exercised with randomised onset/duration. Production "
         "thresholds and model — nothing tuned on these results._", "",
         "## Binary detection (decision level, benign + single-attack sessions)", "",
         "| Scoring policy | Decisions | TP / FP / TN / FN | Accuracy | Precision | Recall | FPR | F1 |",
         "|---|---|---|---|---|---|---|---|"]
    if baseline:
        L.append(_bin_row("**Baseline benchmark** (artifacts/benchmarks, 5 s grace)",
                          {"n": baseline["n_decisions"], **baseline["binary"],
                           "recall": baseline["binary"]["recall_tpr"]}))
    for key, label in (("binary_grace5", "v2, 5 s grace (baseline policy)"),
                       ("binary_grace0", "v2, **no grace**"),
                       ("binary_grace5_excl_firmware", "v2, 5 s grace, excl. firmware"),
                       ("binary_grace0_excl_firmware", "v2, no grace, excl. firmware"),
                       ("binary_grace5_excl_known_gap", "v2, 5 s grace, excl. known-gap mode")):
        L.append(_bin_row(label, r[key]))
    L += ["", "## Per attack mode (5 s grace)", "",
          "| Mode | Sessions detected | Decision recall | Median / max time-to-detect (s) | Median post-attack alarm tail (s) | Attribution accuracy |",
          "|---|---|---|---|---|---|"]
    for k, v in r["per_mode"].items():
        tag = " ⚠ known gap" if v["known_gap"] else ""
        L.append(f"| `{k}`{tag} | {v['sessions_detected']}/{v['sessions']} | {_p(v['decision_recall'])} | "
                 f"{_n(v['median_ttd_s'])} / {_n(v['max_ttd_s'])} | {_n(v['median_alarm_tail_s'])} | "
                 f"{_p(v['attribution_accuracy'])} |")
    L += ["", "## Benign sessions (false alarms)", "",
          "| Condition | Sessions | Decisions | FP decisions | FPR | Sessions with ≥1 FP | FP classes |",
          "|---|---|---|---|---|---|---|"]
    for k in ("benign", "link_fifo_benign", "link_reorder_benign"):
        b = r.get(k)
        if b:
            L.append(f"| `{k}` | {b['sessions']} | {b['decisions']} | {b['false_positive_decisions']} | "
                     f"{_p(b['fpr'])} | {b['sessions_with_any_fp']} | `{json.dumps(b['fp_classes'])}` |")
    L += ["", f"_Link stress conditions: `{json.dumps(c['link_stress'])}`_", "",
          "## Simultaneous attacks (multi-label ground truth)", "",
          "| Combination | Sessions | In-window decisions | Binary recall | Primary ∈ truth | All active classes reported (both active) |",
          "|---|---|---|---|---|---|"]
    for k, v in r["combos"].items():
        L.append(f"| `{k}` | {v['sessions']} | {v['decisions']} | {_p(v['binary_recall'])} | "
                 f"{_p(v['primary_in_truth_rate'])} | {_p(v['full_coverage_when_both_active'])} |")
    L += ["", "_Prediction set for a decision = fused primary class ∪ `secondary_indicators`. "
          "The fusion emits one primary label; secondary indicators are ≥25 % of the primary vote._",
          "", f"Compute: mean {_n(r['compute_ms_mean_of_sessions'])} ms/decision (mean of session "
          f"means), worst session p95 {_n(r['compute_ms_p95_max'])} ms.", ""]
    return "\n".join(L)


def write_summary(out_dir: str | Path, baseline_path: str | Path = "artifacts/benchmarks/results.json") -> Path:
    out_dir = Path(out_dir)
    r = json.loads((out_dir / "results.json").read_text(encoding="utf-8"))
    bp = Path(baseline_path)
    base = json.loads(bp.read_text(encoding="utf-8")) if bp.exists() else None
    p = out_dir / "summary.md"
    p.write_text(render(r, base), encoding="utf-8")
    return p
