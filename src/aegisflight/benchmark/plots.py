"""Benchmark figure generation (matplotlib, headless).

All figures are rendered from a benchmark ``result`` dict (as written to
``results.json``) plus, for the timeline, one freshly-run attack session. Kept
separate from the harness so the core library never imports matplotlib on the
hot path.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

# Brand-neutral, colour-blind-safe palette.
_ACCENT = "#2b8cbe"
_WARN = "#e6550d"
_OK = "#31a354"
_GRID = "#d9d9d9"
_ATTACKS = [
    "GPS_SPOOFING", "MAVLINK_ANOMALY", "COMMAND_INJECTION",
    "TELEMETRY_MANIPULATION", "DOS", "FIRMWARE_INTEGRITY",
]


def _style(ax) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color=_GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def confusion_matrix(result: dict, out: Path) -> Path:
    cm = result["confusion_matrix"]
    labels = list(cm.keys())
    mat = np.array([[cm[a][b] for b in labels] for a in labels], dtype=float)
    short = [lb.replace("_", "\n") for lb in labels]
    fig, ax = plt.subplots(figsize=(8, 6.5))
    norm = mat / np.clip(mat.sum(axis=1, keepdims=True), 1, None)
    im = ax.imshow(norm, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(len(labels)), short, fontsize=7, rotation=45, ha="right")
    ax.set_yticks(range(len(labels)), short, fontsize=7)
    ax.set_xlabel("Predicted"); ax.set_ylabel("True (ground truth)")
    ax.set_title("Confusion matrix (row-normalised)")
    for i in range(len(labels)):
        for j in range(len(labels)):
            if mat[i, j] > 0:
                ax.text(j, i, int(mat[i, j]), ha="center", va="center",
                        color="white" if norm[i, j] > 0.5 else "#333", fontsize=7)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    p = out / "confusion_matrix.png"
    fig.savefig(p, dpi=140); plt.close(fig)
    return p


def per_attack_recall(result: dict, out: Path) -> Path:
    pa = result["per_attack"]
    labels = [a for a in _ATTACKS if a in pa]
    recall = [pa[a]["recall"] for a in labels]
    prec = [pa[a]["precision"] for a in labels]
    x = np.arange(len(labels)); w = 0.38
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.bar(x - w / 2, recall, w, label="Recall", color=_ACCENT)
    ax.bar(x + w / 2, prec, w, label="Precision", color=_OK)
    ax.set_xticks(x, [lb.replace("_", "\n") for lb in labels], fontsize=8)
    ax.set_ylim(0, 1.05); ax.set_ylabel("Score")
    ax.set_title("Per-attack recall & precision")
    ax.legend(frameon=False)
    _style(ax)
    for i, v in enumerate(recall):
        ax.text(i - w / 2, v + 0.02, f"{v:.2f}", ha="center", fontsize=7)
    fig.tight_layout()
    p = out / "per_attack_recall.png"
    fig.savefig(p, dpi=140); plt.close(fig)
    return p


def fpr_chart(result: dict, out: Path) -> Path:
    ps = result.get("per_scenario", {})
    labels = [s for s in ps if s != "benign"] + (["benign"] if "benign" in ps else [])
    fpr = [ps[s]["fpr"] for s in labels]
    fig, ax = plt.subplots(figsize=(9, 4.2))
    colors = [_WARN if s == "benign" else _ACCENT for s in labels]
    ax.bar([lb.replace("_", "\n") for lb in labels], fpr, color=colors)
    ax.set_ylabel("False-positive rate")
    ax.set_title("False-positive rate by scenario (non-attack decisions)")
    _style(ax)
    ymax = max(fpr) if fpr else 0.0
    ax.set_ylim(0, max(0.05, ymax * 1.3))
    for i, v in enumerate(fpr):
        ax.text(i, v + ymax * 0.03 + 0.001, f"{v:.3f}", ha="center", fontsize=7)
    fig.tight_layout()
    p = out / "fpr.png"
    fig.savefig(p, dpi=140); plt.close(fig)
    return p


def latency_chart(result: dict, out: Path) -> Path:
    lat = result.get("per_attack_detection_latency_s", {})
    labels = [a for a in _ATTACKS if a.lower() in lat]
    means = [lat[a.lower()]["mean"] for a in labels]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))
    ax1.bar([lb.replace("_", "\n") for lb in labels], means, color=_ACCENT)
    ax1.set_title("Detection latency by attack (s)")
    ax1.set_ylabel("seconds"); _style(ax1)
    for i, v in enumerate(means):
        ax1.text(i, v + 0.03, f"{v:.2f}", ha="center", fontsize=7)
    comp = result["compute_latency_ms"]
    keys = ["mean", "p50", "p95", "max"]
    ax2.bar(keys, [comp[k] for k in keys], color=_OK)
    ax2.set_title("Per-decision compute latency (ms)")
    ax2.set_ylabel("milliseconds"); _style(ax2)
    for i, k in enumerate(keys):
        ax2.text(i, comp[k], f"{comp[k]:.2f}", ha="center", va="bottom", fontsize=7)
    fig.tight_layout()
    p = out / "latency.png"
    fig.savefig(p, dpi=140); plt.close(fig)
    return p


def resource_usage(result: dict, out: Path) -> Path:
    res = result["resources"]; th = result["throughput"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    ax1.bar(["CPU mean", "CPU max"], [res["cpu_percent_mean"], res["cpu_percent_max"]],
            color=_ACCENT)
    ax1.set_title(f"CPU usage (% of one core; {res['n_cores']} cores)")
    ax1.set_ylabel("%"); _style(ax1)
    ax2.bar(["RSS mean", "RSS max"], [res["rss_mb_mean"], res["rss_mb_max"]], color=_OK)
    ax2.set_title("Process memory (RSS)"); ax2.set_ylabel("MB"); _style(ax2)
    fig.suptitle(f"Throughput: {th['messages_per_s']:.0f} MAVLink msgs/s", fontsize=10)
    fig.tight_layout()
    p = out / "resource_usage.png"
    fig.savefig(p, dpi=140); plt.close(fig)
    return p


def threat_timeline(cfg, out: Path, attack: str = "gps_spoofing", seed: int = 3) -> Path:
    """Render threat score over one attack session with the window shaded."""
    from ..attacks import build_attack
    from .runner import run_session

    res = run_session(cfg, attack, seed=seed, model_path="models/isoforest.joblib")
    rng = __import__("numpy").random.default_rng(0)
    win = build_attack(attack, cfg.attacks, rng).window()
    t = [a.t for a in res.assessments]
    score = [a.threat_score for a in res.assessments]
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(t, score, color=_ACCENT, linewidth=1.5, label="threat score")
    ax.axvspan(win[0], win[1], color=_WARN, alpha=0.15, label="attack window")
    ax.axhline(0.45, color="#888", linestyle="--", linewidth=1, label="threat threshold")
    ax.set_xlabel("time (s)"); ax.set_ylabel("threat score"); ax.set_ylim(0, 1.05)
    ax.set_title(f"Threat timeline — {attack} (seed {seed})")
    ax.legend(frameon=False, fontsize=8, loc="upper right")
    _style(ax)
    fig.tight_layout()
    p = out / "threat_timeline.png"
    fig.savefig(p, dpi=140); plt.close(fig)
    return p


def generate_all(cfg, result: dict, out_dir: str | Path) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = [
        confusion_matrix(result, out),
        per_attack_recall(result, out),
        fpr_chart(result, out),
        latency_chart(result, out),
        resource_usage(result, out),
        threat_timeline(cfg, out),
    ]
    return paths
