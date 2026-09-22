# AegisFlight — Event Logging

Alerts are persisted to SQLite by `EventStore` (`logging/store.py`) in a
**tamper-evident, per-run SHA-256 hash chain**: any post-hoc edit, insertion, or
deletion breaks the chain and is detected by `verify_chain`.

## Schema

`events` table (one row per logged alert):

| Column | Type | Meaning |
|---|---|---|
| `id` | INTEGER PK | autoincrement |
| `run_id` | TEXT | which run/session |
| `t` | REAL | simulator time (s) |
| `wall_time` | REAL | wall-clock epoch |
| `attack_type` | TEXT | predicted `AttackType` |
| `severity` | TEXT | `Severity` |
| `threat_score`, `confidence` | REAL | fused score / heuristic confidence |
| `integrity_status` | TEXT | firmware verdict at the time |
| `latency_ms` | REAL | per-decision compute latency |
| `evidence` | TEXT (JSON) | human-readable reasons |
| `detector_scores` | TEXT (JSON) | per-detector scores |
| `contributing_detectors` | TEXT (JSON) | detectors with score > 0.1 |
| `telemetry` | TEXT (JSON) | compact telemetry context |
| `prev_hash` | TEXT | previous event's hash in this run |
| `hash` | TEXT | `SHA-256(prev_hash ‖ canonical(payload))` |

`runs` table: `run_id`, `started`, `label`, `meta`.

## Hash chain
- **Canonicalisation:** `json.dumps(payload, sort_keys=True,
  separators=(",",":"))` over a fixed field set (the columns above except
  `id`/`prev_hash`/`hash`).
- **Per-run chaining:** each run is its own chain from `GENESIS` (64 zeros).
  `log_event` reads the last hash *for that run_id*; `verify_chain(run_id)`
  recomputes from genesis; `verify_chain()` (no arg) verifies every run
  independently and reports the first break.
- **Tamper detection:** `ChainStatus(ok, length, broken_at, detail)`.
  `broken_at` is the 0-indexed position of the first inconsistent event.

## Where it lives
- CLI `aegis simulate --db path.sqlite` logs that session's alerts.
- The live backend logs to `artifacts/aegisflight_live.sqlite` (gitignored).
- `*.sqlite` is gitignored (regenerable operational data).

## Inspecting / verifying
```bash
aegis verify-log artifacts/aegisflight_live.sqlite       # -> "chain: OK"
sqlite3 artifacts/aegisflight_live.sqlite \
  "SELECT t, attack_type, severity, threat_score FROM events ORDER BY id DESC LIMIT 10;"
```
Programmatically:
```python
from aegisflight.logging import EventStore
store = EventStore("run.sqlite")
store.verify_chain()               # ChainStatus(ok=True, ...)
store.get_events(limit=20)         # list of dicts (JSON fields decoded)
```

## What happens if an event is modified
Editing any field (e.g. lowering a `threat_score` to hide an incident), deleting
a row, or inserting one recomputes to a different hash → `verify_chain` returns
`ok=False` with the offending index. This gives the forensic log the integrity a
UAV incident investigation needs. Tested by
`tests/unit/test_integrity_and_logging.py::test_hash_chain_detects_tamper`.
