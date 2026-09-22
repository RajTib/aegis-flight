"""End-to-end: simulated drone -> MAVLink -> IDS -> alert -> SQLite -> verify.

Exercises the full vertical slice the demo relies on, including persistence and
the tamper-evident event log.
"""

from aegisflight.benchmark.runner import run_session
from aegisflight.config import load_config
from aegisflight.logging import EventStore


def test_gps_spoof_flows_to_event_log(tmp_path):
    cfg = load_config()
    res = run_session(cfg, "gps_spoofing", seed=3, model_path=None)
    alerts = [a for a in res.assessments if a.is_alert]
    assert alerts, "GPS spoofing produced no alerts"
    assert any(a.attack_type.value == "GPS_SPOOFING" for a in alerts)
    assert all(a.evidence for a in alerts), "alerts must carry evidence"

    # persist to SQLite and verify the hash chain
    db = tmp_path / "e2e.sqlite"
    store = EventStore(db)
    store.start_run("e2e", label="gps")
    for a in alerts:
        store.log_event(a, "e2e")
    assert store.count_events("e2e") == len(alerts)
    cs = store.verify_chain("e2e")
    assert cs.ok

    # a stored alert exposes its evidence + telemetry context
    rows = store.get_events("e2e", limit=1)
    assert rows and rows[0]["attack_type"] == alerts[-1].attack_type.value
    assert isinstance(rows[0]["evidence"], list)
    store.close()


def test_latency_is_realtime_capable():
    cfg = load_config()
    res = run_session(cfg, "benign", seed=1, model_path=None)
    import numpy as np
    p95 = float(np.percentile(res.compute_latency_ms, 95))
    # decision budget at 5 Hz is 200 ms; we must be well under it
    assert p95 < 50.0, f"compute p95 {p95} ms too high"
