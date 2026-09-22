# AegisFlight — Attack Implementation

All attacks live in `src/aegisflight/attacks/` and are **safe local
simulations**. See `docs/THREAT_MODEL.md` for the conceptual catalogue; this doc
is the implementation reference.

## The `Attack` interface (`attacks/base.py`)

```python
class Attack:
    attack_type: AttackType
    def active(self, t) -> bool                      # inside [start_s, start_s+duration_s)
    def label(self, t) -> AttackType                 # ground truth (benchmark only)
    def window(self) -> tuple[float, float]
    # perturbation hooks (default = identity):
    def before_encode(self, t, tick, encoder)        # tamper encoder state (seq)
    def perturb_state(self, t, state) -> FlightState # value attacks (pre-encode)
    def perturb_packets(self, t, packets, ctx) -> list[RawPacket]  # stream attacks
    def integrity_status(self, t) -> IntegrityStatus # firmware
```

`AttackContext` gives `perturb_packets` the current `tick`, the `MavlinkEncoder`
(to synthesise frames), a seeded `rng`, and the clean `state` (for
impersonation). `NoAttack` is the benign case.

`build_attack(name, attacks_cfg, rng, **kwargs)` (in `attacks/__init__.py`) reads
the per-attack block from `configs/attacks.yaml` and instantiates the class from
`ATTACK_REGISTRY`.

## Per-attack detail

| Attack | Class | Hook | Modes (config `mode`) | Changes | Leaves truthful |
|---|---|---|---|---|---|
| GPS spoofing | `GpsSpoofingAttack` | `perturb_state` | `gradual_drift`*, `sudden_offset`, `replay_freeze` | lat/lon | velocity (→ residual) |
| Telemetry manip. | `TelemetryManipulationAttack` | `perturb_state` | `altitude_bias`*, `speed_mismatch`, `battery_jump`, `frozen_attitude` | one reported channel | the cross-check channel |
| MAVLink anomaly | `MavlinkAnomalyAttack` | `perturb_packets` / `before_encode` | `rogue_sysid`*, `rate_spike`, `seq_scramble`, `packet_loss` | the frame stream | payload values |
| Command injection | `CommandInjectionAttack` | `perturb_packets` | `rogue_command`*, `mode_flip`, `arm_disarm_burst` | injects COMMAND_LONG from rogue id | vehicle telemetry |
| DoS | `DosAttack` | `perturb_packets` | `flood`*, `blackout`, `latency` | duplicates/drops/delays frames | payload values |
| Firmware | `FirmwareIntegrityAttack` | `integrity_status` | (n/a; open-ended from `start_s`) | flips a byte in a component file | the manifest |

\* = default mode in `configs/attacks.yaml`.

Notes:
- **GPS `gradual_drift`** injects `drift_rate_ms · elapsed` metres along
  `bearing_deg`; **`replay_freeze`** pins lat/lon at attack onset.
- **Telemetry `altitude_bias`** biases GPS/EKF altitude but not the baro channel
  → `gps_baro_alt_diff`. **`frozen_attitude`** freezes yaw while the course
  keeps turning → `yaw_course_diff`.
- **MAVLink `rogue_sysid`** uses `encoder.encode_as(state, rogue_sysid, …)` to
  emit vehicle-like telemetry from a rogue node. **`seq_scramble`** jumps the
  encoder's per-source seq counter in `before_encode` (frames stay CRC-valid but
  sequence-anomalous).
- **DoS `flood`** replays the tick's frames ×`flood_multiplier`; the duplicated
  seq stream also inflates `max_seq_gap`.
- **Firmware** shares its firmware directory with the pipeline's
  `FirmwareVerifier`; at `start_s` it flips a byte in `tamper_component` and the
  verifier's next `verify()` returns INVALID (genuine SHA-256).

## Adding a new attack
See `docs/ADDING_A_NEW_ATTACK.md`.
