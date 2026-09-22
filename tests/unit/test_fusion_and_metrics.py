"""Fusion engine combination logic and metrics computation."""

from aegisflight.config import load_config
from aegisflight.core.enums import AttackType, DetectorName, IntegrityStatus, Severity
from aegisflight.core.types import DetectorResult
from aegisflight.fusion import FusionEngine
from aegisflight.metrics import evaluate


def _fusion():
    return FusionEngine(load_config().detector["fusion"])


def _result(name, score, attack=None):
    votes = {attack: score} if attack else {}
    return DetectorResult(detector=name, score=score, triggered=score > 0.5,
                          evidence=[], attack_votes=votes)


def test_lone_firmware_triggers():
    # firmware weight is only 0.20 in a weighted sum, but noisy-OR + max-norm
    # must let a lone firmware failure raise a threat.
    fe = _fusion()
    res = [
        _result(DetectorName.PROTOCOL, 0.0),
        _result(DetectorName.PHYSICS, 0.0),
        _result(DetectorName.ANOMALY, 0.0),
        _result(DetectorName.INTEGRITY, 1.0, AttackType.FIRMWARE_INTEGRITY),
    ]
    a = fe.fuse(1.0, 0.0, res, IntegrityStatus.INVALID)
    assert a.threat
    assert a.attack_type is AttackType.FIRMWARE_INTEGRITY


def test_lone_weak_ml_does_not_trigger():
    fe = _fusion()
    res = [
        _result(DetectorName.PROTOCOL, 0.0),
        _result(DetectorName.PHYSICS, 0.0),
        _result(DetectorName.ANOMALY, 0.62, AttackType.GPS_SPOOFING),
        _result(DetectorName.INTEGRITY, 0.0),
    ]
    a = fe.fuse(1.0, 0.0, res, IntegrityStatus.VALID)
    assert not a.threat  # ML alone stays below threat threshold


def test_strong_physics_triggers_and_attributes():
    fe = _fusion()
    res = [
        _result(DetectorName.PROTOCOL, 0.0),
        _result(DetectorName.PHYSICS, 1.0, AttackType.GPS_SPOOFING),
        _result(DetectorName.ANOMALY, 0.0),
        _result(DetectorName.INTEGRITY, 0.0),
    ]
    a = fe.fuse(1.0, 0.0, res, IntegrityStatus.VALID)
    assert a.threat and a.attack_type is AttackType.GPS_SPOOFING
    assert a.severity.rank >= Severity.HIGH.rank


def test_all_benign_is_normal():
    fe = _fusion()
    res = [_result(d, 0.0) for d in DetectorName]
    a = fe.fuse(1.0, 0.0, res, IntegrityStatus.VALID)
    assert not a.threat
    assert a.severity is Severity.NORMAL
    assert a.attack_type is AttackType.BENIGN


# ---- metrics ----
def test_evaluate_perfect():
    yt = [AttackType.BENIGN, AttackType.GPS_SPOOFING, AttackType.GPS_SPOOFING]
    yp = [AttackType.BENIGN, AttackType.GPS_SPOOFING, AttackType.GPS_SPOOFING]
    ev = evaluate(yt, yp)
    assert ev.binary.recall == 1.0
    assert ev.binary.fpr == 0.0
    assert ev.per_class[AttackType.GPS_SPOOFING].recall == 1.0


def test_evaluate_false_positive_and_miss():
    yt = [AttackType.BENIGN, AttackType.DOS]
    yp = [AttackType.DOS, AttackType.BENIGN]  # 1 FP, 1 FN
    ev = evaluate(yt, yp)
    assert ev.binary.fp == 1
    assert ev.binary.fn == 1
    assert ev.binary.recall == 0.0
    assert ev.binary.fpr == 1.0
