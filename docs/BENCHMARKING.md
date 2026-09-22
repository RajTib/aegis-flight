# AegisFlight — Benchmarking

**Every number in this repository's docs comes from `scripts/benchmark.py`.**
Nothing is hand-written. Re-run it to reproduce.

## How to run
```bash
aegis train                      # (once) train the anomaly model
aegis benchmark                  # -> artifacts/benchmarks/ + artifacts/figures/
# equivalently:
python scripts/benchmark.py --seeds 1 2 3 4 5 6
python scripts/benchmark.py --no-model      # rule+physics only (ML off)
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
- **Train/test isolation:** benchmark seeds (1–6) are disjoint from ML training
  seeds (100+), so the model is evaluated on unseen flights.

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
| Throughput | 388 msg/s (14× real-time; ~9,000 msg/s with ML off) |
| Mean distance / flight | 1,146 m |
| Memory (RSS) mean / max | 155 / 158 MB |

Figures: `artifacts/figures/{confusion_matrix,per_attack_recall,fpr,latency,resource_usage,threat_timeline}.png`.

## Interpreting the numbers
- **GPS recall 0.954** is the detection-latency cost: the sliding-window residual
  takes ~1.4 s to cross threshold at onset; the missed decisions are those first
  ticks, not steady-state misses.
- **FPR 0.0002** — four false decisions across ~17k benign, from transient
  turn/climb dynamics; none escalate to sustained alerts.
- **CPU ~99% during the benchmark** reflects running flat-out (unpaced). In
  real-time operation the meaningful figure is the **per-decision latency**
  (17.7 ms mean at 5 Hz ≈ 9 % duty cycle), not benchmark CPU saturation.
- **Compute cost is dominated by ML inference** (Isolation Forest
  `score_samples`); with `--no-model` the pipeline is ~0.4 ms/decision.

## Caveats
- Metrics are on a *simulated* MAVLink link; they characterise the detection
  logic, not real-RF field performance.
- Absolute recall depends on attack magnitudes in `configs/attacks.yaml`; weaker
  attacks lower recall and raise latency (re-run to measure).
