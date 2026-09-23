# What AegisFlight has evidence for — and what it does not

This page is the honesty check for the report and the demo. Quote numbers only from the
generated files it links (`artifacts/**/summary.md`, `artifacts/validation/validation_table.md`).

## 1. Real evidence (measured on real, public flight data)

| Claim we can make | Evidence |
|---|---|
| The IDS pipeline ingests **genuine recorded MAVLink telemetry** (ground-station `.tlog`, real radio link timing, sequence numbers, source ids) and runs end-to-end unchanged, via an adapter only | ALFA replay, `artifacts/external/alfa/summary.md` |
| With the **production (simulator-calibrated) configuration**, the IDS raises an alarm on essentially every decision of a real link — the simulated false-positive rate does **not** transfer | same file: fused threat rate on author-labelled benign periods; top evidence = message-rate spike + ML |
| Root causes are identified and measured: the real ArduPilot link runs at several times the simulator's configured nominal message rate, so the rate rule fires and the ML network features (rate, jitter) fall far outside the simulated training range | `real_link_stats_airborne` in the same file vs `configs/detector.yaml` and the model's scaler |
| After a **documented one-parameter per-vehicle calibration** (nominal message rate from calibration dates only, ML off, test on held-out dates) the real-link alarm rate is reported separately | `artifacts/external/alfa_calibrated/summary.md` |
| The **physics layer** is comparatively quiet on real fixed-wing telemetry, and its behaviour on real multirotors is measured under three explicit channel mappings | ALFA summary (physics column); `artifacts/external/px4_review_v2/summary.md` |
| On real PX4 and ArduPilot telemetry, `GLOBAL_POSITION_INT` and `VFR_HUD` are **both estimator outputs**, so three physics cross-checks lose independence; the heading-vs-course rule does not hold for multirotors; GPS/baro needs a baro offset correction | PX4 source (cited in `external/ulog_adapter.py`), E1 exceedance table |
| The selection of "real" public logs must be verified: the first protocol (rated logs) yielded **0 real flights** (HITL from one uploader), caught automatically by the `SYS_HITL` check | `artifacts/external/px4_review_v1/summary.md` |

**Not claimed:** real *attack* detection. No public real-attack MAVLink data was downloadable
in this session (the UAV Attack Dataset requires an IEEE account). Real data here measures
**false alarms and fault reactions only**. ALFA faults are physical, not cyber.

## 2. Simulation-only evidence

| Claim | Evidence | Caveat |
|---|---|---|
| Baseline fused-IDS accuracy / recall / FPR on 23,430 simulated decisions | `artifacts/benchmarks/summary.md` | 3 trajectories, default modes, 5 s grace |
| What the ML layer adds on the same grid | `artifacts/benchmarks_ablation_no_ml/summary.md` | ML is the only FP source in the baseline |
| Detection across **all 20 attack modes**, diverse trajectories, no-grace scoring, excl. firmware | `artifacts/benchmarks_extended/summary.md` | simulated link and attacker |
| Simultaneous attacks (4 combinations, multi-label truth) | same file, *Simultaneous attacks* | the fusion reports one primary + secondary indicators; full multi-label attribution is partial |
| GNSS jamming detection (new fix-loss rule) | same file, `dos:gnss_jamming` | scored as DOS; trivially observable in simulation |
| Benign link impairment stress (loss, delay, reordering) | same file, *Benign sessions* | synthetic impairment model |
| Firmware tamper detection | SHA-256 manifest compare | manifest is **unsigned** in the PoC |

## 3. Known gaps (reported, not hidden)

* `command_injection:gcs_replay` — a replayed command from the legitimate GCS identity is
  **not detected** (no MAVLink-2 signing). It stays in the v2 benchmark as a known-gap row.
* `gps_spoofing:sudden_offset` — a constant, self-consistent offset is caught only at the
  jump (see v2 per-mode recall).
* Link-impairment stress shows the sequence/rate rules and ML network features are
  brittle to realistic loss and reordering.

## 4. Future work (not implemented)

1. Real attack validation: UAV Attack Dataset (live HackRF spoofing/jamming on a Pixhawk 4);
   own SITL/HITL + SDR lab.
2. Per-vehicle baselining of transport features (automated, not hand-set) and retraining the
   ML layer on **real benign telemetry with network features** (ALFA-style `.tlog`s), with
   flight-level splits — only now scientifically justified because real tlogs exist.
3. Raw-sensor cross-checks for real vehicles: `GPS_RAW_INT` vs EKF position/velocity,
   `SCALED_PRESSURE` vs EKF altitude, with causal bias removal.
4. MAVLink-2 message signing (fixes command replay), signed firmware manifest (Ed25519).
5. A separate fault class (ALFA shows physical faults and attacks overlap in feature space).
6. A dedicated GPS_JAMMING class in the enum / dashboard.

## 5. Overclaim audit (documentation language)

| Phrase | Where it was | Status |
|---|---|---|
| "signed firmware manifest" | `integrity/verifier.py`, `detectors/integrity.py`, `DETECTION.md`, `THREAT_MODEL.md`, `technical_proposal.md` | **fixed** → "SHA-256 manifest (unsigned in PoC)" |
| "Robust Mahalanobis" | `detectors/anomaly.py`, `DETECTION.md`, `ML_PIPELINE.md`, `technical_proposal.md` | **fixed** → "diagonal Mahalanobis (z-score norm)" |
| "99.7 % ML accuracy" | not found in docs | README now states explicitly it is the fused IDS on simulation |
| "evaluated on unseen flights" | `BENCHMARKING.md`, `ML_PIPELINE.md`, `harness.py`, `technical_proposal.md` | **fixed** → unseen *noise realisations* of 3 trajectories; v2 adds diversity |
| "keeps a lone weak ML signal below threshold" | `fusion/engine.py`, `DETECTION.md`, `technical_proposal.md` | **qualified**: a lone strong ML score crosses the threshold (source of baseline FPs) |
| "~9,000 msg/s / ~0.4 ms with ML off" | `BENCHMARKING.md` | **replaced** by the regenerated ablation (the `--no-model` flag did not disable ML before the fix) |
| "see scripts/tune_thresholds.py" | `configs/detector.yaml` | **fixed** — script never existed |
| "(bias-corrected)" GPS/baro | `configs/detector.yaml` | **fixed** — no correction is implemented |
| "benign residual ~4 m RMS" | `features/extractor.py` | **fixed** — replaced with a pointer to measured distributions |
| real-world deployment claims | `README.md`, `technical_proposal.md` | already scoped as future work; keep it that way |
