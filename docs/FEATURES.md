# AegisFlight — Feature Catalogue

The `FeatureExtractor` (`features/extractor.py`) consumes decoded
`MessageEnvelope`s (`update(msg)`), reconstructs an observed `TelemetrySnapshot`,
and emits a `FeatureFrame` at each decision tick (`extract(t)`). It is
**policy-free**: it computes physical quantities and raw aggregates; detectors
apply thresholds and the "expected source" policy.

## Feature groups

### Network / transport
| Feature | Unit | Meaning / calculation | Used by |
|---|---|---|---|
| `msg_rate_hz` | msg/s | messages in the last `rate_window_s` (1 s) | protocol, ML |
| `interarrival_mean_ms` / `interarrival_jitter_ms` | ms | mean / std of inter-arrival in the window | protocol, ML |
| `max_seq_gap` | count | largest per-source sequence jump this decision window | protocol, ML |
| `n_sources` | count | distinct (sysid,compid) seen this window | protocol |
| `sources` | map | (sysid,compid) → count (rogue-source detection) | protocol |
| `heartbeat_age_s` / `gps_age_s` | s | time since last HEARTBEAT / GLOBAL_POSITION_INT | protocol |
| `loss_ratio` | 0–1 | `min(1, max_seq_gap/50)` loss estimate | protocol, ML |
| `signed_ratio` | 0–1 | fraction of signed messages | protocol |

### Navigation / cyber-physical
| Feature | Unit | Meaning / calculation | Used by |
|---|---|---|---|
| `pos_residual_m` | m | **bounded sliding-window sum** of (measured displacement − velocity·dt); the signature GPS-spoofing signal | physics, ML |
| `gps_vfr_speed_diff_ms` | m/s | `|hypot(vx,vy) − VFR groundspeed|` | physics, ML |
| `gps_baro_alt_diff_m` | m | `|GPS altitude − baro altitude|` (independent channels) | physics, ML |
| `alt_rate_ms` | m/s | baro-altitude derivative (decision cadence) | physics, ML |
| `accel_ms2` / `jerk_ms3` | m/s²,³ | horizontal accel/jerk from velocity history | physics, ML |
| `battery_v_rate` / `battery_v_rise` | V/s | battery-voltage derivative / upward part | physics (**not** ML*) |
| `yaw_course_diff_deg` | ° | `|attitude yaw − course-over-ground|` (frozen-attitude signal) | physics, ML |

\* `battery_v_rate` is intentionally excluded from `ML_FEATURES`: it is ~0 in
steady flight (near-zero variance), so throttle transitions read as extreme
outliers and caused benign false positives. The physics detector's
transition-robust 0.4 V threshold covers battery attacks instead.

### Command
| Feature | Unit | Meaning | Used by |
|---|---|---|---|
| `cmd_rate_hz` | cmd/s | COMMAND_LONG rate in `cmd_window_s` (2 s) | protocol, ML |
| `commands_recent` | list | recent `CommandEvent`s (source, id, params) | protocol |

## The ML feature vector (`ML_FEATURES`, 11 dims)

`msg_rate_hz, interarrival_jitter_ms, max_seq_gap, pos_residual_m,
gps_vfr_speed_diff_ms, gps_baro_alt_diff_m, alt_rate_ms, accel_ms2,
yaw_course_diff_deg, cmd_rate_hz, loss_ratio`

`FeatureFrame.to_vector()` returns them in this exact order. **The saved model
depends on this order and content** — changing `ML_FEATURES` requires retraining
(`aegis train`).

## Windows, warmup, state

- **Position residual:** `_RESID_WINDOW` = 15 position fixes (~3 s), per-fix
  increment magnitude-clamped to 30 m so a single position snap-back cannot
  dominate. Bounded window ⇒ recovers ~3 s after an attack stops (no long
  detector tail) while still accumulating sub-noise gradual drift.
- **Rate window:** 1 s sliding (`_recv_times` deque). **Command window:** 2 s.
- **Per-decision reset:** `clear_window_counts()` resets per-window source
  counts and sequence-gap maxima (the pipeline calls it after each `extract`).
  Persistent state (`_seq_state`, residual increments, histories) is *not*
  reset.
- **Warmup:** benchmark/training exclude the first `warmup_s` (5 s); the ML
  detector also has a `warmup_ticks` (20) grace before it scores.
- **Missing values:** `TelemetrySnapshot` fields start `None`; features guard
  against `None` (treated as 0 / skipped) until the first message of each type.

## False-positive conditions (known)
- Sharp turns momentarily raise `yaw_course_diff` and `accel` (damped by physics
  hysteresis; small ML z-scores because turns are common in benign training).
- Throttle transitions perturb `battery_v_rate` (excluded from ML for exactly
  this reason).
- A GPS spoof leaves a ~3 s elevated `pos_residual` after it stops (the position
  snap-back is genuinely anomalous); handled by the benchmark's grace window and
  documented in `docs/BENCHMARKING.md`.
