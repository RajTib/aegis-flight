"""Telemetry sources that feed the IDS (in-process simulated; UDP for demo)."""

from .stream import SimulatedTelemetrySource, TelemetryTick

__all__ = ["SimulatedTelemetrySource", "TelemetryTick"]
