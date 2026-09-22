# AegisFlight — Data Flow & Object Lifecycle

The core objects and how they transform. All are defined in
`core/types.py` unless noted.

```
FlightState ──encode──▶ RawPacket ──decode──▶ MessageEnvelope
   (truth)                (bytes)               (observed)
                                                   │ update()
                                                   ▼
                                             FeatureFrame ──▶ DetectorResult×4
                                                                   │ fuse()
                                                                   ▼
                                                            ThreatAssessment
                                          (benchmark)  ──▶ DecisionRecord
                                          (logging)    ──▶ events row (SQLite)
```

## `FlightState` — clean ground truth (simulator)
Physical state at one tick: `t, lat, lon, alt_msl, rel_alt, vx/vy/vz,
groundspeed, vertical_speed, ax/ay/az, roll/pitch/yaw (+speeds), heading,
throttle, battery_voltage, battery_remaining, satellites, gps_fix_type, hdop,
baro_alt, flight_mode, armed, mission_seq, phase`. **Produced by**
`FlightSimulator`. **Never seen by** detectors — only the encoder (and, via
`TelemetryTick.truth_state`, the benchmark).

## `RawPacket` — a frame on the wire (`mavlink/codec.py`)
`send_time: float`, `data: bytes` (genuine MAVLink 2). **Produced by** the
encoder / attack packet-injection; **consumed by** the decoder. Attacks add
sensor noise (encoder) and drop/dup/delay/inject at this layer.

## `MessageEnvelope` — observed message
`recv_time, sysid, compid, msgid, msgname, seq, signed, byte_len, fields:dict`.
Transport-neutral (no pymavlink types leak downstream). **Produced by** decoder;
**consumed by** `FeatureExtractor.update`.

## `TelemetrySnapshot` — reconstructed observed state
The extractor's running best estimate (all fields Optional; `None` = not yet
seen) plus `gps_age`/`attitude_age`. **Owned by** `FeatureExtractor`; a compact
subset rides on each `ThreatAssessment.telemetry`.

## `FeatureFrame` — features at a decision tick (`features/extractor.py`)
Network + navigation + sensor + command features (see `docs/FEATURES.md`) plus
the `snapshot` and `commands_recent`. `to_vector()` yields the 11-dim
`ML_FEATURES`. **Produced by** `extract(t)`; **consumed by** all detectors.

## `DetectorResult` — one layer's output
`detector: DetectorName, score, triggered, evidence[], attack_votes{}, signals{}`.
**Produced by** each detector; **consumed by** `FusionEngine`.

## `ThreatAssessment` — the fused decision
`t, wall_time, threat, threat_score, severity, attack_type, confidence,
secondary_indicators, evidence, detector_scores, contributing_detectors,
integrity_status, latency_ms, telemetry, is_alert`; `to_dict()` for JSON.
**Produced by** `FusionEngine.fuse`; **consumed by** the backend (WS/REST),
event store, and benchmark.

## `DecisionRecord` — labelled tick (`benchmark/runner.py`)
`t, true_label, pred_label, threat, latency_ms, severity, scored`. Ground-truth
`true_label` from the attack; `scored=False` for warmup/grace ticks. **Consumed
by** `metrics.evaluate`.

## events row — persisted alert (`logging/store.py`)
The `ThreatAssessment` payload + `prev_hash` + `hash` (per-run SHA-256 chain).
See `docs/EVENT_LOGGING.md`.

## Ground-truth isolation
`TelemetryTick` (`sources/stream.py`) carries both the observed `messages` and
the hidden `truth_state`/`label`/`integrity_truth`. The **pipeline reads only
`messages`**; ground truth is consumed exclusively by the benchmark runner for
scoring. This boundary is what keeps the reported metrics honest.
