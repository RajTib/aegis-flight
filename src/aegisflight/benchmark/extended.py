"""Extended synthetic benchmark (v2) -- *in addition to* the baseline benchmark.

The baseline (``harness.py``) is left untouched and remains the reference
result. This module addresses its documented weaknesses without hiding hard
cases:

* **trajectory diversity** -- every session draws its own kinematics seed,
  route, cruise speed (8-16 m/s), altitude (35-90 m) and sensor-noise scale
  (0.7-1.6x); ranges deliberately extend beyond the ML training ranges
  (9-15 m/s, 40-80 m, 0.8-1.4x). Seeds are disjoint from training (101-124),
  the baseline (kinematics 42) and the external sim reference (9001+).
* **every implemented attack mode** (20 modes incl. the two new ones,
  ``dos:gnss_jamming`` and the known-gap ``command_injection:gcs_replay``)
  with randomised onset (25-55 s) and duration (15-30 s);
* **both scoring policies** from one run: the baseline's 5 s post-attack grace
  and **no grace**; plus metrics **excluding firmware** (41 % of the baseline's
  positives);
* **no duplicated benign decisions** -- each session has its own trajectory;
* **simultaneous attacks** (multi-label ground truth) and a **benign link
  impairment** stress condition.

Nothing is tuned against these results; thresholds and the model are the
production ones.
"""

from __future__ import annotations

import copy
import csv
import gzip
import json
import platform
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from ..config import AegisConfig, load_config
from ..core.enums import AttackType
from ..metrics.scoring import evaluate
from .runner import run_session

MODES: dict[str, list[str]] = {
    "gps_spoofing": ["gradual_drift", "sudden_offset", "replay_freeze"],
    "mavlink_anomaly": ["rogue_sysid", "rate_spike", "seq_scramble", "packet_loss"],
    "command_injection": ["rogue_command", "mode_flip", "arm_disarm_burst", "gcs_replay"],
    "telemetry_manipulation": ["altitude_bias", "speed_mismatch", "battery_jump", "frozen_attitude"],
    "dos": ["flood", "blackout", "latency", "gnss_jamming"],
    "firmware_integrity": ["default"],
}
# (combination, onset offset of the 2nd component in seconds)
COMBOS: list[tuple[str, float]] = [
    ("gps_spoofing+mavlink_anomaly", 0.0),
    ("gps_spoofing+command_injection", 5.0),
    ("dos+telemetry_manipulation", 5.0),
    ("telemetry_manipulation+firmware_integrity", 10.0),
]
KNOWN_GAP_MODES = {"command_injection:gcs_replay"}
LINK_STRESS = {
    "link_fifo_benign": {"mean_delay_ms": 25.0, "loss_prob": 0.02, "fifo": True},
    "link_reorder_benign": {"mean_delay_ms": 25.0, "loss_prob": 0.02, "fifo": False},
}
ROUTES = ("survey_box", "out_and_back", "perimeter")


@dataclass
class SessionSpec:
    idx: int
    kind: str  # benign | single | combo | link_fifo_benign | link_reorder_benign
    scenario: str  # attack name(s) for build_attack, or "benign"
    mode: str  # "gradual_drift", "a/b" for combos, "" for benign
    seed: int
    route: str
    speed: float
    alt: float
    noise_scale: float
    onset: float = 0.0
    duration: float = 0.0
    offset2: float = 0.0
    link: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.scenario}:{self.mode}" if self.mode else self.scenario


def build_grid(seeds_per_mode: int = 4, n_benign: int = 12, combo_seeds: int = 3,
               n_link: int = 6, master_seed: int = 20260923) -> list[SessionSpec]:
    rng = np.random.default_rng(master_seed)
    specs: list[SessionSpec] = []

    def base(kind, scenario, mode, **kw):
        i = len(specs)
        specs.append(SessionSpec(
            idx=i, kind=kind, scenario=scenario, mode=mode, seed=30000 + i,
            route=ROUTES[i % 3], speed=float(rng.uniform(8, 16)), alt=float(rng.uniform(35, 90)),
            noise_scale=float(rng.uniform(0.7, 1.6)),
            onset=float(rng.uniform(25, 55)), duration=float(rng.uniform(15, 30)), **kw))

    for _ in range(n_benign):
        base("benign", "benign", "")
    for atk, modes in MODES.items():
        for m in modes:
            for _ in range(seeds_per_mode):
                base("single", atk, m)
    for combo, off in COMBOS:
        for _ in range(combo_seeds):
            base("combo", combo, "", offset2=off)
    for kind, link in LINK_STRESS.items():
        for _ in range(n_link):
            base(kind, "benign", "", link=dict(link))
    return specs


def session_config(base_cfg: AegisConfig, s: SessionSpec) -> AegisConfig:
    cfg = copy.deepcopy(base_cfg)
    sim = cfg.simulation
    sim.update(route=s.route, cruise_speed_ms=s.speed, cruise_alt_m=s.alt, seed=s.seed)
    sim["noise"] = {k: v * s.noise_scale for k, v in sim.get("noise", {}).items()}
    if s.link:
        sim["link"] = dict(s.link)
    parts = s.scenario.split("+") if s.scenario != "benign" else []
    for j, name in enumerate(parts):
        a = cfg.attacks.setdefault(name, {})
        a["start_s"] = s.onset + (s.offset2 if j > 0 else 0.0)
        if name != "firmware_integrity":
            a["duration_s"] = s.duration
        if s.kind == "single" and s.mode and s.mode != "default":
            a["mode"] = s.mode
    return cfg


def _run_one(args: tuple[dict, str | None]) -> dict:
    spec_d, model_path = args
    s = SessionSpec(**spec_d)
    cfg = session_config(load_config(), s)
    res = run_session(cfg, s.scenario, seed=s.seed, model_path=model_path, grace_s=5.0)
    recs = [{"t": round(r.t, 2), "true": r.true_label.value, "true_set": "|".join(r.true_set),
             "pred": r.pred_label.value, "secondary": "|".join(r.pred_secondary),
             "threat": int(r.threat), "in_grace": int(r.in_grace), "warm": int(r.t < 5.0)}
            for r in res.records]
    return {"spec": asdict(s), "key": s.key, "records": recs,
            "time_to_detect_s": res.time_to_detect_s,
            "compute_ms_mean": float(np.mean(res.compute_latency_ms)),
            "compute_ms_p95": float(np.percentile(res.compute_latency_ms, 95)),
            "n_messages": res.n_messages, "wall_s": res.wall_time_s}


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #

def _scored(recs: list[dict], grace: bool) -> list[dict]:
    return [r for r in recs if not r["warm"] and not (grace and r["in_grace"])]


def _binary(recs: list[dict]) -> dict:
    ev = evaluate([AttackType(r["true"]) for r in recs], [AttackType(r["pred"]) for r in recs])
    b = ev.binary
    return {"n": len(recs), "tp": b.tp, "fp": b.fp, "tn": b.tn, "fn": b.fn,
            "accuracy": b.accuracy, "precision": b.precision, "recall": b.recall,
            "fpr": b.fpr, "f1": b.f1}


def _session_events(sess: dict) -> dict:
    recs = sess["records"]
    inwin = [r for r in recs if r["true"] != "BENIGN"]
    detected = any(r["threat"] for r in inwin)
    end_t = max((r["t"] for r in inwin), default=None)
    tail = None
    if end_t is not None:
        after = [r["t"] - end_t for r in recs if end_t < r["t"] <= end_t + 30 and r["threat"]]
        tail = max(after) if after else 0.0
    correct = [r["pred"] == r["true"] for r in inwin if r["threat"]]
    return {"detected": detected, "ttd": sess["time_to_detect_s"], "alarm_tail_s": tail,
            "attribution_acc": (sum(correct) / len(correct)) if correct else None}


def summarise(sessions: list[dict]) -> dict:
    single = [s for s in sessions if s["spec"]["kind"] in ("benign", "single")]
    out: dict = {"n_sessions": len(sessions)}
    for name, grace in (("grace5", True), ("grace0", False)):
        recs = [r for s in single for r in _scored(s["records"], grace)]
        nofw = [r for s in single if s["spec"]["scenario"] != "firmware_integrity"
                for r in _scored(s["records"], grace)]
        nogap = [r for s in single if s["key"] not in KNOWN_GAP_MODES
                 for r in _scored(s["records"], grace)]
        out[f"binary_{name}"] = _binary(recs)
        out[f"binary_{name}_excl_firmware"] = _binary(nofw)
        out[f"binary_{name}_excl_known_gap"] = _binary(nogap)
        ev = evaluate([AttackType(r["true"]) for r in recs], [AttackType(r["pred"]) for r in recs])
        out[f"confusion_{name}"] = ev.to_dict()["confusion_matrix"]
    per_mode: dict[str, dict] = {}
    for s in single:
        if s["spec"]["kind"] != "single":
            continue
        pm = per_mode.setdefault(s["key"], {"sessions": 0, "detected": 0, "ttd": [], "tail": [],
                                            "attr": [], "pos": 0, "tp": 0})
        ev = _session_events(s)
        pm["sessions"] += 1
        pm["detected"] += int(ev["detected"])
        if ev["ttd"] is not None:
            pm["ttd"].append(ev["ttd"])
        if ev["alarm_tail_s"] is not None:
            pm["tail"].append(ev["alarm_tail_s"])
        if ev["attribution_acc"] is not None:
            pm["attr"].append(ev["attribution_acc"])
        sc = [r for r in _scored(s["records"], True) if r["true"] != "BENIGN"]
        pm["pos"] += len(sc)
        pm["tp"] += sum(r["pred"] != "BENIGN" for r in sc)
    out["per_mode"] = {
        k: {"sessions": v["sessions"], "sessions_detected": v["detected"],
            "decision_recall": v["tp"] / v["pos"] if v["pos"] else None,
            "median_ttd_s": float(np.median(v["ttd"])) if v["ttd"] else None,
            "max_ttd_s": float(np.max(v["ttd"])) if v["ttd"] else None,
            "median_alarm_tail_s": float(np.median(v["tail"])) if v["tail"] else None,
            "attribution_accuracy": float(np.mean(v["attr"])) if v["attr"] else None,
            "known_gap": k in KNOWN_GAP_MODES}
        for k, v in sorted(per_mode.items())}
    for kind in ("benign", *LINK_STRESS):
        ss = [s for s in sessions if s["spec"]["kind"] == kind]
        recs = [r for s in ss for r in _scored(s["records"], True)]
        out[kind] = {"sessions": len(ss),
                     "decisions": len(recs),
                     "false_positive_decisions": sum(r["pred"] != "BENIGN" for r in recs),
                     "fpr": (sum(r["pred"] != "BENIGN" for r in recs) / len(recs)) if recs else None,
                     "sessions_with_any_fp": sum(any(r["pred"] != "BENIGN" for r in
                                                     _scored(s["records"], True)) for s in ss),
                     "fp_classes": _count(r["pred"] for r in recs if r["pred"] != "BENIGN")}
    combos: dict[str, dict] = {}
    for s in sessions:
        if s["spec"]["kind"] != "combo":
            continue
        c = combos.setdefault(s["key"], {"sessions": 0, "decisions": 0, "detected": 0,
                                         "primary_in_truth": 0, "all_covered": 0,
                                         "multi_label_decisions": 0, "multi_all_covered": 0})
        c["sessions"] += 1
        for r in _scored(s["records"], True):
            truth = set(filter(None, r["true_set"].split("|")))
            if not truth:
                continue
            pred = {r["pred"]} | set(filter(None, r["secondary"].split("|"))) if r["threat"] else set()
            c["decisions"] += 1
            c["detected"] += int(bool(r["threat"]))
            c["primary_in_truth"] += int(r["pred"] in truth)
            c["all_covered"] += int(truth <= pred)
            if len(truth) > 1:
                c["multi_label_decisions"] += 1
                c["multi_all_covered"] += int(truth <= pred)
    out["combos"] = {k: {**v,
                         "binary_recall": v["detected"] / v["decisions"] if v["decisions"] else None,
                         "primary_in_truth_rate": v["primary_in_truth"] / v["decisions"] if v["decisions"] else None,
                         "full_coverage_when_both_active": (v["multi_all_covered"] / v["multi_label_decisions"])
                         if v["multi_label_decisions"] else None}
                     for k, v in combos.items()}
    lat = [s["compute_ms_mean"] for s in sessions]
    out["compute_ms_mean_of_sessions"] = float(np.mean(lat))
    out["compute_ms_p95_max"] = float(np.max([s["compute_ms_p95"] for s in sessions]))
    return out


def _count(it) -> dict:
    d: dict = {}
    for x in it:
        d[x] = d.get(x, 0) + 1
    return d


def run_extended(out_dir: str | Path = "artifacts/benchmarks_extended",
                 model_path: str | None = "models/isoforest.joblib", workers: int = 4,
                 **grid_kw) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if model_path and not Path(model_path).exists():
        model_path = None
    specs = build_grid(**grid_kw)
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        sessions = list(ex.map(_run_one, [(asdict(s), model_path) for s in specs]))
    result = summarise(sessions)
    result["config"] = {"grid": dict(grid_kw) or "defaults",
                        "modes": MODES, "combos": COMBOS, "link_stress": LINK_STRESS,
                        "known_gap_modes": sorted(KNOWN_GAP_MODES), "model_used": bool(model_path),
                        "python": platform.python_version(), "workers": workers,
                        "wall_time_s": round(time.perf_counter() - t0, 1)}
    (out / "results.json").write_text(json.dumps(result, indent=2, default=_json), encoding="utf-8")
    with (out / "sessions.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["idx", "kind", "key", "seed", "route", "speed", "alt", "noise_scale", "onset",
                    "duration", "offset2", "detected", "ttd_s", "alarm_tail_s", "fp_decisions"])
        for s in sessions:
            sp, ev = s["spec"], _session_events(s)
            fp = sum(r["pred"] != "BENIGN" for r in _scored(s["records"], True) if r["true"] == "BENIGN")
            w.writerow([sp["idx"], sp["kind"], s["key"], sp["seed"], sp["route"], round(sp["speed"], 2),
                        round(sp["alt"], 1), round(sp["noise_scale"], 3), round(sp["onset"], 1),
                        round(sp["duration"], 1), sp["offset2"], ev["detected"], ev["ttd"],
                        ev["alarm_tail_s"], fp])
    with gzip.open(out / "decisions.csv.gz", "wt", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["session", "key", "t", "true", "true_set", "pred", "secondary", "threat",
                    "in_grace", "warmup"])
        for s in sessions:
            for r in s["records"]:
                w.writerow([s["spec"]["idx"], s["key"], r["t"], r["true"], r["true_set"], r["pred"],
                            r["secondary"], r["threat"], r["in_grace"], r["warm"]])
    return result


def _json(x):
    if isinstance(x, float | np.floating):
        return float(x)
    raise TypeError(type(x))
