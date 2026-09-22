"""FastAPI backend: live sim+IDS engine, REST API, and telemetry WebSocket."""

from .engine import LiveEngine

__all__ = ["LiveEngine"]
