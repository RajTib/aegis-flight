# AegisFlight — Development Guide

## Environment
```bash
python -m venv .venv && .venv/Scripts/activate   # or source .venv/bin/activate
pip install -e ".[dev]"
```
Python ≥ 3.11. Deps are pinned as floors in `pyproject.toml`.

## Conventions
- **Style/lint:** `ruff` (line length 100; rules `E,F,I,W,UP,B,C4`; see
  `[tool.ruff]` in `pyproject.toml`). Run `ruff check src tests scripts backend`
  and `ruff check --fix`. Keep it clean — CI-equivalent gate.
- **Types:** `from __future__ import annotations` everywhere; modern generics
  (`list[...]`, `X | None`). `mypy` config present (`[tool.mypy]`).
- **Docstrings:** module-level docstring explaining *why* the module exists and
  its contract; match the surrounding density.
- **Hot path uses plain dataclasses**, not Pydantic (Pydantic only at the API
  boundary if needed).

## Architectural boundaries (enforced by convention — see `CODEBASE_MAP.md`)
1. `core/` imports nothing from the package.
2. Detectors read only a `FeatureFrame` (+ integrity verifier for D4); never the
   simulator/attacks/ground-truth.
3. Ground truth (`FlightState`, attack `label`) is benchmark-only.
4. Attack↔IDS interaction happens only through the wire (`MessageEnvelope`) and
   the firmware directory.
5. `pipeline.py` is the single place that wires detectors + fusion.

## Where to add things
| Task | Where | Then |
|---|---|---|
| New attack | `attacks/scenarios.py` + registry | `docs/ADDING_A_NEW_ATTACK.md` |
| New detector | `detectors/` + pipeline + fusion weight | `docs/ADDING_A_NEW_DETECTOR.md` |
| New feature | `features/extractor.py` (+ `ML_FEATURES` → retrain) | `docs/FEATURES.md` |
| New route | `simulator/flight.py:_route_waypoints` | — |
| New threshold | `configs/detector.yaml` | `docs/CONFIGURATION.md` |
| New API route | `backend/app.py` | `docs/API.md` |

## Testing expectations
Add/extend tests for any behaviour change; keep `pytest` green and `ruff` clean.
Unit tests should be fast and deterministic (use seeds + `tmp_path`). Re-run
`aegis benchmark` if you touch detectors/features/simulator and update the
numbers in `docs/BENCHMARKING.md`, `README.md`, `docs/technical_proposal.md`.

## Dependency management
Runtime deps in `[project.dependencies]`, dev tools in
`[project.optional-dependencies].dev`. Prefer stdlib; the frontend deliberately
uses no chart/UI library.

## Generated artifacts policy
- **Commit:** `artifacts/benchmarks/*` and `artifacts/figures/*` (competition
  evidence, regenerable via `aegis benchmark`).
- **Do not commit (gitignored):** `models/*.joblib` (regenerate via
  `aegis train`), `*.sqlite`, `frontend/dist/`, `node_modules/`, caches, venv.

## Git & documentation discipline
Small, logical commits; end messages with the `Co-Authored-By` trailer. **Keep
docs in sync with code:** changing the API → `API.md`; a detector → `DETECTION.md`;
features → `FEATURES.md`; an attack → `ATTACKS.md`; benchmark → `BENCHMARKING.md`;
config → `CONFIGURATION.md`; modules → `FILE_REFERENCE.md`. Never claim a feature
is implemented unless the code works and a test/benchmark backs it.
