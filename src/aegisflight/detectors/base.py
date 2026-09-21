"""Detector interface + shared scoring helpers."""

from __future__ import annotations

from ..core.enums import DetectorName
from ..core.types import DetectorResult
from ..features.extractor import FeatureFrame


def ramp(x: float, lo: float, hi: float) -> float:
    """Piecewise-linear 0->1 ramp: 0 below ``lo``, 1 above ``hi``."""
    if hi <= lo:
        return 1.0 if x >= hi else 0.0
    return max(0.0, min(1.0, (x - lo) / (hi - lo)))


class Detector:
    """Base class. Subclasses implement :meth:`process`."""

    name: DetectorName

    def process(self, frame: FeatureFrame) -> DetectorResult:  # pragma: no cover - abstract
        raise NotImplementedError

    def reset(self) -> None:
        """Reset any per-session internal state."""
        return None
