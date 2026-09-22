# AegisFlight — References

## Protocol & platforms
- **MAVLink 2** message/protocol specification — https://mavlink.io/
- **pymavlink** (the reference Python MAVLink implementation used here) —
  https://github.com/ArduPilot/pymavlink
- **ArduPilot** (message semantics, flight modes, SITL for future work) —
  https://ardupilot.org/ ; **PX4** — https://px4.io/
- MAVLink 2 **message signing** (future work) —
  https://mavlink.io/en/guide/message_signing.html

## Tools & libraries
- **scikit-learn** `IsolationForest` (Liu, Ting & Zhou, "Isolation Forest",
  ICDM 2008) — https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html
- **FastAPI** — https://fastapi.tiangolo.com/ ; **Uvicorn** —
  https://www.uvicorn.org/
- **NumPy**, **pandas**, **SciPy**, **matplotlib**, **psutil**, **joblib**,
  **PyYAML** (see `pyproject.toml` for versions)
- **Vite** + **React** + **TypeScript** (dashboard)

## Background (UAV / GNSS security)
- GNSS/GPS spoofing detection via kinematic/cyber-physical consistency
  (position–velocity, altitude cross-checks) — the principle behind
  `PhysicsDetector`.
- Anomaly-based intrusion detection for MAVLink/UAV telemetry — the motivation
  for the benign-trained ML layer.
- Firmware attestation via cryptographic hashing (SHA-256 manifests) — the basis
  of `FirmwareVerifier`.

## Competition
- **PUSHPAK Grand Challenge 2026-27**, IIT Bombay Techfest — Security of Drones,
  Objective 2 (Drone Intrusion Detection System). Stage-1 deliverables: technical
  proposal, software architecture, working PoC simulation, source code,
  installation instructions, demonstration video.

*Note:* URLs are provided for orientation; this PoC depends only on the pinned
Python/Node packages in `pyproject.toml` / `frontend/package.json` and needs no
network access to build, test, or run.
