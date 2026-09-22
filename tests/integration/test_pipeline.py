"""Integration: each attack is detected and correctly attributed end-to-end.

Runs without the ML model (rule + physics + integrity only) so the suite is
self-contained and fast; the ML layer only *improves* these numbers.
"""

import pytest

from aegisflight.benchmark.runner import run_session
from aegisflight.config import load_config
from aegisflight.core.enums import AttackType
from aegisflight.metrics import evaluate

CFG = load_config()

EXPECTED = {
    "gps_spoofing": AttackType.GPS_SPOOFING,
    "mavlink_anomaly": AttackType.MAVLINK_ANOMALY,
    "command_injection": AttackType.COMMAND_INJECTION,
    "telemetry_manipulation": AttackType.TELEMETRY_MANIPULATION,
    "dos": AttackType.DOS,
    "firmware_integrity": AttackType.FIRMWARE_INTEGRITY,
}


def _recall_and_top(name):
    res = run_session(CFG, name, seed=7, model_path=None, grace_s=5.0)
    scored = [r for r in res.records if r.scored]
    ev = evaluate([r.true_label for r in scored], [r.pred_label for r in scored])
    from collections import Counter
    top = Counter(r.pred_label for r in scored if r.true_label.is_attack and r.threat)
    return ev.binary.recall, (top.most_common(1)[0][0] if top else None)


def test_benign_no_false_positives():
    res = run_session(CFG, "benign", seed=7, model_path=None, grace_s=5.0)
    scored = [r for r in res.records if r.scored]
    ev = evaluate([r.true_label for r in scored], [r.pred_label for r in scored])
    assert ev.binary.fpr == 0.0


@pytest.mark.parametrize("name", list(EXPECTED))
def test_attack_detected_and_attributed(name):
    recall, top = _recall_and_top(name)
    assert recall >= 0.85, f"{name} recall {recall}"
    assert top is EXPECTED[name], f"{name} attributed as {top}"
