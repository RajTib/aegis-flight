# AegisFlight — Engineering Handoff

For the next engineer taking this over. Read this, then `QUICKSTART.md`, then
`ARCHITECTURE.md` / `END_TO_END_FLOW.md`.

## What this project is
A Stage-1 proof-of-concept UAV Intrusion Detection System for the PUSHPAK
challenge. It detects six attack classes on a **simulated** MAVLink link +
firmware, fuses four detectors into explainable alerts, logs them to a
tamper-evident chain, and shows them on a live dashboard. **Everything is a local
simulation — no real drone or network is involved.**

## Current implementation status

| Subsystem | Status |
|---|---|
| Config, core types/enums/geo | ✅ COMPLETE |
| Simulator (3 routes, deterministic, lands) | ✅ COMPLETE |
| MAVLink v2 codec (pymavlink) + sensor noise | ✅ COMPLETE |
| Six attacks (value/stream/firmware) | ✅ COMPLETE |
| Firmware integrity (real SHA-256) | ✅ COMPLETE |
| Feature extraction (11 ML features + more) | ✅ COMPLETE |
| Detectors: protocol / physics / integrity | ✅ COMPLETE |
| Detector: ML anomaly (IsoForest+Mahalanobis) | ✅ COMPLETE (trained; graceful no-op if model absent) |
| Fusion engine | ✅ COMPLETE |
| Pipeline | ✅ COMPLETE |
| Event logging (per-run hash chain) | ✅ COMPLETE |
| Metrics + benchmark harness + figures | ✅ COMPLETE |
| CLI (`aegis`) | ✅ COMPLETE |
| Backend (FastAPI REST + WebSocket) | ✅ COMPLETE |
| Frontend dashboard (React/Vite) | ✅ COMPLETE (builds to `frontend/dist`) |
| Tests (unit/integration/e2e/API) | ✅ COMPLETE |
| External real-flight validation (PX4 ULog, ALFA tlog) | ✅ analysis-only (`docs/EXTERNAL_DATA.md`) |
| Extended benchmark v2 + simultaneous attacks | ✅ (`docs/BENCHMARKING.md`) |
| Real-RF / SITL / hardware | ⛔ PLANNED (future work; not built) |

## What you can demonstrate today
`aegis serve` → dashboard → click any of the six attacks → live detection with
evidence, severity, latency; firmware tamper → SHA-256 INVALID alert; event log
verifiable via `aegis verify-log`. Headless: `python scripts/run_demo.py`.
Metrics: `aegis benchmark`.

## Current limitations (be honest)
- A *constant, fully-consistent* GPS offset is only detected at the transition
  (drift/replay-freeze detected throughout). GPS recall 0.95 is the onset latency
  cost, not steady-state misses.
- GPS position residual has a ~3 s post-attack tail (disclosed; scored via a
  grace window — see `BENCHMARKING.md`).
- ML inference dominates compute (17.7 ms/decision); fine at 5 Hz, but it makes
  the full benchmark take a few minutes.
- Simulated link only; no real RF, no message-signing verification, single-node
  SQLite.

## Most important files
`pipeline.py` (wires everything), `fusion/engine.py` (the decision),
`features/extractor.py` (the signals), `detectors/*`, `sources/stream.py` (the
orchestration), `backend/engine.py` (live loop), `configs/*.yaml` (all tunables).
Full map: `docs/FILE_REFERENCE.md`.

## How to run (exact commands)
```bash
pip install -e ".[dev]"                     # deps + editable install
aegis train                                 # train anomaly model -> models/isoforest.joblib
aegis simulate --attack dos                 # one session, printed alerts
aegis benchmark                             # metrics + figures -> artifacts/
pytest                                      # full suite
npm --prefix frontend install && npm --prefix frontend run build
aegis serve                                 # dashboard at http://127.0.0.1:8000
aegis verify-log artifacts/aegisflight_live.sqlite
```
Demo script: `docs/DEMO_RUNBOOK.md`.

## How to modify
- **Thresholds:** `configs/detector.yaml` (see `CONFIGURATION.md`). Restart after
  editing.
- **New attack / detector:** `docs/ADDING_A_NEW_ATTACK.md` /
  `ADDING_A_NEW_DETECTOR.md`.
- **Retrain:** `aegis train` (required after changing `ML_FEATURES`, the
  simulator, or noise).

## Do NOT change casually
- **`ML_FEATURES` order/content** (`features/extractor.py`) — the saved model
  depends on it exactly; changing it silently breaks inference. Retrain.
- **`FlightState` / `MessageEnvelope` fields** — codec + extractor contract.
- **Enum `.value` strings** — API/DB/JSON contract.
- **The MAVLink message field mappings** — encoder and extractor must agree.
- **The event schema / hash-chain canonicalisation** — breaks existing logs.
- **The benchmark scoring policy** (warmup/grace) — changing it changes reported
  numbers; if you do, re-document it.
- **Attack hook signatures** — many attacks depend on the base interface.

## Known problems / watch-list
- `httpx`/Starlette `TestClient` deprecation warning in `backend/tests` (cosmetic).
- ML benchmark runtime (~minutes) due to `score_samples` cost; `--no-model` is
  fast for quick checks.

## Recommended next steps (grounded in this repo)
1. Add MAVLink 2 **message-signing** verification (the protocol detector already
   has a `require_signing` hook — wire real signature checks).
2. Add a **real UDP MAVLink source** alongside `SimulatedTelemetrySource` and
   validate against ArduPilot/PX4 SITL (single integration point).
3. Speed ML inference (train with `n_jobs=1`, or a smaller forest) if targeting a
   constrained companion computer.
4. Broaden benign training diversity (wind, GPS-degradation) to tighten FPR
   further under adverse-but-benign conditions.
5. Package `aegis serve` + built frontend as a one-command container for judges.

## Recovery note
This repository was recovered after a mid-build crash of an earlier session (see
`docs/RECOVERY_AUDIT.md`). The crash left only the foundation; everything above
was implemented during continuation. Nothing was thrown away — the foundation
(config/core) is unchanged and was used as the contract.
