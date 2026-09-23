"""Firmware integrity verifier and tamper-evident event log."""

from aegisflight.core.enums import AttackType, IntegrityStatus, Severity
from aegisflight.core.types import ThreatAssessment
from aegisflight.integrity.verifier import FirmwareVerifier
from aegisflight.logging import EventStore


# ---- firmware integrity ----
def test_firmware_valid_then_tampered(tmp_path):
    v = FirmwareVerifier(tmp_path)
    v.write_fixture()
    v.build_manifest()
    assert v.verify().status is IntegrityStatus.VALID

    assert v.tamper("ekf3_params.bin") is True
    rep = v.verify()
    assert rep.status is IntegrityStatus.INVALID
    assert "ekf3_params.bin" in rep.tampered

    v.restore()
    assert v.verify().status is IntegrityStatus.VALID


def test_firmware_missing_component(tmp_path):
    v = FirmwareVerifier(tmp_path)
    v.write_fixture()
    v.build_manifest()
    (tmp_path / "comms_stack.bin").unlink()
    rep = v.verify()
    assert rep.status is IntegrityStatus.INVALID
    assert "comms_stack.bin" in rep.missing


def test_restore_fixture_reflashes_known_good_not_tampered_bytes(tmp_path):
    """Reset must reflash the *known-good* image, not re-trust tampered bytes.

    Tampers a component AND drops a stray unexpected component, then restores.
    The restored bytes must equal the pristine fixture (proving tampered bytes
    were discarded, not promoted into the manifest) and the stray file must be
    gone — otherwise a reset would silently bless a compromised firmware.
    """
    v = FirmwareVerifier(tmp_path)
    v.write_fixture()
    v.build_manifest()
    good = (tmp_path / "ekf3_params.bin").read_bytes()

    v.tamper("ekf3_params.bin")
    (tmp_path / "evil.bin").write_bytes(b"attacker payload")
    assert v.verify().status is IntegrityStatus.INVALID

    v.restore_fixture()

    rep = v.verify()
    assert rep.status is IntegrityStatus.VALID
    # tampered bytes were discarded and known-good bytes restored
    assert (tmp_path / "ekf3_params.bin").read_bytes() == good
    # the stray unexpected component was removed
    assert not (tmp_path / "evil.bin").exists()
    # the manifest describes the known-good image, so a re-tamper is caught again
    v.tamper("ekf3_params.bin")
    assert v.verify().status is IntegrityStatus.INVALID


# ---- event log hash chain ----
def _assessment(t):
    return ThreatAssessment(
        t=t, wall_time=1.0, threat=True, threat_score=0.7, severity=Severity.HIGH,
        attack_type=AttackType.GPS_SPOOFING, confidence=0.8, evidence=["e"],
        detector_scores={"physics_consistency": 0.9},
        contributing_detectors=["physics_consistency"],
        integrity_status=IntegrityStatus.VALID, latency_ms=0.4, telemetry={}, is_alert=True,
    )


def test_hash_chain_intact(tmp_path):
    db = tmp_path / "e.sqlite"
    store = EventStore(db)
    store.start_run("r1")
    for i in range(5):
        store.log_event(_assessment(float(i)), "r1")
    cs = store.verify_chain("r1")
    assert cs.ok and cs.length == 5


def test_hash_chain_detects_tamper(tmp_path):
    db = tmp_path / "e.sqlite"
    store = EventStore(db)
    store.start_run("r1")
    for i in range(5):
        store.log_event(_assessment(float(i)), "r1")
    store.conn.execute("UPDATE events SET threat_score=0.1 WHERE id=3")
    store.conn.commit()
    cs = store.verify_chain("r1")
    assert not cs.ok
    assert cs.broken_at == 2


def test_multiple_runs_verify_independently(tmp_path):
    db = tmp_path / "e.sqlite"
    store = EventStore(db)
    for run in ("r1", "r2"):
        store.start_run(run)
        for i in range(3):
            store.log_event(_assessment(float(i)), run)
    assert store.verify_chain("r1").ok
    assert store.verify_chain("r2").ok
    assert store.verify_chain().ok  # all runs
