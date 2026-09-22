# AegisFlight — Troubleshooting

Symptom → cause → check → fix. Based on issues actually encountered building this.

### `ModuleNotFoundError: aegisflight`
- **Cause:** package not installed into the active environment.
- **Check:** `python -c "import aegisflight"`.
- **Fix:** activate the venv and `pip install -e ".[dev]"`.

### `aegis: command not found`
- **Cause:** venv not active, or console-scripts dir not on PATH.
- **Fix:** activate the venv, or use `python -m aegisflight.cli <cmd>`.

### ML detector shows "off" / no ML evidence
- **Cause:** `models/isoforest.joblib` missing or incompatible sklearn version.
- **Check:** file exists; `aegis serve` logs / dashboard header "ML off".
- **Fix:** `aegis train`. Detection still works via rule/physics detectors
  without it (graceful no-op by design).

### `joblib.load` error / weird ML scores after upgrading libs
- **Cause:** model trained with a different `sklearn`/`numpy` (see the bundle's
  `metadata.sklearn_version`).
- **Fix:** retrain — `aegis train`.

### Benign flight raises an alert (false positive)
- **Cause:** a transient (sharp turn, throttle change) or an over-tight
  threshold. Historically the `battery_v_rate` ML feature caused this (now
  removed from `ML_FEATURES`).
- **Check:** the alert's evidence names the driver; `aegis benchmark` reports FPR.
- **Fix:** raise the relevant threshold in `configs/detector.yaml`, or exclude a
  noisy feature and retrain. See `docs/FEATURES.md#false-positive-conditions`.

### GPS spoofing keeps alerting a few seconds after "Clear attack"
- **Cause:** expected — the bounded position-residual window takes ~3 s to clear
  after the position snaps back (documented recovery tail).
- **Fix:** none needed; the benchmark scores this with a grace window.

### Port 8000 already in use
- **Fix:** `aegis serve --port 8137` (and open that port). On Windows, find the
  holder with `Get-NetTCPConnection -LocalPort 8000`.

### Dashboard shows raw JSON at `/` ("frontend not built")
- **Cause:** `frontend/dist` doesn't exist.
- **Fix:** `npm --prefix frontend install && npm --prefix frontend run build`,
  then restart `aegis serve`. Or use dev mode (`npm --prefix frontend run dev`).

### Dashboard badge stuck on "Disconnected"
- **Cause:** backend not running, wrong port, or WebSocket blocked.
- **Check:** `curl http://127.0.0.1:8000/health`.
- **Fix:** start `aegis serve`; if using the dev server, ensure it proxies to the
  backend's port (default 8000).

### Frontend build fails on `tsc` project-reference error
- **Cause:** a composite `tsconfig` that disables emit (TS6310).
- **Fix:** already resolved — the build uses `tsc --noEmit && vite build` with a
  single standalone `tsconfig.json`.

### Unicode crash printing evidence on Windows console (`charmap` codec)
- **Cause:** evidence uses `≥`, `°`, `²`; the Windows cp1252 console can't encode.
- **Fix:** the CLI forces UTF-8 stdout (`main()`); if scripting yourself, set
  `PYTHONIOENCODING=utf-8`.

### `verify-log` reports BROKEN unexpectedly
- **Cause:** the DB mixes events from an old global-chain build, or a row was
  edited.
- **Fix:** for a fresh demo, delete the `*.sqlite` and re-run; genuine tampering
  is exactly what this is meant to catch.

### Benchmark is slow (minutes)
- **Cause:** ML `score_samples` runs per decision across ~23k decisions.
- **Fix (for quick checks):** `aegis benchmark --no-model` (rule+physics only,
  seconds). The per-decision latency (17.7 ms) is the real-time-relevant number.

### `pymavlink` install/build issues
- **Check:** `python -c "from pymavlink.dialects.v20 import common"`.
- **Fix:** ensure a recent pip; reinstall `pip install --force-reinstall pymavlink`.
