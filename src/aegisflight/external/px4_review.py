"""PX4 Flight Review (review.px4.io) public-log selection.

Flight Review publishes metadata for every *public* uploaded log at
``/dbinfo``. We apply a fixed, pre-registered selection protocol so the sample
is reproducible and not cherry-picked:

* ``mav_type == "Quadrotor"`` (closest to the simulated airframe)
* real hardware only: ``sys_hw`` present and not containing ``SITL``
  (HITL is rejected later from the log's ``SYS_HITL`` parameter)
* uploader ``rating`` in {good, great, BRAVO!} and no ``error_labels``
  (proxy for a nominal / benign flight -- *not* ground truth, see docs)
* EKF2 estimator, log year 2024-2026, duration 120-1800 s
* deterministic ``random.Random(seed).sample`` over the log_id-sorted list

Nothing here asserts that a flight is attack-free; public uploads are treated
as *presumed benign* and every exclusion is recorded.
"""

from __future__ import annotations

import gzip
import json
import random
import urllib.request
from pathlib import Path

from .provenance import USER_AGENT

DBINFO_URL = "https://review.px4.io/dbinfo"
DOWNLOAD_URL = "https://review.px4.io/download?log={log_id}"

SELECTION_V1 = {
    "name": "v1_rated",
    "mav_type": "Quadrotor",
    "ratings": ["good", "great", "BRAVO!"],
    "min_duration_s": 120,
    "max_duration_s": 1800,
    "years": ["2024", "2025", "2026"],
    "estimator": "EKF2",
    "exclude_hw_substrings": ["SITL"],
}

# v1 (uploader-rated logs only) was run first and turned out to be 38/40 HITL
# flights from a single uploader -- the rating filter selected a tiny, biased
# pool. v2 drops the rating requirement, removes HITL/SIH airframes at selection
# time, requires zero logged errors and caps the sample at one log per vehicle.
SELECTION_V2 = {
    "name": "v2_unrated_one_per_vehicle",
    "mav_type": "Quadrotor",
    "exclude_ratings": ["crash_sw_hw", "crash_pilot", "unsatisfactory"],
    "max_logged_errors": 0,
    "min_duration_s": 120,
    "max_duration_s": 1800,
    "years": ["2024", "2025", "2026"],
    "estimator": "EKF2",
    "exclude_hw_substrings": ["SITL"],
    "exclude_airframe_substrings": ["HIL", "SIH", "Sim"],
    "exclude_autostart_ids": [1001, 1002, 1100, 1101, 1102, 1103],
    "one_per_vehicle_uuid": True,
}
SELECTION = SELECTION_V2
PROTOCOLS = {"v1": SELECTION_V1, "v2": SELECTION_V2}


def fetch_dbinfo(dest: str | Path) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(DBINFO_URL, headers={"User-Agent": USER_AGENT,
                                                     "Accept-Encoding": "gzip"})
    raw = urllib.request.urlopen(req, timeout=300).read()
    try:
        raw = gzip.decompress(raw)
    except OSError:
        pass
    dest.write_bytes(raw)
    return dest


def eligible(entry: dict, sel: dict = SELECTION) -> bool:
    hw = entry.get("sys_hw") or ""
    if not hw or any(s in hw for s in sel["exclude_hw_substrings"]):
        return False
    if entry.get("mav_type") != sel["mav_type"]:
        return False
    if entry.get("error_labels"):
        return False
    if "ratings" in sel and entry.get("rating") not in sel["ratings"]:
        return False
    if entry.get("rating") in sel.get("exclude_ratings", []):
        return False
    if "max_logged_errors" in sel and (entry.get("num_logged_errors") or 0) > sel["max_logged_errors"]:
        return False
    airframe = entry.get("airframe_name") or ""
    if any(s in airframe for s in sel.get("exclude_airframe_substrings", [])):
        return False
    if entry.get("sys_autostart_id") in sel.get("exclude_autostart_ids", []):
        return False
    if entry.get("estimator") != sel["estimator"]:
        return False
    dur = entry.get("duration_s") or 0
    if not (sel["min_duration_s"] <= dur <= sel["max_duration_s"]):
        return False
    return (entry.get("log_date") or "")[:4] in sel["years"]


def select_logs(dbinfo: list[dict], n: int, seed: int, sel: dict = SELECTION) -> tuple[list[dict], int]:
    """Return (deterministic sample of ``n`` eligible entries, number eligible).

    With ``one_per_vehicle_uuid`` the pool keeps only the first (by log_id) log
    of each non-empty ``vehicle_uuid`` so one prolific uploader cannot dominate.
    """
    cand = sorted((e for e in dbinfo if eligible(e, sel)), key=lambda e: e["log_id"])
    if sel.get("one_per_vehicle_uuid"):
        seen: set[str] = set()
        uniq = []
        for e in cand:
            v = e.get("vehicle_uuid") or ""
            if v and v in seen:
                continue
            if v:
                seen.add(v)
            uniq.append(e)
        cand = uniq
    k = min(n, len(cand))
    return random.Random(seed).sample(cand, k), len(cand)


def load_dbinfo(path: str | Path) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
