"""Lightweight process resource sampling for benchmarks (CPU / memory)."""

from __future__ import annotations

from dataclasses import dataclass, field

import psutil


@dataclass
class ResourceSampler:
    """Samples the current process's CPU% and RSS memory over a run."""

    proc: psutil.Process = field(default_factory=psutil.Process)
    cpu: list[float] = field(default_factory=list)
    rss_mb: list[float] = field(default_factory=list)

    def start(self) -> None:
        self.proc.cpu_percent(None)  # prime the CPU% baseline

    def sample(self) -> None:
        self.cpu.append(self.proc.cpu_percent(None))
        self.rss_mb.append(self.proc.memory_info().rss / (1024 * 1024))

    def summary(self) -> dict[str, float]:
        def _mean(x: list[float]) -> float:
            return round(sum(x) / len(x), 2) if x else 0.0

        def _max(x: list[float]) -> float:
            return round(max(x), 2) if x else 0.0

        return {
            "cpu_percent_mean": _mean(self.cpu),
            "cpu_percent_max": _max(self.cpu),
            "rss_mb_mean": _mean(self.rss_mb),
            "rss_mb_max": _max(self.rss_mb),
            "n_cores": psutil.cpu_count(logical=True) or 1,
        }
