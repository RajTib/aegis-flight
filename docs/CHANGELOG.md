# AegisFlight — Changelog

Milestones derived from the actual git history (`git log`). AegisFlight was
**recovered after a mid-build crash** of an earlier autonomous session that left
only the foundation; everything from the simulator onward was implemented during
continuation. See `docs/RECOVERY_AUDIT.md`.

## Recovery & continuation (single development arc)

- **`cb16dcd` — recovery baseline.** Preserved the interrupted foundation
  verbatim (config system, `core/` types/enums/geo, dir skeleton, venv) as the
  committed recovery point before any changes.
- **`bced0a3` — recovery docs.** Forensic audit, failures log, continuation
  priority (`docs/RECOVERY_*.md`).
- **`8d53191` — simulator.** Deterministic coordinated-turn flight model
  (`simulator/flight.py`, the crash point) — takeoff→route→RTL→landing, 3 routes.
- **`c1de76e` — MAVLink codec.** Genuine pymavlink v2 encode/decode with sensor
  noise; per-source sequence counters; 28 msg/s nominal verified.
- **`00864f2` — attacks + integrity + source.** Six safe local attack scenarios,
  SHA-256 firmware verifier, `SimulatedTelemetrySource` orchestration.
- **`b7349da` — feature extraction.** Online extractor; bounded sliding-window
  position residual; verified feature separation benign vs attack.
- **`6f0044c` — detection + fusion + pipeline.** Four detectors, noisy-OR fusion,
  `IDSPipeline`; all six attacks detected end-to-end (pre-ML).
- **`c711e71` — logging + metrics + runner.** SQLite hash-chain event store,
  scoring/metrics, session runner; switched the position residual to a bounded
  window (GPS recovery tail 23 s → 3 s).
- **`d6af995` — ML anomaly detector.** IsolationForest + Mahalanobis ensemble,
  benign-only session-split training (`scripts/train_models.py`).
- **`763eb92` — benchmark + CLI + evidence.** Multi-seed harness, six figures,
  `aegis` CLI; committed benchmark results as evidence.
- **`9f52ea2` — backend.** FastAPI REST + WebSocket live engine with runtime
  attack injection; fixed hash chaining to be per-run.
- **`3b9d268` — dashboard + tests.** React/Vite dashboard; 44-test suite
  (unit/integration/e2e/API), all passing.
- **`248b1b1` — ML feature fix + docs.** Removed the benign-FP-prone
  `battery_v_rate` ML feature (retrained); final benchmark acc 0.997 / recall
  0.99 / FPR 0.0002; full documentation package.

## Final Stage-1 status
Working PoC: simulator → MAVLink → six attacks → four detectors → fusion →
tamper-evident logging → REST/WebSocket → dashboard, with a reproducible
benchmark and a 44-test suite. See `docs/HANDOFF.md` for status detail.

## External validation & benchmark v2 (2026-09-24)
- **External real-flight data (analysis only):** provenance-tracked download of PX4
  Flight Review public logs (selection protocol v1 → failed, 38/40 HITL; v2 → one log per
  vehicle) and the ALFA dataset (real ArduPilot MAVLink `.tlog`s). ULog and tlog adapters;
  `scripts/external_validation.py` (E1 navigation replay, E2 full-pipeline replay, E2b
  per-vehicle link calibration on held-out dates). No retraining. `docs/EXTERNAL_DATA.md`.
- **Extended benchmark v2** (`scripts/benchmark_extended.py`): per-session trajectory
  seeds/speed/altitude/noise, all 20 attack modes, grace 5 s *and* 0 s, excl.-firmware
  metrics, simultaneous attacks (`CompositeAttack`, multi-label ground truth), benign
  link-impairment stress (FIFO and reordering). Baseline benchmark untouched and
  re-verified bit-identical after the changes.
- **New attack variants:** `dos:gnss_jamming` (+ protocol rule *GNSS fix lost*),
  `command_injection:gcs_replay` (documented known gap).
- **Bug fix:** `model_path=None` / `--no-model` now really disables ML (it previously
  loaded `models/isoforest.joblib` if present). ML-off ablation regenerated.
- **Docs honesty pass:** unsigned manifest, diagonal (not robust) Mahalanobis, "unseen
  noise realisations" not "unseen flights", lone-ML threat behaviour, missing
  `tune_thresholds.py`, unimplemented baro bias correction.
