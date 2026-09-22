"""Detection-quality metrics computed from real runs.

All figures are derived from labelled decision-tick predictions produced by the
benchmark harness — never hand-written. Binary metrics treat "any attack class"
as positive; multiclass metrics score attribution (did we name the right attack
class?). Latency is measured per attack session as time-to-first-detection.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..core.enums import AttackType

ALL_CLASSES: list[AttackType] = list(AttackType)


@dataclass
class BinaryStats:
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0

    @property
    def support_pos(self) -> int:
        return self.tp + self.fn

    @property
    def support_neg(self) -> int:
        return self.tn + self.fp

    @property
    def recall(self) -> float:  # TPR / detection rate
        return self.tp / self.support_pos if self.support_pos else float("nan")

    @property
    def precision(self) -> float:
        d = self.tp + self.fp
        return self.tp / d if d else float("nan")

    @property
    def fpr(self) -> float:
        return self.fp / self.support_neg if self.support_neg else float("nan")

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        if not p or not r or np.isnan(p) or np.isnan(r) or (p + r) == 0:
            return float("nan")
        return 2 * p * r / (p + r)

    @property
    def accuracy(self) -> float:
        tot = self.tp + self.tn + self.fp + self.fn
        return (self.tp + self.tn) / tot if tot else float("nan")


@dataclass
class ClassScore:
    attack: AttackType
    tp: int = 0
    fp: int = 0
    fn: int = 0
    support: int = 0

    @property
    def recall(self) -> float:
        return self.tp / self.support if self.support else float("nan")

    @property
    def precision(self) -> float:
        d = self.tp + self.fp
        return self.tp / d if d else float("nan")

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        if np.isnan(p) or np.isnan(r) or (p + r) == 0:
            return float("nan")
        return 2 * p * r / (p + r)


@dataclass
class Evaluation:
    binary: BinaryStats
    per_class: dict[AttackType, ClassScore]
    confusion: dict[AttackType, dict[AttackType, int]]
    n: int
    latencies_ms: list[float] = field(default_factory=list)  # time-to-detect per session

    def latency_summary(self) -> dict[str, float]:
        if not self.latencies_ms:
            return {"mean": float("nan"), "p50": float("nan"), "p95": float("nan")}
        arr = np.array(self.latencies_ms, dtype=float)
        return {
            "mean": float(arr.mean()),
            "p50": float(np.percentile(arr, 50)),
            "p95": float(np.percentile(arr, 95)),
            "max": float(arr.max()),
        }

    def to_dict(self) -> dict:
        b = self.binary
        return {
            "n_decisions": self.n,
            "binary": {
                "accuracy": _r(b.accuracy),
                "precision": _r(b.precision),
                "recall_tpr": _r(b.recall),
                "fpr": _r(b.fpr),
                "f1": _r(b.f1),
                "tp": b.tp, "fp": b.fp, "tn": b.tn, "fn": b.fn,
            },
            "per_attack": {
                a.value: {
                    "precision": _r(c.precision),
                    "recall": _r(c.recall),
                    "f1": _r(c.f1),
                    "support": c.support,
                }
                for a, c in self.per_class.items()
                if a.is_attack
            },
            "macro": self.macro(),
            "confusion_matrix": {
                a.value: {b2.value: self.confusion[a][b2] for b2 in ALL_CLASSES}
                for a in ALL_CLASSES
            },
            "detection_latency_s": self.latency_summary(),
        }

    def macro(self) -> dict[str, float]:
        attacks = [c for a, c in self.per_class.items() if a.is_attack and c.support > 0]
        if not attacks:
            return {"precision": float("nan"), "recall": float("nan"), "f1": float("nan")}
        return {
            "precision": _r(float(np.nanmean([c.precision for c in attacks]))),
            "recall": _r(float(np.nanmean([c.recall for c in attacks]))),
            "f1": _r(float(np.nanmean([c.f1 for c in attacks]))),
        }


def _r(x: float) -> float:
    return round(float(x), 4) if x == x else float("nan")  # x==x filters NaN


def evaluate(
    y_true: list[AttackType],
    y_pred: list[AttackType],
    latencies_ms: list[float] | None = None,
) -> Evaluation:
    """Compute binary + multiclass detection metrics from labelled predictions."""
    binary = BinaryStats()
    per_class = {a: ClassScore(a) for a in ALL_CLASSES}
    confusion = {a: dict.fromkeys(ALL_CLASSES, 0) for a in ALL_CLASSES}

    for yt, yp in zip(y_true, y_pred, strict=True):
        confusion[yt][yp] += 1
        # binary
        if yt.is_attack and yp.is_attack:
            binary.tp += 1
        elif yt.is_attack and not yp.is_attack:
            binary.fn += 1
        elif not yt.is_attack and yp.is_attack:
            binary.fp += 1
        else:
            binary.tn += 1

    # per-class (one-vs-rest attribution)
    for a in ALL_CLASSES:
        per_class[a].support = sum(confusion[a][b] for b in ALL_CLASSES)
        per_class[a].tp = confusion[a][a]
        per_class[a].fn = per_class[a].support - confusion[a][a]
        per_class[a].fp = sum(confusion[b][a] for b in ALL_CLASSES if b != a)

    return Evaluation(
        binary=binary,
        per_class=per_class,
        confusion=confusion,
        n=len(y_true),
        latencies_ms=list(latencies_ms or []),
    )
