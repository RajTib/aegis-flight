#!/usr/bin/env python
"""External real-flight validation of AegisFlight (analysis only).

Usage:
    python scripts/fetch_external_data.py --alfa --px4 40      # once
    python scripts/external_validation.py --px4 --alfa [--workers 8]

Experiments (see docs/EXTERNAL_DATA.md):
  E1  PX4 Flight Review ULogs -> navigation replay under three channel
      mappings; production FeatureExtractor + PhysicsDetector; ML nav probe.
      Compared with simulated benign reference flights (fresh seeds).
  E2  ALFA real MAVLink .tlog files -> FULL IDSPipeline replay (unchanged).
      No-failure periods measure the real-link false-alarm rate; fault
      periods measure how the IDS reacts to real *faults* (not attacks).

Nothing is trained, tuned or re-thresholded. All numbers in the generated
summary.md files come from this script.
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import joblib
import numpy as np

from aegisflight.config import load_config
from aegisflight.external import realdata, ulog_adapter
from aegisflight.external.provenance import read_manifest
from aegisflight.features.extractor import ML_FEATURES as ML_FEATURES_ALL

MODEL = "models/isoforest.joblib"
MAPPINGS = ulog_adapter.MAPPINGS


# --------------------------------------------------------------------------- #
# E1: PX4 ULog navigation replay
# --------------------------------------------------------------------------- #

def _px4_one(path: str) -> dict:
    cfg = load_config()
    bundle = joblib.load(MODEL) if Path(MODEL).exists() else None
    out: dict = {"file": Path(path).name}
    try:
        fl = ulog_adapter.load_ulog(path)
    except Exception as e:  # noqa: BLE001
        return {**out, "excluded": f"parse error: {e}"}
    out["hardware"] = fl.hardware
    if fl.is_simulation:
        return {**out, "excluded": "simulation build (SITL/HITL)"}
    out["mappings"] = {}
    out["rows"] = {}
    for mp in MAPPINGS:
        miss = ulog_adapter.missing_requirements(fl, mp)
        if miss:
            out["mappings"][mp] = {"excluded": "missing topics: " + ", ".join(miss)}
            continue
        ticks = list(ulog_adapter.replay_ticks(fl, mp))
        ts = np.array([t for t, _ in ticks])
        air = dict(zip(ts.tolist(), ulog_adapter.airborne_mask(fl, ts).tolist(), strict=True))
        rows = realdata.score_ulog_flight(ticks, lambda t, a=air: a.get(t, False), cfg, bundle)
        m = realdata.flight_metrics(rows, cfg.detector["physics"])
        if m.get("n_airborne_ticks", 0) < 300:  # < 60 s airborne
            out["mappings"][mp] = {"excluded": "less than 60 s airborne", **m}
            continue
        out["mappings"][mp] = m
        out["rows"][mp] = [
            {k: r[k] for k in (*realdata.NAV_FEATURES, "groundspeed_ms", "ml_nav_probe")
             if k in r} for r in rows if r["airborne"] and r["gps_age_s"] < 1.0]
    return out


def _sim_one(args: tuple) -> dict:
    seed, route, speed, alt, noise = args
    cfg = load_config()
    bundle = joblib.load(MODEL) if Path(MODEL).exists() else None
    data = list(realdata.sim_reference_ticks(cfg, seed, route, speed, alt, noise))
    air = {t: a for t, _, a in data}
    rows = realdata.score_ulog_flight([(t, m) for t, m, _ in data],
                                      lambda t: air.get(t, False), cfg, bundle)
    m = realdata.flight_metrics(rows, cfg.detector["physics"])
    return {"seed": seed, "route": route, "speed": speed, "alt": alt, "noise_scale": noise,
            "metrics": m, "rows": [
                {k: r[k] for k in (*realdata.NAV_FEATURES, "groundspeed_ms", "ml_nav_probe")
                 if k in r} for r in rows if r["airborne"] and r["gps_age_s"] < 1.0]}


def sim_reference(n: int, workers: int) -> list[dict]:
    rng = np.random.default_rng(9000)
    routes = ("survey_box", "out_and_back", "perimeter")
    jobs = [(9001 + i, routes[i % 3], float(rng.uniform(9, 15)), float(rng.uniform(40, 80)),
             float(rng.uniform(0.8, 1.4))) for i in range(n)]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(_sim_one, jobs))


def _pooled(rows: list[dict]) -> dict:
    cols = (*realdata.NAV_FEATURES, "ml_nav_probe")
    return realdata.summarise(rows, [c for c in cols if rows and c in rows[0]])


def _rate_block(metrics: list[dict]) -> dict:
    keys = ["physics_trigger_rate", "ml_probe_alarm_rate", "ml_probe_lone_threat_rate",
            *[f"exceed_{f}" for f in realdata.NAV_FEATURES]]
    n_ticks = [m["n_airborne_ticks"] for m in metrics]
    tot = sum(n_ticks)
    out = {"n_flights": len(metrics), "n_airborne_ticks": tot, "airborne_hours": tot * 0.2 / 3600}
    for k in keys:
        vals = [m.get(k) for m in metrics if m.get(k) is not None]
        if not vals:
            continue
        out[k] = {"pooled": float(sum(v * w for v, w in zip(vals, n_ticks, strict=False)) / tot),
                  "median_of_flights": float(np.median(vals)),
                  "flights_with_any": int(sum(v > 0 for v in vals))}
    return out


def run_px4(out_dir: Path, workers: int, n_sim: int, protocol: str = "v2") -> dict:
    man_path = f"data/external/manifests/px4_review_{protocol}.json"
    man = read_manifest(man_path)
    paths = [f["path"] for f in man["files"]]
    print(f"E1: {len(paths)} downloaded PX4 logs; simulating {n_sim} reference flights …")
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        flights = list(ex.map(_px4_one, paths))
    sims = sim_reference(n_sim, workers)
    cfg = load_config()

    result: dict = {
        "experiment": "E1 PX4 Flight Review ULog navigation replay",
        "dataset_manifest": man_path, "protocol": protocol,
        "selection": man.get("selection"), "seed": man.get("seed"),
        "n_public_logs": man.get("n_public_logs"), "n_eligible": man.get("n_eligible"),
        "n_downloaded": len(paths),
        "thresholds": {k: cfg.detector["physics"][v] for k, v in realdata.NAV_THRESHOLD_KEYS.items()}
        | {"yaw_course_diff_deg": realdata.YAW_COURSE_THRESHOLD_DEG,
           "ml_score_threshold": cfg.detector["anomaly"]["score_threshold"],
           "ml_lone_threat_threshold": 0.9563},
        "exclusions": [{"file": f["file"], "reason": f["excluded"]} for f in flights
                       if "excluded" in f],
        "mappings": {},
        "sim_reference": {"n_flights": len(sims), "seeds": [s["seed"] for s in sims],
                          "rates": _rate_block([s["metrics"] for s in sims]),
                          "features": _pooled([r for s in sims for r in s["rows"]])},
        "python": platform.python_version(),
    }
    per_flight_rows = []
    for mp in MAPPINGS:
        ok = [f for f in flights if "excluded" not in f and "excluded" not in f["mappings"].get(mp, {"excluded": 1})]
        excl = [{"file": f["file"], "reason": f["mappings"][mp]["excluded"]} for f in flights
                if "excluded" not in f and "excluded" in f["mappings"].get(mp, {})]
        rows = [r for f in ok for r in f["rows"][mp]]
        result["mappings"][mp] = {
            "n_usable_flights": len(ok), "exclusions": excl,
            "rates": _rate_block([f["mappings"][mp] for f in ok]),
            "features": _pooled(rows),
            "hardware": sorted({f["hardware"] for f in ok}),
        }
        try:
            from scipy.stats import ks_2samp
            sim_rows = [r for s in sims for r in s["rows"]]
            result["mappings"][mp]["ks_vs_sim"] = {
                c: float(ks_2samp([r[c] for r in rows], [r[c] for r in sim_rows]).statistic)
                for c in realdata.NAV_FEATURES} if rows else {}
        except ImportError:
            pass
        for f in ok:
            per_flight_rows.append({"mapping": mp, "file": f["file"], "hardware": f["hardware"],
                                    **{k: v for k, v in f["mappings"][mp].items()
                                       if not isinstance(v, dict)}})
    result["wall_time_s"] = round(time.perf_counter() - t0, 1)
    d = out_dir / f"px4_review_{protocol}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    if per_flight_rows:
        keys = sorted({k for r in per_flight_rows for k in r})
        with (d / "per_flight.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=keys)
            w.writeheader()
            w.writerows(per_flight_rows)
    np.savez_compressed(d / "feature_samples.npz", **{
        f"{mp}__{c}": np.array([r[c] for f in flights if "excluded" not in f
                                and mp in f.get("rows", {}) for r in f["rows"][mp]])
        for mp in MAPPINGS for c in realdata.NAV_FEATURES},
        **{f"sim__{c}": np.array([r[c] for s in sims for r in s["rows"]])
           for c in realdata.NAV_FEATURES})
    return result


# --------------------------------------------------------------------------- #
# E2: ALFA real MAVLink telemetry -> full pipeline
# --------------------------------------------------------------------------- #

ALFA_ROOT = Path("data/external/raw/alfa")
DETS = ("protocol_rule", "physics_consistency", "ml_anomaly")

DET_TRIG = {"protocol_rule": 0.5, "physics_consistency": 0.5, "ml_anomaly": 0.62}


CALIBRATION_DATES = ("2018-07-18", "2018-07-30")  # E2b: calibrate on these, test on the rest


def _alfa_one(args: tuple[str, dict | None, bool]) -> dict:
    """Replay one tlog. ``protocol_over`` patches cfg.detector['protocol'] (E2b)."""
    from aegisflight.external import alfa, tlog_adapter

    path, protocol_over, use_ml = args
    cfg = load_config()
    if protocol_over:
        cfg.detector["protocol"].update(protocol_over)
    seqs = alfa.index_sequences(ALFA_ROOT / "processed" / "processed")
    rel = Path(path).relative_to(ALFA_ROOT).as_posix()
    date = Path(path).parent.parent.name
    segs = tlog_adapter.segments(tlog_adapter.iter_tlog(path))
    if not segs:
        return {"file": rel, "date": date, "excluded": "no decodable MAVLink frames", "rows": [],
                "segments": 0}
    rows: list[dict] = []
    model = MODEL if (use_ml and Path(MODEL).exists()) else None
    for k, (seg_t0, envs) in enumerate(segs):
        if len(envs) < 50:
            continue
        for r in realdata.score_tlog_flight(tlog_adapter.tlog_ticks(envs), cfg, model):
            r["seg"] = k
            r["t_unix"] = seg_t0 + r["t"]
            r["gt"] = alfa.label_at(seqs, r["t_unix"])
            r["airborne"] = (r["rel_alt"] or 0.0) > 5.0
            rows.append(r)
    keep = ("t_unix", "seg", "gt", "airborne", "threat", "pred", *[f"det_{d}" for d in DETS],
            *ML_FEATURES_ALL, "n_sources", "sources", "evidence")
    return {"file": rel, "date": date, "segments": len(segs),
            "rows": [{k: r[k] for k in keep} for r in rows]}


def _fault_events(rows: list[dict]) -> list[dict]:
    from aegisflight.external import alfa

    seqs = alfa.index_sequences(ALFA_ROOT / "processed" / "processed")
    rows = sorted(rows, key=lambda r: r["t_unix"])
    events = []
    for s in seqs:
        if s.kind != "fault" or s.t_onset is None:
            continue
        pre = [r for r in rows if s.t_start <= r["t_unix"] < s.t_onset]
        post = [r for r in rows if s.t_onset <= r["t_unix"] <= s.t_end]
        if not post:
            continue  # no telemetry recorded for this sequence
        events.append({
            "sequence": s.name, "fault": s.fault,
            "pre_onset_decisions": len(pre), "pre_onset_threat_rate": _rate(pre, "threat"),
            "post_onset_decisions": len(post), "post_onset_threat_rate": _rate(post, "threat"),
            "time_to_first_threat_s": next((r["t_unix"] - s.t_onset for r in post if r["threat"]), None),
            "pre_onset_physics_rate": _rate(pre, "det_physics_consistency", 0.5),
            "post_onset_physics_rate": _rate(post, "det_physics_consistency", 0.5),
            "time_to_first_physics_s": next((r["t_unix"] - s.t_onset for r in post
                                             if r["det_physics_consistency"] >= 0.5), None)})
    return events


def _rate(rows: list[dict], key: str, thr: float | None = None) -> float | None:
    if not rows:
        return None
    if thr is None:
        return sum(bool(r[key]) for r in rows) / len(rows)
    return sum(r[key] >= thr for r in rows) / len(rows)


def _category_block(rows: list[dict]) -> dict:
    from collections import Counter

    out: dict = {"n_decisions": len(rows)}
    if not rows:
        return out
    out["threat_rate"] = _rate(rows, "threat")
    for d in DETS:
        out[f"{d}_trigger_rate"] = _rate(rows, f"det_{d}", DET_TRIG[d])
    out["predicted_classes"] = dict(Counter(r["pred"] for r in rows if r["threat"]))
    ev = Counter()
    for r in rows:
        if r["threat"]:
            for e in r["evidence"]:
                ev[e.split(":")[0].split("(")[0].split(" ≥")[0].split(" >")[0].strip()[:48]] += 1
    out["top_evidence"] = dict(ev.most_common(8))
    return out


def _alfa_result(flights: list[dict], title: str, extra: dict) -> dict:
    from aegisflight.external import alfa

    seqs = alfa.index_sequences(ALFA_ROOT / "processed" / "processed")
    flights, n_dup = alfa.dedup_overlapping_recordings([f for f in flights if "excluded" not in f])
    rows = [r for f in flights for r in f["rows"]]
    faults = _fault_events(rows)
    sources: dict[str, int] = {}
    for r in rows:
        for s in r["sources"]:
            sources[s] = sources.get(s, 0) + 1
    fe = [f for f in faults if f["post_onset_threat_rate"] is not None]
    return {
        "experiment": title, **extra,
        "dataset_manifest": "data/external/manifests/alfa.json",
        "n_tlogs": len(flights),
        "decisions_after_dedup": len(rows),
        "overlapping_duplicate_decisions_dropped": n_dup,
        "total_decision_hours": len(rows) * 0.2 / 3600,
        "n_sequences_indexed": len(seqs),
        "sequence_kinds": {k: sum(s.kind == k for s in seqs) for k in
                           ("no_failure", "fault", "no_ground_truth")},
        "categories": {c: _category_block([r for r in rows if r["gt"] == c])
                       for c in ("benign_gt", "fault", "unlabelled")},
        "categories_airborne": {c: _category_block([r for r in rows if r["gt"] == c and r["airborne"]])
                                for c in ("benign_gt", "fault", "unlabelled")},
        "fault_events": faults,
        "fault_event_summary": {
            "n_with_telemetry": len(fe),
            "detected_any_threat": sum(f["time_to_first_threat_s"] is not None for f in fe),
            "detected_by_physics": sum(f["time_to_first_physics_s"] is not None for f in fe),
            "mean_pre_onset_threat_rate": float(np.mean([f["pre_onset_threat_rate"] for f in fe
                                                         if f["pre_onset_threat_rate"] is not None]))
            if fe else None,
            "mean_post_onset_threat_rate": float(np.mean([f["post_onset_threat_rate"] for f in fe]))
            if fe else None,
        },
        "real_link_stats_airborne": realdata.summarise(
            [r for r in rows if r["airborne"] and r["gt"] == "benign_gt"],
            ["msg_rate_hz", "interarrival_jitter_ms", "max_seq_gap", "loss_ratio", "n_sources"]),
        "source_ids_seen": dict(sorted(sources.items(), key=lambda kv: -kv[1])[:12]),
        "per_flight": [{"file": f["file"], "date": f["date"], "segments": f["segments"],
                        "decisions_kept": len(f["rows"]), "threat_rate": _rate(f["rows"], "threat")}
                       for f in flights],
        "python": platform.python_version(),
    }


def run_alfa(out_dir: Path, workers: int) -> dict:
    tlogs = sorted(str(p) for p in (ALFA_ROOT / "telemetry").rglob("*.tlog"))
    print(f"E2: {len(tlogs)} ALFA telemetry logs -> full IDS replay (production config) …")
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        flights = list(ex.map(_alfa_one, [(p, None, True) for p in tlogs]))
    excluded = [{"file": f["file"], "reason": f["excluded"]} for f in flights if "excluded" in f]
    result = _alfa_result(flights, "E2 ALFA real MAVLink telemetry -> full AegisFlight pipeline "
                          "(production config, ML on)", {"exclusions": excluded})
    result["wall_time_s"] = round(time.perf_counter() - t0, 1)
    _write(out_dir / "alfa", result)

    # ---- E2b: per-vehicle link calibration on held-out dates, ML off ----
    cal_rows = [r for f in flights if f.get("date") in CALIBRATION_DATES
                for r in f.get("rows", []) if r["airborne"] and r["gt"] != "fault"]
    cfg = load_config()
    p = cfg.detector["protocol"]
    nominal = float(np.median([r["msg_rate_hz"] for r in cal_rows]))
    over = {"nominal_msg_rate_hz": nominal,
            "max_msg_rate_hz": nominal * float(p["max_msg_rate_hz"]) / float(p["nominal_msg_rate_hz"])}
    test = [x for x in tlogs if Path(x).parent.parent.name not in CALIBRATION_DATES]
    print(f"E2b: calibrated nominal rate {nominal:.1f} msg/s on {CALIBRATION_DATES}; "
          f"testing {len(test)} tlogs with ML off …")
    with ProcessPoolExecutor(max_workers=workers) as ex:
        tflights = list(ex.map(_alfa_one, [(x, over, False) for x in test]))
    res_b = _alfa_result(tflights, "E2b ALFA held-out dates: protocol rate thresholds calibrated "
                         "per vehicle, ML off",
                         {"calibration": {"dates": list(CALIBRATION_DATES),
                                          "n_calibration_decisions": len(cal_rows),
                                          "rule": "nominal_msg_rate_hz := median airborne non-fault "
                                                  "msg rate on calibration dates; max_msg_rate_hz scaled "
                                                  "by the same ratio as the default config",
                                          "protocol_overrides": over},
                          "test_dates": sorted({Path(x).parent.parent.name for x in test}),
                          "exclusions": [{"file": f["file"], "reason": f["excluded"]}
                                         for f in tflights if "excluded" in f]})
    _write(out_dir / "alfa_calibrated", res_b)
    return result


def _write(d: Path, result: dict) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / "results.json").write_text(json.dumps(result, indent=2, default=float), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--px4", action="store_true")
    ap.add_argument("--px4-protocol", default="v2", choices=["v1", "v2"])
    ap.add_argument("--alfa", action="store_true")
    ap.add_argument("--sim-ref", type=int, default=12, help="simulated reference flights (E1)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", type=Path, default=Path("artifacts/external"))
    a = ap.parse_args()
    if a.px4:
        run_px4(a.out, a.workers, a.sim_ref, a.px4_protocol)
    if a.alfa:
        run_alfa(a.out, a.workers)
    from aegisflight.external.report import write_summaries
    for p in write_summaries(a.out):
        print("wrote", p)


if __name__ == "__main__":
    main()
