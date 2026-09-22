# Adding a New Attack

Worked example: a hypothetical `geofence_breach` value-attack.

### 1. (If it's a new class) add the enum
`src/aegisflight/core/enums.py` → add to `AttackType`:
```python
GEOFENCE_BREACH = "GEOFENCE_BREACH"
```
Most new attacks are *variants* of the existing six — if so, reuse that
`AttackType` and skip this step.

### 2. Implement the attack class
`src/aegisflight/attacks/scenarios.py`:
```python
class GeofenceBreachAttack(Attack):
    attack_type = AttackType.GEOFENCE_BREACH

    def __init__(self, cfg, rng):
        super().__init__(cfg, rng)
        self.push_m = float(cfg.get("push_m", 200.0))

    def perturb_state(self, t, state):          # value attack
        if not self.active(t):
            return state
        lat, lon = offset_latlon(state.lat, state.lon, self.push_m, 0.0)
        return replace(state, lat=lat, lon=lon)
```
Pick the right hook: `perturb_state` (values), `perturb_packets` (stream, uses
`ctx.encoder`), `before_encode` (encoder state), or `integrity_status`
(firmware). See `docs/ATTACKS.md`.

### 3. Register it
`src/aegisflight/attacks/__init__.py` → add to `ATTACK_REGISTRY` (and
`TYPE_TO_KEY` if it's a new type).

### 4. Add config
`configs/attacks.yaml`:
```yaml
geofence_breach:
  mode: push_out
  start_s: 40.0
  duration_s: 30.0
  push_m: 200.0
```

### 5. Make sure a detector catches it (+ evidence)
Either an existing detector already fires (e.g. the physics `pos_residual` for a
positional attack — check!), or add a rule/feature. If you add a feature, put it
in `features/extractor.py`; if it should feed the ML detector, add it to
`ML_FEATURES` **and retrain** (`aegis train`). Ensure the firing detector votes
for the right `AttackType` and appends clear `evidence`.

### 6. Benchmark label
Nothing extra needed — the harness reads ground truth from `Attack.label(t)`.
Add the scenario name to `benchmark/harness.py:SCENARIOS` to include it in the
grid.

### 7. Dashboard (optional)
Add a button in `frontend/src/components/ControlPanel.tsx` `ATTACKS` list.

### 8. Tests + docs
Add a case to `tests/integration/test_pipeline.py::EXPECTED`, and update
`docs/ATTACKS.md` + `docs/THREAT_MODEL.md`.

### Verify
```bash
aegis simulate --attack geofence_breach        # inspect alerts + evidence
python -m pytest tests/integration -q
```
