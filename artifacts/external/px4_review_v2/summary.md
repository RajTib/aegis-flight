# E1 — PX4 Flight Review real flights: navigation replay (generated)

_Source manifest: `data/external/manifests/px4_review_v2.json` · public logs listed: 468513 · eligible under the selection protocol: 11974 · downloaded: 40 (seed 2026, protocol `v2`)._

Network features (msg rate, jitter, sequence gaps, loss, command rate) are **not available** from an on-board ULog and are excluded. The ML column is a *navigation probe*: network features held at their benign training mean (z = 0) — it is **not** an ML validation.

## Exclusions (whole log)

- none

## Airborne alarm / exceedance rates (production thresholds, no tuning)

| Metric | Sim reference | Real: `px4_telemetry` | Real: `independent_sensors` | Real: `independent_sensors_biascorr` |
|---|---|---|---|---|
| Usable flights | 12 | 24 | 26 | 26 |
| Airborne hours | 0.35 | 2.18 | 2.36 | 2.36 |
| physics_trigger_rate | 0.00 % (flights: 0) | 5.51 % (flights: 16) | 93.42 % (flights: 26) | 28.56 % (flights: 20) |
| ml_probe_alarm_rate | 0.30 % (flights: 9) | 7.90 % (flights: 17) | 94.65 % (flights: 26) | 34.91 % (flights: 22) |
| ml_probe_lone_threat_rate | 0.08 % (flights: 4) | 7.53 % (flights: 17) | 89.58 % (flights: 26) | 21.80 % (flights: 22) |
| exceed_pos_residual_m | 0.00 % (flights: 0) | 0.15 % (flights: 2) | 0.03 % (flights: 1) | 0.03 % (flights: 1) |
| exceed_gps_vfr_speed_diff_ms | 0.00 % (flights: 0) | 0.00 % (flights: 0) | 5.66 % (flights: 3) | 5.66 % (flights: 3) |
| exceed_gps_baro_alt_diff_m | 0.00 % (flights: 0) | 0.00 % (flights: 1) | 92.99 % (flights: 25) | 25.56 % (flights: 15) |
| exceed_alt_rate_ms | 0.05 % (flights: 3) | 0.01 % (flights: 3) | 0.43 % (flights: 6) | 0.43 % (flights: 6) |
| exceed_accel_ms2 | 0.00 % (flights: 0) | 0.00 % (flights: 1) | 0.01 % (flights: 2) | 0.01 % (flights: 2) |
| exceed_yaw_course_diff_deg | 0.00 % (flights: 0) | 48.01 % (flights: 16) | 50.14 % (flights: 18) | 50.14 % (flights: 18) |

## Feature distributions (airborne, pooled): p50 / p99

| Feature | Sim | `px4_telemetry` | `independent_sensors` | `independent_sensors_biascorr` | KS vs sim (px4_telemetry, independent_sensors, independent_sensors_biascorr) |
|---|---|---|---|---|---|
| pos_residual_m | 1.15 / 3.05 | 0.13 / 2.52 | 0.09 / 2.02 | 0.09 / 2.02 | 0.73, 0.75, 0.75 |
| gps_vfr_speed_diff_ms | 0.15 / 0.59 | 0.01 / 0.08 | 0.04 / 12.00 | 0.04 / 12.00 | 0.92, 0.40, 0.40 |
| gps_baro_alt_diff_m | 1.10 / 4.46 | 0.00 / 0.28 | 104.36 / 5458.78 | 3.33 / 57.76 | 0.91, 0.94, 0.46 |
| alt_rate_ms | -0.04 / 15.95 | -0.00 / 2.99 | 0.00 / 14.37 | 0.00 / 14.37 | 0.38, 0.21, 0.21 |
| accel_ms2 | 1.65 / 9.29 | 0.15 / 5.61 | 0.26 / 5.54 | 0.26 / 5.54 | 0.73, 0.65, 0.65 |
| yaw_course_diff_deg | 0.35 / 3.22 | 0.00 / 169.58 | 0.00 / 167.58 | 0.00 / 167.58 | 0.53, 0.54, 0.54 |
| ml_nav_probe | 0.04 / 0.36 | 0.07 / 1.00 | 1.00 / 1.00 | 0.12 / 1.00 | —, —, — |

_Thresholds: {"pos_residual_m": 12.0, "gps_vfr_speed_diff_ms": 5.0, "gps_baro_alt_diff_m": 8.0, "alt_rate_ms": 25.0, "accel_ms2": 20.0, "yaw_course_diff_deg": 25.0, "ml_score_threshold": 0.62, "ml_lone_threat_threshold": 0.9563}_
