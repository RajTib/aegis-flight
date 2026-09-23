"""Render ``summary.md`` for external experiments from their ``results.json``.

Docs must never hand-copy numbers: they link to these generated files.
"""

from __future__ import annotations

import json
from pathlib import Path


def _pct(x) -> str:
    return "—" if x is None else f"{100.0 * float(x):.2f} %"


def _num(x, nd=2) -> str:
    return "—" if x is None else f"{float(x):.{nd}f}"


def _px4_md(r: dict) -> str:
    L = ["# E1 — PX4 Flight Review real flights: navigation replay (generated)", "",
         f"_Source manifest: `{r['dataset_manifest']}` · public logs listed: {r['n_public_logs']} · "
         f"eligible under the selection protocol: {r['n_eligible']} · downloaded: {r['n_downloaded']} "
         f"(seed {r['seed']}, protocol `{r.get('protocol', '?')}`)._", "",
         "Network features (msg rate, jitter, sequence gaps, loss, command rate) are **not "
         "available** from an on-board ULog and are excluded. The ML column is a *navigation "
         "probe*: network features held at their benign training mean (z = 0) — it is **not** "
         "an ML validation.", ""]
    L += ["## Exclusions (whole log)", ""]
    L += [f"- `{e['file']}`: {e['reason']}" for e in r["exclusions"]] or ["- none"]
    L += ["", "## Airborne alarm / exceedance rates (production thresholds, no tuning)", "",
          "| Metric | Sim reference | " + " | ".join(f"Real: `{m}`" for m in r["mappings"]) + " |",
          "|---|---|" + "---|" * len(r["mappings"])]
    sim = r["sim_reference"]["rates"]
    rows = [("Usable flights", lambda b: str(b.get("n_flights", "—")), None),
            ("Airborne hours", lambda b: _num(b.get("airborne_hours")), None)]
    keys = ["physics_trigger_rate", "ml_probe_alarm_rate", "ml_probe_lone_threat_rate",
            "exceed_pos_residual_m", "exceed_gps_vfr_speed_diff_ms", "exceed_gps_baro_alt_diff_m",
            "exceed_alt_rate_ms", "exceed_accel_ms2", "exceed_yaw_course_diff_deg"]
    for name, fn, _ in rows:
        L.append(f"| {name} | {fn(sim)} | " + " | ".join(fn(r['mappings'][m]['rates'])
                                                     for m in r["mappings"]) + " |")
    for k in keys:
        def cell(b, k=k):
            v = b.get(k)
            return "—" if not v else f"{_pct(v['pooled'])} (flights: {v['flights_with_any']})"
        L.append(f"| {k} | {cell(sim)} | " + " | ".join(cell(r['mappings'][m]['rates'])
                                                       for m in r["mappings"]) + " |")
    L += ["", "## Feature distributions (airborne, pooled): p50 / p99", "",
          "| Feature | Sim | " + " | ".join(f"`{m}`" for m in r["mappings"]) + " | KS vs sim (" +
          ", ".join(r["mappings"]) + ") |", "|---|---|" + "---|" * len(r["mappings"]) + "---|"]
    for f, s in r["sim_reference"]["features"].items():
        cells = []
        for m in r["mappings"]:
            v = r["mappings"][m]["features"].get(f, {})
            cells.append(f"{_num(v.get('p50'))} / {_num(v.get('p99'))}" if v.get("n") else "—")
        ks = ", ".join(_num(r["mappings"][m].get("ks_vs_sim", {}).get(f)) for m in r["mappings"])
        L.append(f"| {f} | {_num(s.get('p50'))} / {_num(s.get('p99'))} | " + " | ".join(cells)
                 + f" | {ks} |")
    L += ["", f"_Thresholds: {json.dumps(r['thresholds'])}_", ""]
    return "\n".join(L)


def _alfa_md(r: dict) -> str:
    L = ["# E2 — ALFA real MAVLink telemetry through the full IDS (generated)", "",
         f"_{r['experiment']}._", "",
         f"_Manifest: `{r['dataset_manifest']}` · {r['n_tlogs']} ground-station `.tlog` files · "
         f"{r['decisions_after_dedup']} decisions ({_num(r['total_decision_hours'])} h) after dropping "
         f"{r['overlapping_duplicate_decisions_dropped']} decisions from overlapping recordings of the "
         f"same flight · {r['n_sequences_indexed']} author-labelled sequences "
         f"{json.dumps(r['sequence_kinds'])}._", "",
         "Ground truth comes from the dataset authors' processed sequences: `benign_gt` = "
         "no-failure sequences + pre-onset part of fault sequences; `fault` = after the "
         "`failure_status` onset (physical faults, **not** cyber attacks); `unlabelled` = rest "
         "of the log (manual flight, taxi, ground).", "",
         "## Decision-level alarm rates (fused IDS; configuration as in the title — nothing retrained)", "",
         "| Category | Decisions | Fused threat rate | Protocol ≥0.5 | Physics ≥0.5 | ML ≥0.62 |",
         "|---|---|---|---|---|---|"]
    for scope, key in (("all", "categories"), ("airborne", "categories_airborne")):
        for c, b in r[key].items():
            L.append(f"| {c} ({scope}) | {b['n_decisions']} | {_pct(b.get('threat_rate'))} | "
                     f"{_pct(b.get('protocol_rule_trigger_rate'))} | "
                     f"{_pct(b.get('physics_consistency_trigger_rate'))} | "
                     f"{_pct(b.get('ml_anomaly_trigger_rate'))} |")
    L += ["", "## What fired on author-labelled benign periods", "",
          "```", json.dumps({k: r["categories"]["benign_gt"].get(k) for k in
                             ("predicted_classes", "top_evidence")}, indent=1), "```", "",
          "## Real link statistics (airborne, author-labelled benign) vs simulator assumptions", "",
          "Simulator reference: nominal 28 msg/s configured (`protocol.nominal_msg_rate_hz`); see the "
          "ML scaler means in `models/isoforest.joblib` for the simulated benign rate/jitter.", "", "```",
          json.dumps(r["real_link_stats_airborne"], indent=1), "```",
          f"Source ids seen (sysid/compid: decisions present): `{json.dumps(r['source_ids_seen'])}`",
          "", "## Fault events (physical faults — not attacks)", "",
          "| Sequence | Pre-onset threat rate | Post-onset threat rate | First threat after onset (s) | First physics after onset (s) |",
          "|---|---|---|---|---|"]
    for f in r["fault_events"]:
        L.append(f"| {f['sequence']} | {_pct(f['pre_onset_threat_rate'])} | "
                 f"{_pct(f['post_onset_threat_rate'])} | {_num(f['time_to_first_threat_s'])} | "
                 f"{_num(f['time_to_first_physics_s'])} |")
    L.append("")
    L.append(f"Summary: `{json.dumps(r['fault_event_summary'])}`")
    if r.get("calibration"):
        L += ["", "## Calibration (E2b)", "", "```", json.dumps(r["calibration"], indent=1), "```",
              f"Test dates: {r.get('test_dates')}"]
    return "\n".join(L) + "\n"


def write_summaries(out_dir: str | Path) -> list[Path]:
    out_dir = Path(out_dir)
    written = []
    for name, fn in (("px4_review_v1", _px4_md), ("px4_review_v2", _px4_md), ("alfa", _alfa_md),
                     ("alfa_calibrated", _alfa_md)):
        p = out_dir / name / "results.json"
        if p.exists():
            md = out_dir / name / "summary.md"
            try:
                md.write_text(fn(json.loads(p.read_text(encoding="utf-8"))), encoding="utf-8")
            except KeyError as e:  # results.json from an older schema -> re-run that experiment
                print(f"skip {name}: results.json predates current schema (missing {e})")
                continue
            written.append(md)
    return written
