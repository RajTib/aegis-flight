# Stage-1 report ↔ repository alignment

Purpose: make sure every statement in the official Stage-1 report is backed by a file in
this repository, and that the report never claims more than the evidence supports.
Numbers are **never** typed here — each row points at the generated artifact to quote.

## Section map

| Report section | Write from | Evidence to cite | Must say |
|---|---|---|---|
| 1. Executive summary | `README.md`, `docs/VALIDATION_EVIDENCE.md` | `artifacts/validation/validation_table.md` (Overall) | "simulation-based Stage-1 PoC"; accuracy is of the **fused IDS** on the **simulated** benchmark; real-flight replays measured false alarms, not attack detection |
| 2. Understanding of the problem | `docs/THREAT_MODEL.md`, `docs/ATTACKS.md` (coverage by category) | — | the six challenge classes + category mapping (communication, navigation, telemetry, command & control, firmware, system) |
| 3. Proposed IDS architecture | `docs/ARCHITECTURE.md`, `docs/DETECTION.md`, `docs/FEATURES.md`, `docs/ML_PIPELINE.md` | `docs/diagrams/*.mmd` | 4 detectors + noisy-OR fusion; ML = Isolation Forest + **diagonal** Mahalanobis, benign-only; firmware manifest **unsigned** in PoC |
| 4. Platform integration & interoperability | `docs/EXTERNAL_DATA.md` §2, `src/aegisflight/external/` | `artifacts/external/alfa/summary.md`, `artifacts/external/alfa_calibrated/summary.md` | the pipeline **ingests real MAVLink `.tlog` and PX4 ULog** via adapters without core changes; production thresholds need **per-vehicle calibration**; real PX4/ArduPilot telemetry makes some physics cross-checks degenerate (use GPS_RAW_INT / SCALED_PRESSURE on a real vehicle) |
| 5. Validation & testing methodology | `docs/BENCHMARKING.md`, `docs/EXTERNAL_DATA.md` §3, `docs/TESTING.md` | `artifacts/benchmarks/summary.md`, `artifacts/benchmarks_ablation_no_ml/summary.md`, `artifacts/benchmarks_extended/summary.md`, `artifacts/external/*/summary.md`, `artifacts/validation/validation_table.md` | baseline **and** v2 (no-grace, excl. firmware); ML-off ablation; known gaps (`gcs_replay`, constant-offset spoofing) |
| 6. Development plan | `docs/VALIDATION_EVIDENCE.md` (future work), `docs/HANDOFF.md` | — | real attack data (UAV Attack Dataset / SITL+HackRF lab), per-vehicle baselining, raw-sensor cross-checks, MAVLink-2 signing, signed firmware manifest |

## Specifically requested items

| Requirement | Where it is answered |
|---|---|
| Feature extraction & dataset strategy | `docs/FEATURES.md`, `docs/ML_PIPELINE.md`, `docs/dataset_strategy.md`, `docs/EXTERNAL_DATA.md` §2 (feature compatibility A/B/C/D) |
| Attack scenario coverage | `docs/ATTACKS.md` (modes, categories, composites), v2 per-mode table |
| Test evidence / datasets | synthetic: benchmark + v2 (`decisions.csv.gz`); real: manifests in `data/external/manifests/` (URL, SHA-256) + `artifacts/external/` |
| Ground truth | simulated: attack time window from `Attack.label(t)` / `labels(t)` (multi-label for composites), never visible to detectors; ALFA: authors' `failure_status` onset; PX4: *presumed* benign (no labels) |
| Repeatability | fixed seeds; `scripts/benchmark.py`, `scripts/benchmark_extended.py`, `scripts/fetch_external_data.py` (SHA-256 manifests), `scripts/external_validation.py`, `scripts/make_validation_table.py`; baseline re-run bit-identical |
| Accuracy / completeness | validation table + per-mode recall + known-gap rows (report them, do not drop them) |
| Performance metrics | compute latency & throughput in each `summary.md` |
| Validation table TC-01 … TC-06 | `artifacts/validation/validation_table.md` (TC numbering assumed = one TC per challenge attack class; adapt to the official template if it differs) |

## Language to avoid (see `docs/VALIDATION_EVIDENCE.md` for the full audit)

"99.7 % ML accuracy" · "real-world detection accuracy" · "deployed" / "field-tested" ·
"signed firmware manifest" · "robust Mahalanobis" · "evaluated on unseen flights" ·
"detects all command injection" (replay from the legitimate GCS id is not detected) ·
"detects GPS spoofing" without the constant-offset caveat.
