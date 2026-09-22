# Adding a New Detector

Worked example: a `link_quality` detector.

### 1. Know the interface
`detectors/base.py`:
```python
class Detector:
    name: DetectorName
    def process(self, frame: FeatureFrame) -> DetectorResult: ...
    def reset(self) -> None: ...            # optional per-session state reset
```
`DetectorResult` fields: `detector` (a `DetectorName`), `score` ∈ [0,1],
`triggered`, `evidence: list[str]`, `attack_votes: dict[AttackType, float]`,
`signals: dict[str, float]`. Use the `ramp(x, lo, hi)` helper for smooth
sub-scores.

### 2. (If new) add a `DetectorName`
`core/enums.py`:
```python
class DetectorName(str, Enum):
    ...
    LINK_QUALITY = "link_quality"
```

### 3. Implement it
`detectors/link_quality.py`:
```python
class LinkQualityDetector(Detector):
    name = DetectorName.LINK_QUALITY
    def __init__(self, cfg): self.jitter_max = float(cfg.get("jitter_max_ms", 120))
    def process(self, frame):
        s = ramp(frame.interarrival_jitter_ms, self.jitter_max, self.jitter_max*2)
        ev = [f"link jitter {frame.interarrival_jitter_ms:.0f} ms"] if s > 0.5 else []
        return DetectorResult(self.name, s, s > 0.5, ev,
                              {AttackType.DOS: s} if s else {}, {})
```
Consume only the `FeatureFrame` (add a feature to `features/extractor.py` first
if you need a new signal). Don't touch the simulator, attacks, or ground truth.

### 4. Wire it into the pipeline
`pipeline.py`: construct it in `IDSPipeline.__init__`, call it in
`process_tick`, and pass its result into `fusion.fuse([...])`.

### 5. Give it a fusion weight
`fusion/engine.py` `_WEIGHT_KEYS` maps `DetectorName → weight key`; add
`DetectorName.LINK_QUALITY: "link_quality"` and add
`link_quality: <w>` under `detector.fusion.weights` in `configs/detector.yaml`.
Weights are max-normalised, so the value expresses *relative trust*.

### 6. Understand the impact on scoring
- **threat score** rises via noisy-OR when your detector corroborates others.
- A **lone** detector triggers only if `score · (w/max_w) ≥ threat_threshold`
  (0.45) — size its weight/score accordingly.
- Set `attack_votes` so the fused `attack_type` attributes correctly.

### 7. Tests + benchmark + docs
Add a unit test (mirror `tests/unit/test_fusion_and_metrics.py`), re-run
`aegis benchmark` to confirm FPR didn't regress, and update `docs/DETECTION.md`.
