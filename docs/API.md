# AegisFlight — Backend API

FastAPI app in `src/aegisflight/backend/app.py`, driven by the real-time
`LiveEngine` (`backend/engine.py`). Start with `aegis serve` (default
`127.0.0.1:8000`). Every payload carries `"sim": true`. CORS is open (local demo
only). If `frontend/dist` exists it is served at `/`.

## REST

### `GET /health`
→ `{"status":"ok","version":"0.1.0","sim":true}`

### `GET /api/status`
Live engine status.
```json
{"running":true,"sim":true,"sim_time_s":42.5,"uptime_s":50.1,
 "active_attack":"gps_spoofing","ml_available":true,"threat":true,
 "severity":"HIGH","attack_type":"GPS_SPOOFING","threat_score":0.76,
 "integrity_status":"VALID","run_id":"live-20260922-..."}
```
`threat/severity/attack_type/threat_score` reflect the **last decision tick**.

### `GET /api/metrics`
```json
{"messages_processed":2144,"decisions":149,"alerts":7,
 "throughput_msgs_per_s":61.5,"last_latency_ms":0.4,
 "event_log":{"count":7,"chain_ok":true},"ml_available":true}
```

### `GET /api/events?limit=50`
→ `{"events":[AlertRow, …],"run_id":"…"}` — recent logged alerts (newest first),
each with `attack_type, severity, threat_score, confidence, evidence[],
integrity_status, latency_ms, t`.

### `GET /api/config`
Sanitised config: `attacks` (choices), `decision_rate_hz`, `sample_rate_hz`,
`fusion.{threat_threshold,weights,severity_bands}`, `home`.

### Simulation control (POST)
| Route | Body | Effect |
|---|---|---|
| `/api/simulation/start` | — | start the live loop |
| `/api/simulation/stop` | — | pause the loop |
| `/api/simulation/reset` | — | stop loop → restore clean baseline → start a fresh run |
| `/api/simulation/attack` | `{"attack":"gps_spoofing"}` or `{"attack":"none"}` | inject / clear an attack at runtime |

Unknown attack → `400 {"ok":false,"error":…,"choices":[…]}`.

**Reset semantics.** Reset returns the simulated vehicle to a known-good
baseline: it clears the active attack, **reflashes the simulated firmware fixture
to known-good bytes** (a tampered image is discarded, never re-trusted — see
`FirmwareVerifier.restore_fixture`), clears every extractor / detector / fusion
runtime state, and starts a **new run id** (its own hash chain). Historical audit
records from earlier runs are preserved. These endpoints are `async` so the
loop restart runs on the event loop.

Example:
```bash
curl -X POST localhost:8000/api/simulation/attack \
     -H 'Content-Type: application/json' -d '{"attack":"dos"}'
```

## WebSocket — `GET /ws/telemetry`
Streams one JSON message per simulator tick (~10 Hz):
```json
{"type":"update","sim":true,"t":42.5,
 "telemetry":{"lat":19.13,"lon":72.91,"rel_alt":60.0,"groundspeed":12.0,
              "heading":135,"battery_voltage":23.2,"battery_remaining":67,
              "satellites":14,"flight_mode":"AUTO","armed":true},
 "attack_active":"gps_spoofing",
 "threat":{ /* present only on decision ticks (5 Hz) */
   "threat":true,"threat_score":0.76,"severity":"HIGH",
   "attack_type":"GPS_SPOOFING","confidence":0.76,"evidence":[…],
   "detector_scores":{…},"contributing_detectors":[…],
   "integrity_status":"VALID","latency_ms":0.4,"is_alert":true}}
```
The dashboard's `useLiveData` hook consumes this (auto-reconnect). Slow clients
have frames dropped (bounded per-subscriber queue), never blocking the engine.

## Notes / status
- All endpoints above are **implemented**. There are no PLANNED-but-absent
  routes.
- The engine auto-starts on app startup (FastAPI lifespan).
- Data is a live **simulation**; the API never connects to a real UAV.
