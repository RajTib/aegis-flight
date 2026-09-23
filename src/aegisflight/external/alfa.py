"""ALFA (AirLab Failure and Anomaly) dataset -- CMU AirLab, CC BY 4.0.

Keipour, Mousaei & Scherer, "ALFA: A dataset for UAV fault and anomaly
detection", IJRR 40(2-3), 2021. DOI 10.1184/R1/12707963.v1.

Real autonomous flights of a Carbon Z T-28 fixed-wing UAV (Pixhawk, modified
ArduPilot 3.9.0beta1). We use the published *telemetry* archive (MAVLink
``.tlog`` files recorded at the ground station) so the AegisFlight pipeline can
replay a genuine MAVLink link. These are **fault** (engine / control-surface)
flights plus no-failure flights -- not cyber attacks.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

FIGSHARE_ARTICLE = "https://api.figshare.com/v2/articles/12707963"
FILES = {
    "README.txt": "https://ndownloader.figshare.com/files/24098639",
    "telemetry.zip": "https://ndownloader.figshare.com/files/24098393",
    "processed.zip": "https://ndownloader.figshare.com/files/24095870",
}
# The figshare record lists CC BY 4.0; the bundled README.txt says CC0. We
# cite the authors either way and do not redistribute the raw files.
LICENSE = "CC BY 4.0 (figshare record); README.txt states CC0"
CITATION = (
    "A. Keipour, M. Mousaei, S. Scherer. ALFA: A dataset for UAV fault and anomaly "
    "detection. The International Journal of Robotics Research 40(2-3):515-520, 2021. "
    "Data: https://doi.org/10.1184/R1/12707963.v1 (CC BY 4.0)"
)


# --------------------------------------------------------------------------- #
# ground-truth index (from the authors' processed sequences)
# --------------------------------------------------------------------------- #

@dataclass
class AlfaSequence:
    name: str
    kind: str  # "no_failure" | "fault" | "no_ground_truth"
    fault: str  # e.g. "engine_failure" ("" for no_failure)
    t_start: float  # UNIX seconds
    t_end: float
    t_onset: float | None  # first failure_status == 1 (UNIX s), faults only


def _first_last_time(path: Path) -> tuple[float, float]:
    with path.open(newline="") as fh:
        r = csv.reader(fh)
        next(r)
        first = next(r)
        last = first
        for last in r:  # noqa: B007 - we only need the final row
            pass
    return int(first[0]) / 1e9, int(last[0]) / 1e9


def _onset(path: Path) -> float | None:
    with path.open(newline="") as fh:
        r = csv.reader(fh)
        next(r)
        for row in r:
            if row and float(row[-1]) >= 1:
                return int(row[0]) / 1e9
    return None


def index_sequences(processed_root: str | Path) -> list[AlfaSequence]:
    """Index the 47 processed sequences: window + fault onset from failure_status."""
    root = Path(processed_root)
    seqs: list[AlfaSequence] = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        name = d.name
        gp = d / f"{name}-mavros-global_position-global.csv"
        if not gp.exists():
            continue
        t0, t1 = _first_last_time(gp)
        suffix = name.split("_", 2)[-1] if name.count("_") >= 2 else name
        if "no_ground_truth" in name:
            kind, fault, onset = "no_ground_truth", "", None
        elif "no_failure" in name:
            kind, fault, onset = "no_failure", "", None
        else:
            fs = sorted(d.glob(f"{name}-failure_status-*.csv"))
            onsets = [o for o in (_onset(f) for f in fs) if o is not None]
            kind = "fault"
            fault = suffix
            onset = min(onsets) if onsets else None
        seqs.append(AlfaSequence(name, kind, fault, t0, t1, onset))
    return seqs


def label_at(seqs: list[AlfaSequence], t_unix: float) -> str:
    """Ground-truth category of one instant: benign_gt | fault | unlabelled."""
    for s in seqs:
        if not (s.t_start <= t_unix <= s.t_end):
            continue
        if s.kind == "no_failure":
            return "benign_gt"
        if s.kind == "fault" and s.t_onset is not None:
            return "fault" if t_unix >= s.t_onset else "benign_gt"
    return "unlabelled"


def dedup_overlapping_recordings(flights: list[dict]) -> tuple[list[dict], int]:
    """ALFA ships overlapping GCS recordings of the same flight; count each instant once.

    ``flights`` are dicts with a ``rows`` list whose items carry ``t_unix`` (and ``seg``,
    the clock-continuous segment index, default 0). Recordings
    are taken largest-first; a decision is dropped if its timestamp lies inside the
    time span already covered by a previously kept recording. Returns
    ``(flights_with_filtered_rows, n_dropped)``.
    """
    kept: list[tuple[float, float]] = []
    out, dropped = [], 0
    for f in sorted(flights, key=lambda f: -len(f["rows"])):
        rows = [r for r in f["rows"] if not any(a <= r["t_unix"] <= b for a, b in kept)]
        dropped += len(f["rows"]) - len(rows)
        # one interval per clock-continuous segment (a recording can span a clock jump)
        by_seg: dict[int, list[float]] = {}
        for r in rows:
            by_seg.setdefault(int(r.get("seg", 0)), []).append(r["t_unix"])
        kept.extend((min(v), max(v)) for v in by_seg.values())
        out.append({**f, "rows": rows})
    return out, dropped
