# AegisFlight — convenience targets. On Windows, run the underlying commands
# directly (see docs/QUICKSTART.md) or use `make` via Git Bash / WSL.
.PHONY: install train benchmark test lint demo serve frontend clean

install:          ## install python package + dev tools (+ frontend deps)
	pip install -e ".[dev]"
	cd frontend && npm install

train:            ## train the anomaly model -> models/isoforest.joblib
	python scripts/train_models.py

benchmark:        ## run the benchmark grid -> artifacts/
	python scripts/benchmark.py

test:             ## run the full test suite
	pytest

lint:             ## ruff lint
	ruff check src tests scripts backend

frontend:         ## build the dashboard -> frontend/dist
	cd frontend && npm run build

demo:             ## narrated headless demo of all six scenarios
	python scripts/run_demo.py

serve: frontend   ## build UI then start the live dashboard on :8000
	aegis serve

clean:            ## remove generated (regenerable) artifacts
	rm -f models/*.joblib *.sqlite artifacts/aegisflight_live.sqlite
	rm -rf frontend/dist .pytest_cache
