# AegisFlight — Demo Runbook

For recording the Stage-1 demonstration video. A teammate can run this without
the original author. Everything shown is a **local simulation** — say so on
camera.

## Pre-demo checklist
```bash
pip install -e ".[dev]"                       # deps installed
aegis train                                   # models/isoforest.joblib exists
npm --prefix frontend install && npm --prefix frontend run build   # frontend/dist exists
pytest -q                                     # 44 passing (confidence check)
```
- Close other apps using port 8000.
- Have `aegis verify-log` ready in a second terminal.

## Startup
```bash
aegis serve            # http://127.0.0.1:8000
```
Open the browser. The header shows **● Simulation**, **● Connected**, **ML on**,
and the sim clock advancing. Point out the "SIMULATION" labelling.

## Segment 1 — Normal flight (~20 s)
- Show the **Threat State = NORMAL**, the position track drawing the survey
  pattern, live telemetry (altitude ~60 m, speed ~12 m/s, battery draining), and
  the flat threat-score sparkline below the 0.45 line.
- Narrate: four detectors run every 200 ms; nothing fires on benign flight.

## Segment 2 — GPS spoofing
- Click **GPS Spoofing**. Within ~1.5 s the Threat State turns **HIGH /
  GPS SPOOFING**; the Evidence panel shows *"position residual > 12 m (reported
  track diverges from velocity)"* and an ML corroboration line.
- Point at the **Detector Contributions** bars (physics + ML light up) and the
  sparkline crossing the threshold.
- Click **Clear attack** — the score decays back to normal within a few seconds
  (mention the disclosed ~3 s recovery tail).

## Segment 3 — Denial of service
- Click **Denial of Service**. Threat goes **CRITICAL / DOS**; evidence shows the
  message-rate spike / sequence gaps. Note the message counter jumping in the
  bottom metrics bar. Clear it.

## Segment 4 — Firmware tampering
- Click **Firmware Tamper**. The **Firmware** field flips to **INVALID** and a
  **FIRMWARE_INTEGRITY** alert appears with the exact component and SHA-256
  mismatch. Emphasise this is a *real* cryptographic check.

## Segment 5 — Event log integrity
- In the second terminal:
  ```bash
  aegis verify-log artifacts/aegisflight_live.sqlite     # -> chain: OK
  ```
- Explain the per-run SHA-256 hash chain makes the alert log tamper-evident.

## Segment 6 — Benchmark results
- Show `artifacts/figures/per_attack_recall.png`, `confusion_matrix.png`, and
  `threat_timeline.png`, and quote from `artifacts/benchmarks/summary.md`:
  accuracy 0.997, recall 0.99, **FPR 0.0002**, detection latency 0.36 s. State
  they are reproducible with `aegis benchmark`.

## Shutdown
`Ctrl-C` the server. Optionally `aegis benchmark` on camera to show the numbers
regenerate.

## If you prefer no dashboard
```bash
python scripts/run_demo.py         # narrated, deterministic, all six scenarios
```

## Troubleshooting during the demo
- Dashboard blank / "frontend not built" JSON at `/` → run the `npm run build`
  step, restart `aegis serve`.
- Port busy → `aegis serve --port 8137` and open that port.
- No detections → confirm `models/isoforest.joblib` exists (`aegis train`); note
  detection still works without ML via the rule/physics detectors.
- WebSocket "Disconnected" badge → backend not running or wrong port; restart.
