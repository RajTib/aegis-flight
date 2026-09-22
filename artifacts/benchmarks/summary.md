# AegisFlight — Benchmark Summary

_Generated from 23430 scored decisions across 6 seeds × 7 scenarios. Model used: True._

## Binary detection (attack vs benign)

| Metric | Value |
|---|---|
| Accuracy | 0.997 |
| Precision | 1.000 |
| Recall (TPR) | 0.989 |
| False-positive rate | 0.000 |
| F1 | 0.995 |
| TP / FP / TN / FN | 6529 / 0 / 16830 / 71 |

## Per-attack detection

| Attack | Precision | Recall | F1 | Support | Detection latency (s) |
|---|---|---|---|---|---|
| GPS_SPOOFING | 1.000 | 0.948 | 0.973 | 900 | 1.47 |
| MAVLINK_ANOMALY | 1.000 | 1.000 | 1.000 | 900 | 0.00 |
| COMMAND_INJECTION | 1.000 | 1.000 | 1.000 | 600 | 0.00 |
| TELEMETRY_MANIPULATION | 1.000 | 1.000 | 1.000 | 900 | 0.00 |
| DOS | 1.000 | 1.000 | 1.000 | 600 | 0.00 |
| FIRMWARE_INTEGRITY | 1.000 | 0.991 | 0.996 | 2700 | 0.80 |

## Latency, throughput & resources

| Metric | Value |
|---|---|
| Detection latency mean / p95 (s) | 0.378 / 1.600 |
| Compute latency mean / p95 (ms) | 13.553 / 17.569 |
| Throughput (messages/s) | 509.0 |
| Mean distance / flight (m) | 1145.8 |
| CPU mean / max (%) | 99.21 / 99.9 |
| RSS mean / max (MB) | 155.46 / 159.48 |

_All figures produced by `python scripts/benchmark.py`; see `results.json`._