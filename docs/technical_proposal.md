# AegisFlight — Technical Proposal

**PUSHPAK Grand Challenge 2026-27 · IIT Bombay Techfest · Security of Drones ·
Objective 2 — Drone Intrusion Detection System (Stage 1)**

Team Ardra · Proof-of-concept simulation · All figures produced by
`scripts/benchmark.py` from real runs.

---

## 1. Introduction
Small UAVs increasingly rely on the MAVLink protocol for telemetry and command
over links that are typically unauthenticated and unencrypted. This exposes them
to GPS spoofing, protocol abuse, command injection, telemetry falsification,
denial of service, and firmware tampering. AegisFlight is a hybrid, explainable
Intrusion Detection System that monitors the MAVLink stream and firmware
attestation of a UAV and produces severity-ranked, evidence-backed alerts in
real time. This document describes a Stage-1 proof-of-concept implemented and
benchmarked entirely in a reproducible local simulation.

## 2. Problem statement
Detect, classify, and explain intrusions against a UAV's cyber-physical link
with **high recall, very low false-positive rate, low latency, and low compute**,
in a way that is **reproducible** and offers a credible **deployment path**. The
system must cover the six representative attack classes named by the challenge
and must not depend on real hardware at Stage 1.

## 3. Threat model
Six attack classes, all simulated locally (see `docs/THREAT_MODEL.md`):
GPS spoofing, MAVLink anomaly, command injection, telemetry manipulation, denial
of service, and firmware integrity violation. The IDS observes the full MAVLink 2
stream (vehicle sysid 1, GCS 254/255) plus a SHA-256 firmware manifest (unsigned in the PoC). The
adversary can inject/modify/drop frames and tamper firmware files but cannot
forge a valid SHA-256.

## 4. System architecture
*(Diagram: [`diagrams/system-architecture.mmd`](diagrams/system-architecture.mmd);
data-flow: [`diagrams/end-to-end-flow.mmd`](diagrams/end-to-end-flow.mmd).)*

A deterministic simulator emits clean ground-truth `FlightState`; a genuine
`pymavlink` MAVLink 2 codec encodes it (with sensor noise) and decodes it back to
transport-neutral `MessageEnvelope`s; attacks perturb telemetry values, the
packet stream, or firmware files. The IDS extracts features online and runs four
detectors whose outputs are fused into a `ThreatAssessment`, logged to a
tamper-evident SQLite hash chain and streamed to a React dashboard over a
WebSocket. The same pipeline backs a benchmark harness. (Modules:
`src/aegisflight/{simulator,mavlink,attacks,features,detectors,fusion,integrity,
logging}` — see `docs/ARCHITECTURE.md`.)

## 5. Attack scenarios
Each maps 1:1 to an `AttackType` and to a detectable signature
(`docs/ATTACKS.md`): GPS spoofing shifts position while velocity stays truthful
(→ position residual); telemetry manipulation biases one channel but not its
cross-check (→ GPS/baro, GPS/VFR, attitude/course, battery); MAVLink anomaly
injects rogue sysids / rate spikes / sequence scrambles; command injection emits
COMMAND_LONG from an unauthorised GCS id; DoS floods, blacks out, or delays
frames; firmware tampering flips a byte, breaking the SHA-256 manifest.

## 6. Detection methodology
*(Diagram: [`diagrams/detection-flow.mmd`](diagrams/detection-flow.mmd).)*

Four detectors (`docs/DETECTION.md`): (A) a stateless **protocol/rule engine**;
(B) a **cyber-physical consistency** detector that cross-checks coupled channels;
(C) a benign-trained **ML anomaly** ensemble (Isolation Forest + diagonal
Mahalanobis, the latter covering Isolation Forest's inability to extrapolate
past its training range); (D) a **firmware integrity** verifier. Fusion uses a
**noisy-OR with max-normalised weights**, so a single high-trust detector (or a
firmware failure) can raise a threat while corroboration boosts confidence and a
lone weak ML signal stays below threshold. Every alert carries the concatenated
evidence from all firing detectors — no black-box decisions.

## 7. Feature engineering
Eleven policy-free, benign-stable features across network, navigation,
sensor-consistency, and command groups (`docs/FEATURES.md`). The signature
cyber-physical feature is a **bounded sliding-window position residual** — the
divergence between the reported position track and the track implied by reported
velocity — which detects sub-GPS-noise gradual drift yet recovers within ~3 s
after an attack stops (avoiding a long detector tail).

## 8. Dataset generation & ML
The anomaly model is trained **only on benign flights**, varied across route,
speed, altitude, sensor-noise scale, and seed, and split **by session** (whole
flights, never rows) into train/val/test to prevent leakage
(`docs/ML_PIPELINE.md`). Benchmark noise seeds are disjoint from training seeds (the
baseline's kinematics are fixed — 3 trajectories; benchmark v2 adds diversity). The
saved bundle records the scaler, model, feature schema, calibration statistics,
and `sklearn` version. Benign held-out alarm rate ≈ 0.2 %.

## 9. Logging
Alerts are persisted to SQLite with a **per-run SHA-256 hash chain**
(`docs/EVENT_LOGGING.md`): `hash = SHA-256(prev_hash ‖ canonical(event))`. Any
edit, insertion, or deletion breaks the chain, which `verify_chain` detects —
giving the forensic record the integrity an incident investigation requires.

## 10. Integration
The IDS ingests standard MAVLink 2 and is transport-agnostic: the Stage-1 PoC
uses an in-process source for determinism, and the codec/decoder are the genuine
wire format a real UDP link would carry. Swapping `SimulatedTelemetrySource` for
a real MAVLink UDP source is the single integration point
(`docs/diagrams/deployment.mmd`).

## 11. Compute platform
Pure-Python, CPU-only, no GPU. Steady-state cost is one lightweight decision
every 200 ms; peak process memory ~158 MB. This comfortably targets a companion
computer (e.g. Raspberry Pi / Jetson class) for future on-vehicle deployment.

## 12. Benchmarking
![Per-attack recall](figures/per_attack_recall.png)
![Confusion matrix](figures/confusion_matrix.png)

Grid: benign + six attacks × 6 seeds, routes cycled → 42 sessions, 23,430 scored
decisions. Methodology (warmup exclusion, disclosed post-attack recovery grace,
train/test isolation) is in `docs/BENCHMARKING.md`.

## 13. Validation
Detectors read only observed messages; ground-truth labels are used solely to
score. A 44-test suite (unit/integration/e2e/API) exercises every subsystem and
the full vertical slice including hash-chain verification. FPR is corroborated on
benign-only sessions.

## 14. Results
![Threat timeline](figures/threat_timeline.png)

| Metric | Value |
|---|---|
| Accuracy / Precision / Recall | 0.997 / 0.999 / 0.990 |
| **False-positive rate** | **0.0002** (4 / 16,830 benign decisions) |
| F1 | 0.995 |
| Per-attack recall | GPS 0.95 · MAVLink 1.0 · Command 1.0 · Telemetry 1.0 · DoS 1.0 · Firmware 0.99 |
| Detection latency (mean / p95) | 0.36 s / 1.40 s |
| Compute latency (mean / p95) | 17.7 ms / 23.6 ms |
| Throughput | 388 msg/s (14× real-time) |
| Memory | ≤ 158 MB |

![Latency](figures/latency.png) ![Resources](figures/resource_usage.png)

## 15. Limitations
A constant, fully-consistent GPS offset is detectable only at the transition
(sustained drift and replay-freeze are detected throughout). The GPS position
residual leaves a ~3 s post-attack tail (disclosed and scored transparently).
Results characterise a *simulated* link, not real-RF field conditions. Isolation
Forest alone is weak on out-of-range spikes (mitigated by the Mahalanobis
ensemble). Single-node SQLite logging.

## 16. Future work / deployment path
Replace the simulated source with a real MAVLink UDP link and validate against
ArduPilot/PX4 SITL, then hardware-in-the-loop on a companion computer; add
MAVLink 2 message signing verification, multi-vehicle support, per-airframe model
calibration, and a hardened deployment. None of these are claimed as implemented.

## 17. References
See `docs/REFERENCES.md` (MAVLink, pymavlink, ArduPilot, scikit-learn Isolation
Forest, GPS-spoofing and UAV-IDS literature).
