# AegisFlight — Benchmarking

**Every number in this repository's docs comes from `scripts/benchmark.py`.**
Nothing is hand-written. Re-run it to reproduce.

## How to run
```bash
aegis train                      # (once) train the anomaly model
aegis benchmark                  # -> artifacts/benchmarks/ + artifacts/figures/
# equivalently:
python scripts/benchmark.py --seeds 1 2 3 4 5 6
python scripts/benchmark.py --no-model --no-figures --out artifacts/benchmarks_ablation_no_ml
                                             # rule+physics+firmware only (ML off)
python scripts/benchmark_extended.py --workers 8   # extended benchmark v2 (see below)
```
Outputs (in `artifacts/`): `benchmarks/results.json` (authoritative),
`benchmarks/results.csv` (per-session), `benchmarks/summary.md`, and six figures
in `figures/`.

## Methodology
- **Grid:** benign + the six attacks × 6 seeds, routes cycled
  (survey_box/out_and_back/perimeter) → 42 sessions, 23,430 **scored** decisions.
- **Scoring cadence:** one label per decision tick (5 Hz). `true_label` from the
  attack's ground-truth window; `pred_label` = fused `attack_type` if `threat`
  else BENIGN.
- **Warmup:** first 5 s of each session excluded (extractor/ML warmup).
- **Post-attack recovery grace:** benign ticks within `grace_s` (5 s) *after* an
  attack window are excluded from FP scoring. This is disclosed, not hidden — a
  GPS spoof leaves a ~3 s elevated position residual after it stops (the position
  snap-back is genuinely anomalous). FPR is reported on this policy **and** the
  benign-only sessions independently confirm it.
- **Train/test isolation (precise wording):** the benchmark's seeds (1–6) drive
  the *sensor-noise* and attack RNGs and are disjoint from the ML training seeds
  (101–124). The baseline's flight *kinematics*, however, use one fixed simulator
  seed (42) with cruise 12 m/s / 60 m, so the 42 sessions contain only **three
  distinct ground-truth trajectories** (one per route) and the pre-attack part of
  every attack session repeats a benign session's flight. "Unseen noise
  realisations", not "unseen flights". The extended benchmark v2 fixes this.

## Metrics (definitions)
- **Binary** (attack = positive): accuracy, precision `TP/(TP+FP)`, recall/TPR
  `TP/(TP+FN)`, FPR `FP/(FP+TN)`, F1.
- **Per-attack:** one-vs-rest precision/recall/F1 (did we name the right class?).
- **Confusion matrix:** 7×7 over `AttackType`.
- **Detection latency (s):** per attack session, time from onset to first
  in-window detection.
- **Compute latency (ms):** wall time of the per-decision detector+fusion work.
- **Throughput (msg/s):** MAVLink messages processed per wall second.
- **Resources:** process CPU% and RSS (psutil).

## Authoritative results (6 seeds × 7 scenarios, 23,430 scored decisions)

| Metric | Value |
|---|---|
| Accuracy | 0.997 |
| Precision | 0.999 |
| Recall (TPR) | 0.990 |
| False-positive rate | **0.0002** (4 FP / 16,830 benign) |
| F1 | 0.995 |
| TP / FP / TN / FN | 6535 / 4 / 16826 / 65 |

| Attack | Precision | Recall | F1 | Detection latency (s) |
|---|---|---|---|---|
| GPS spoofing | 1.000 | 0.954 | 0.977 | 1.37 |
| MAVLink anomaly | 1.000 | 1.000 | 1.000 | 0.00 |
| Command injection | 1.000 | 1.000 | 1.000 | 0.00 |
| Telemetry manipulation | 0.996 | 1.000 | 0.998 | 0.00 |
| DoS | 1.000 | 1.000 | 1.000 | 0.00 |
| Firmware integrity | 1.000 | 0.991 | 0.996 | 0.80 |

| Efficiency | Value |
|---|---|
| Detection latency mean / p95 | 0.361 s / 1.400 s |
| Compute latency mean / p95 | 17.7 ms / 23.6 ms (≪ 200 ms decision budget) |
| Throughput | 388 msg/s (14× real-time) — ML-off figure: see `artifacts/benchmarks_ablation_no_ml/summary.md` |
| Mean distance / flight | 1,146 m |
| Memory (RSS) mean / max | 155 / 158 MB |

Figures: `artifacts/figures/{confusion_matrix,per_attack_recall,fpr,latency,resource_usage,threat_timeline}.png`.

## ML-off ablation (same grid)
`python scripts/benchmark.py --no-model --no-figures --out artifacts/benchmarks_ablation_no_ml`
→ [`artifacts/benchmarks_ablation_no_ml/summary.md`](../artifacts/benchmarks_ablation_no_ml/summary.md).
Compare it with the table above to see what the ML layer contributes: on this grid it
adds GPS-onset and telemetry decisions and is the only source of false positives.
The headline 0.997 is therefore a **fused-IDS** figure, not an ML figure.

## Extended benchmark v2 (does not replace the baseline)
`python scripts/benchmark_extended.py --workers 8` →
[`artifacts/benchmarks_extended/summary.md`](../artifacts/benchmarks_extended/summary.md)
(+ `results.json`, `sessions.csv`, `decisions.csv.gz`). Design (`benchmark/extended.py`):

| Weakness of the baseline | v2 treatment |
|---|---|
| 3 underlying trajectories (fixed kinematics seed 42, 12 m/s, 60 m) | every session: own kinematics seed (30000+), route, speed 8–16 m/s, altitude 35–90 m, noise ×0.7–1.6 — deliberately wider than the ML training ranges |
| one default mode per attack | all 20 implemented modes × 4 sessions, randomised onset 25–55 s, duration 15–30 s |
| 5 s post-attack grace | reported **with and without** grace from the same run |
| duplicated benign decisions (pre-attack segments replay benign flights) | no duplication — each session is a distinct flight |
| firmware = 41 % of positives | metrics also reported **excluding firmware** |
| clean synthetic link timing | benign **link-impairment stress**: 2 % loss + 25 ms mean delay, FIFO (serial radio) and reordering (UDP) variants |
| single attacks only | 4 simultaneous-attack combinations with multi-label ground truth |
| — | two new modes: `dos:gnss_jamming`, `command_injection:gcs_replay` (known gap) |

Nothing is tuned against v2: production thresholds and the committed model are used.
After adding v2 the baseline grid was re-run and reproduced **bit-identically**
(same TP/FP/TN/FN, confusion matrix, per-attack metrics and latencies).

## Interpreting the numbers
- **GPS recall 0.954** is the detection-latency cost: the sliding-window residual
  takes ~1.4 s to cross threshold at onset; the missed decisions are those first
  ticks, not steady-state misses.
- **FPR 0.0002** — four false decisions across ~17k benign, from transient
  turn dynamics; none escalate to sustained alerts. The ML-off ablation has zero
  false positives, i.e. every baseline FP involves the ML detector (a lone ML score
  ≥ 0.956 crosses the fusion threshold on its own). Because every attack session's
  pre-attack segment replays a benign session's flight, the ~17k benign decisions
  are far fewer *independent* observations (v2 removes this duplication).
- **CPU ~99% during the benchmark** reflects running flat-out (unpaced). In
  real-time operation the meaningful figure is the **per-decision latency**
  (17.7 ms mean at 5 Hz ≈ 9 % duty cycle), not benchmark CPU saturation.
- **Compute cost is dominated by ML inference** (Isolation Forest
  `score_samples`); for the ML-off cost see the generated ablation summary.
  **Bug fixed (2026-09):** before this fix `--no-model` / `model_path=None` silently
  loaded `models/isoforest.joblib` whenever it existed, so earlier "ML off" figures
  may not have been ML-off. The ablation above is regenerated with the fix.

## Caveats
- Metrics are on a *simulated* MAVLink link; they characterise the detection
  logic, not real-RF field performance. The external real-flight replays
  (`docs/EXTERNAL_DATA.md`) show that the production thresholds do **not**
  transfer to a real link without per-vehicle calibration.
- The 5 s grace is applied after **every** attack type, not only GPS; v2 reports
  the no-grace numbers so the effect is visible.
- Absolute recall depends on attack magnitudes in `configs/attacks.yaml`; weaker
  attacks lower recall and raise latency (re-run to measure).
