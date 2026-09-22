"""Tamper-evident event logging (SQLite + SHA-256 hash chain).

Each persisted alert stores the SHA-256 of ``previous_hash || canonical(event)``.
Any post-hoc modification, insertion, or deletion breaks the chain, which
:meth:`EventStore.verify_chain` detects — giving the forensic log integrity a
UAV incident investigation needs. The store is deliberately small and
dependency-free (Python's stdlib ``sqlite3``).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.types import ThreatAssessment

GENESIS_HASH = "0" * 64

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    t REAL NOT NULL,
    wall_time REAL NOT NULL,
    attack_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    threat_score REAL NOT NULL,
    confidence REAL NOT NULL,
    integrity_status TEXT NOT NULL,
    latency_ms REAL NOT NULL,
    evidence TEXT NOT NULL,
    detector_scores TEXT NOT NULL,
    contributing_detectors TEXT NOT NULL,
    telemetry TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id);
CREATE INDEX IF NOT EXISTS idx_events_t ON events(t);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    started REAL NOT NULL,
    label TEXT,
    meta TEXT
);
"""


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _hash(prev_hash: str, payload: dict[str, Any]) -> str:
    return hashlib.sha256((prev_hash + _canonical(payload)).encode("utf-8")).hexdigest()


@dataclass
class ChainStatus:
    ok: bool
    length: int
    broken_at: int | None = None
    detail: str = ""


class EventStore:
    def __init__(self, db_path: str | Path = "aegisflight.sqlite") -> None:
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    # -- runs --------------------------------------------------------------- #

    def start_run(self, run_id: str, label: str = "", meta: dict | None = None) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO runs(run_id, started, label, meta) VALUES (?,?,?,?)",
            (run_id, time.time(), label, json.dumps(meta or {})),
        )
        self.conn.commit()

    def list_runs(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM runs ORDER BY started DESC").fetchall()
        return [dict(r) for r in rows]

    # -- events ------------------------------------------------------------- #

    def _last_hash(self) -> str:
        row = self.conn.execute("SELECT hash FROM events ORDER BY id DESC LIMIT 1").fetchone()
        return row["hash"] if row else GENESIS_HASH

    def log_event(self, a: ThreatAssessment, run_id: str) -> dict:
        """Append one alert to the chain; returns the stored row as a dict."""
        prev = self._last_hash()
        payload = {
            "run_id": run_id,
            "t": round(a.t, 3),
            "wall_time": a.wall_time,
            "attack_type": a.attack_type.value,
            "severity": a.severity.value,
            "threat_score": round(a.threat_score, 4),
            "confidence": round(a.confidence, 4),
            "integrity_status": a.integrity_status.value,
            "latency_ms": round(a.latency_ms, 4),
            "evidence": a.evidence,
            "detector_scores": {k: round(v, 4) for k, v in a.detector_scores.items()},
            "contributing_detectors": a.contributing_detectors,
            "telemetry": a.telemetry,
        }
        h = _hash(prev, payload)
        cur = self.conn.execute(
            """INSERT INTO events(
                run_id, t, wall_time, attack_type, severity, threat_score, confidence,
                integrity_status, latency_ms, evidence, detector_scores,
                contributing_detectors, telemetry, prev_hash, hash)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                run_id, payload["t"], payload["wall_time"], payload["attack_type"],
                payload["severity"], payload["threat_score"], payload["confidence"],
                payload["integrity_status"], payload["latency_ms"],
                json.dumps(payload["evidence"]), json.dumps(payload["detector_scores"]),
                json.dumps(payload["contributing_detectors"]), json.dumps(payload["telemetry"]),
                prev, h,
            ),
        )
        self.conn.commit()
        return {"id": cur.lastrowid, "hash": h, **payload}

    def get_events(
        self, run_id: str | None = None, limit: int = 100, since_id: int = 0
    ) -> list[dict]:
        q = "SELECT * FROM events WHERE id > ?"
        args: list[Any] = [since_id]
        if run_id:
            q += " AND run_id = ?"
            args.append(run_id)
        q += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        rows = self.conn.execute(q, args).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            for k in ("evidence", "detector_scores", "contributing_detectors", "telemetry"):
                d[k] = json.loads(d[k])
            out.append(d)
        return out

    def count_events(self, run_id: str | None = None) -> int:
        if run_id:
            row = self.conn.execute(
                "SELECT COUNT(*) c FROM events WHERE run_id=?", (run_id,)
            ).fetchone()
        else:
            row = self.conn.execute("SELECT COUNT(*) c FROM events").fetchone()
        return int(row["c"])

    # -- integrity ---------------------------------------------------------- #

    def verify_chain(self, run_id: str | None = None) -> ChainStatus:
        q = "SELECT * FROM events"
        args: list[Any] = []
        if run_id:
            q += " WHERE run_id=?"
            args.append(run_id)
        q += " ORDER BY id ASC"
        rows = self.conn.execute(q, args).fetchall()
        prev = GENESIS_HASH
        for i, r in enumerate(rows):
            payload = {
                "run_id": r["run_id"],
                "t": r["t"],
                "wall_time": r["wall_time"],
                "attack_type": r["attack_type"],
                "severity": r["severity"],
                "threat_score": r["threat_score"],
                "confidence": r["confidence"],
                "integrity_status": r["integrity_status"],
                "latency_ms": r["latency_ms"],
                "evidence": json.loads(r["evidence"]),
                "detector_scores": json.loads(r["detector_scores"]),
                "contributing_detectors": json.loads(r["contributing_detectors"]),
                "telemetry": json.loads(r["telemetry"]),
            }
            expect = _hash(prev, payload)
            if r["prev_hash"] != prev or r["hash"] != expect:
                return ChainStatus(
                    ok=False, length=len(rows), broken_at=i,
                    detail=f"chain broken at event id={r['id']}",
                )
            prev = r["hash"]
        return ChainStatus(ok=True, length=len(rows), detail="chain intact")

    def close(self) -> None:
        self.conn.close()
