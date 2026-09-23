"""External (non-simulated) data: provenance, adapters and validation.

Everything in this package is **analysis-only**. It never feeds the production
training pipeline (``benchmark/dataset.py`` / ``scripts/train_models.py``) and
never touches the synthetic benchmark splits. See ``docs/EXTERNAL_DATA.md``.
"""
