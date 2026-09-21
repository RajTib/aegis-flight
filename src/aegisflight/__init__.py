"""AegisFlight - Hybrid Real-Time Intrusion Detection System for UAV Cyber-Physical Security.

A modular, explainable IDS for UAV/drone telemetry that combines:
  * protocol/rule-based detection,
  * cyber-physical (flight-state) consistency checks,
  * lightweight statistical / ML anomaly detection (Isolation Forest),
  * firmware-integrity verification,
via an evidence-fusion engine that produces explainable, severity-ranked alerts.

This is a Stage-1 proof-of-concept. All attacks are safe, local simulations.
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
