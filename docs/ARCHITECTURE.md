# AegisFlight — Architecture

```
FlightSimulator ──▶ Attack.perturb_state ──▶ MavlinkEncoder(+noise)
                                                    │ RawPacket[]
                                    Attack.perturb_packets / before_encode
                                                    │
                                              MavlinkDecoder
                                                    │ MessageEnvelope[]
                                              FeatureExtractor
                                                    │ FeatureFrame
        ┌───────────────┬───────────────┬──────────┴───────────┐
   ProtocolDetector  PhysicsDetector  AnomalyDetector   IntegrityDetector
        └───────────────┴───────────────┴──────────┬───────────┘
                                              FusionEngine
                                                    │ ThreatAssessment
                             ┌──────────────────────┼──────────────────────┐
                      EventStore (hash chain)  FastAPI + WebSocket    Benchmark harness
                                                    │
                                             React dashboard
```
(See `docs/diagrams/system-architecture.mmd` and `end-to-end-flow.mmd`.)

## Why these boundaries

| Boundary | Rationale |
|---|---|
| **Simulator emits clean truth; noise added at the codec** | keeps ground truth pristine for scoring; puts observation noise at the realistic sensor boundary |
| **Attacks perturb via typed hooks** (`perturb_state` / `perturb_packets` / `integrity_status`) | value vs stream vs firmware attacks stay cleanly separated; adding one doesn't touch detectors |
| **Transport-neutral `MessageEnvelope`** | pymavlink types never leak past the decoder; features/detectors are protocol-detail-free |
| **Detectors read only `FeatureFrame`** | detectors are independent, unit-testable, and can't peek at ground truth |
| **`FusionEngine` is the only combiner** | one place owns weighting, attribution, severity, dedup |
| **`IDSPipeline` is the only wiring** | backend and benchmark share identical detection behaviour |
| **Ground truth rides on `TelemetryTick` but pipeline ignores it** | honest metrics: only the benchmark reads labels |

## Components (responsibility · input → output · key files · failure mode)

- **Simulator** — deterministic flight · `SimulatorConfig` → `FlightState[]` ·
  `simulator/flight.py` · *fails safe:* pure function of seed.
- **MAVLink codec** — genuine v2 encode/decode + sensor noise · `FlightState`
  ↔ bytes ↔ `MessageEnvelope` · `mavlink/codec.py` · *fails:* robust parser
  drops BAD_DATA.
- **Attacks** — 6 safe simulations · perturbation hooks · `attacks/*` ·
  *fails:* identity hooks by default (no-op).
- **Sources** — orchestrate sim+encode+attack+decode · → `TelemetryTick` ·
  `sources/stream.py`.
- **Features** — online extraction · `MessageEnvelope` → `FeatureFrame` ·
  `features/extractor.py` · *fails:* guards `None` until first message.
- **Detectors** — 4 layers · `FeatureFrame` → `DetectorResult` · `detectors/*` ·
  *fails:* ML degrades to no-op if model missing.
- **Fusion** — combine + attribute + severity + dedup · → `ThreatAssessment` ·
  `fusion/engine.py`.
- **Pipeline** — wire + latency measurement · `TelemetryTick` →
  `ThreatAssessment` · `pipeline.py`.
- **Logging** — tamper-evident persistence · `logging/store.py`.
- **Integrity** — SHA-256 firmware verification · `integrity/verifier.py`.
- **Backend** — live engine + REST/WS · `backend/{engine,app}.py`.
- **Frontend** — dashboard · `frontend/`.
- **Benchmark/metrics** — authoritative evaluation · `benchmark/*`, `metrics/*`.

## Runtime cadences
Simulator/telemetry: 10 Hz. Decision/fusion: 5 Hz (200 ms budget; actual mean
17.7 ms). WebSocket push: per tick (10 Hz), threat block on decision ticks.
Firmware re-verify: every `recheck_every` (5) decisions.

## Concurrency
The library is synchronous and single-threaded per session (deterministic). The
backend runs one asyncio task (`LiveEngine._loop`) that advances the sim in real
time and broadcasts to per-subscriber bounded queues; slow WebSocket clients drop
frames rather than block the engine.

See `docs/CODEBASE_MAP.md` for import-direction rules and `docs/DATA_FLOW.md` for
object lifecycles.
