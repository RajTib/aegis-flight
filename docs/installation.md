# AegisFlight — Installation

See `docs/QUICKSTART.md` for the full first-run walkthrough; this is the concise
install reference (a Stage-1 official deliverable).

## Requirements
- Python **≥ 3.11** (tested on 3.13), pip, venv.
- Node **≥ 18** + npm — *only* for the dashboard. The IDS, CLI, benchmark, and
  tests run without Node.
- OS: Windows, Linux, or macOS. No GPU. No network access required after deps
  are installed.

## Python package + CLI

**Windows (PowerShell)**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

**Linux / macOS**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Installs the runtime deps (numpy, pandas, scipy, scikit-learn, pymavlink, psutil,
pyyaml, pydantic, fastapi, uvicorn, websockets, matplotlib) and dev tools
(pytest, ruff, mypy, httpx), and puts the `aegis` command on PATH.

Verify:
```bash
aegis version
python -c "import aegisflight, pymavlink; print('ok')"
pytest tests/unit -q
```

## Anomaly model
```bash
aegis train           # -> models/isoforest.joblib  (~15 s; optional)
```

## Dashboard (frontend)
```bash
npm --prefix frontend install
npm --prefix frontend run build      # -> frontend/dist (served by the backend)
```

## Run
```bash
aegis serve                          # http://127.0.0.1:8000
# or, no UI:
aegis simulate --attack gps_spoofing
aegis benchmark
python scripts/run_demo.py
```

## Notes
- Editable install (`-e`) uses the src-layout in `pyproject.toml`.
- If `aegis` isn't found, activate the venv or use `python -m aegisflight.cli`.
- Windows consoles: the CLI forces UTF-8 output so unicode evidence prints
  correctly.
- Troubleshooting: `docs/TROUBLESHOOTING.md`.
