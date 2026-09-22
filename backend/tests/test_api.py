"""Backend API tests via FastAPI TestClient (drives the live engine briefly)."""

import time

import pytest
from fastapi.testclient import TestClient

from aegisflight.backend.app import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:  # runs lifespan -> engine starts
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["sim"] is True


def test_status_and_config(client):
    time.sleep(1.0)  # let the engine advance a little
    st = client.get("/api/status").json()
    assert st["sim"] is True
    assert st["running"] is True
    cfg = client.get("/api/config").json()
    assert "gps_spoofing" in cfg["attacks"]
    assert cfg["fusion"]["threat_threshold"] == 0.45


def test_inject_attack_and_detect(client):
    r = client.post("/api/simulation/attack", json={"attack": "gps_spoofing"})
    assert r.json()["ok"] is True
    # let the sliding-window residual accumulate and fire
    detected = False
    for _ in range(30):
        time.sleep(0.4)
        st = client.get("/api/status").json()
        if st["threat"] and st["attack_type"] == "GPS_SPOOFING":
            detected = True
            break
    assert detected, "GPS spoofing not detected via live API"
    client.post("/api/simulation/attack", json={"attack": "none"})


def test_unknown_attack_rejected(client):
    r = client.post("/api/simulation/attack", json={"attack": "nope"})
    assert r.status_code == 400


def test_metrics_and_events(client):
    m = client.get("/api/metrics").json()
    assert m["messages_processed"] > 0
    assert m["event_log"]["chain_ok"] in (True, False)
    ev = client.get("/api/events?limit=5").json()
    assert "events" in ev
