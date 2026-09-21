"""Detector D — firmware integrity.

Independently re-hashes the firmware components against a signed SHA-256
manifest (via :class:`~aegisflight.integrity.verifier.FirmwareVerifier`) and
surfaces the verdict as a detector score. An INVALID result is a hard,
unambiguous firmware-integrity alert. The verification is genuine crypto; the
tampering attack and this detector interact only through the shared firmware
directory — as they would on a real airframe.

Re-verification is throttled (every ``recheck_every`` decisions) and cached,
so the hot path stays cheap.
"""

from __future__ import annotations

from ..core.enums import AttackType, DetectorName, IntegrityStatus
from ..core.types import DetectorResult
from ..integrity.verifier import FirmwareVerifier, IntegrityReport
from .base import Detector


class IntegrityDetector(Detector):
    name = DetectorName.INTEGRITY

    def __init__(self, verifier: FirmwareVerifier | None = None, recheck_every: int = 5) -> None:
        self.verifier = verifier
        self.recheck_every = max(1, recheck_every)
        self._n = 0
        self._cached: IntegrityReport | None = None

    def _report(self) -> IntegrityReport:
        if self.verifier is None:
            return IntegrityReport(status=IntegrityStatus.UNKNOWN, evidence=["no verifier configured"])
        if self._cached is None or self._n % self.recheck_every == 0:
            self._cached = self.verifier.verify()
        return self._cached

    def process(self, frame=None) -> DetectorResult:
        self._n += 1
        report = self._report()
        triggered = report.status is IntegrityStatus.INVALID
        score = 1.0 if triggered else 0.0
        return DetectorResult(
            detector=self.name,
            score=score,
            triggered=triggered,
            evidence=report.evidence if triggered else [],
            attack_votes={AttackType.FIRMWARE_INTEGRITY: score} if triggered else {},
            signals={"integrity_invalid": float(triggered)},
        )

    @property
    def status(self) -> IntegrityStatus:
        return self._report().status

    def reset(self) -> None:
        self._n = 0
        self._cached = None
