# AegisFlight — Testing

```
        ╱ e2e (2) ╲          full slice: sim→IDS→alert→SQLite→verify
       ╱ backend (5)╲        FastAPI API + live detection
      ╱ integration(7)╲      all 6 attacks detected & attributed, benign FPR 0
     ╱   unit (30)      ╲    geo/config/simulator/codec/integrity/logging/
    ╱────────────────────╲   fusion/metrics
```
Run with the project venv; the suite must pass in full (the count grows with new
features — `pytest -q` prints it).

## Commands
| Command | Purpose |
|---|---|
| `pytest` | everything (~2 min; integration/e2e run full 120 s sessions) |
| `pytest tests/unit -q` | fast unit subset (seconds) |
| `pytest tests/integration -q` | all six attacks through the pipeline |
| `pytest tests/e2e -q` | end-to-end slice + hash-chain verify |
| `pytest backend/tests -q` | API + live detection (drives `LiveEngine`) |
| `ruff check src tests scripts backend` | lint (must be clean) |
| `python scripts/run_demo.py` | narrated smoke test of all scenarios |

`pyproject.toml` sets `testpaths = ["tests", "backend/tests"]` and
`asyncio_mode = "auto"`.

## What each suite verifies
- **`test_geo`** — haversine/offset/bearing/wrap round-trips.
- **`test_config`** — defaults, YAML-over-defaults merge, missing-file resilience.
- **`test_simulator`** — determinism, tick count, reaches cruise & lands (all
  routes), speed bounds, position↔velocity consistency, battery reserve.
- **`test_mavlink_codec`** — all six message types encode/decode; position
  round-trips within noise; independent GPS/baro altitude channels; vehicle ids.
- **`test_integrity_and_logging`** — SHA-256 valid→tamper→detect, missing
  component; hash-chain intact, tamper detection (`broken_at`), multi-run
  independence.
- **`test_fusion_and_metrics`** — lone firmware triggers, lone weak ML doesn't,
  strong physics attributes correctly, all-benign is NORMAL; metrics maths.
- **`test_pipeline`** (integration) — benign FPR 0; each attack recall ≥ 0.85 and
  attributed to the right class (ML off, so it's a floor not the headline).
- **`test_end_to_end`** — GPS spoof → alerts with evidence → SQLite → chain OK;
  compute p95 < 50 ms.
- **`test_api`** (backend) — health/status/config; live GPS injection detected;
  unknown attack rejected (400); metrics/events.

## Minimum sequence before a demo / release
```bash
ruff check src tests scripts backend      # clean
pytest -q                                  # all passing
aegis train && aegis benchmark             # metrics regenerate, FPR ≈ 0
python scripts/run_demo.py                 # scenarios narrate correctly
```

## Notes
- Integration/e2e run real sessions (no mocks) for fidelity — hence the runtime.
- A harmless `StarletteDeprecationWarning` (httpx TestClient) appears in backend
  tests.
- Tests use seeds/`tmp_path` for determinism and isolation; no test writes into
  the repo tree.
