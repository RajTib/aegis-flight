"""New attack variants, simultaneous attacks, link impairment and benchmark v2 plumbing."""

from __future__ import annotations

import copy

import numpy as np

from aegisflight.attacks import CompositeAttack, build_attack
from aegisflight.benchmark import extended as ext
from aegisflight.benchmark.runner import run_session
from aegisflight.config import load_config
from aegisflight.core.enums import AttackType
from aegisflight.sources.stream import SimulatedTelemetrySource


def _cfg(**attack_over):
    cfg = load_config()
    for name, over in attack_over.items():
        cfg.attacks[name].update(over)
    return cfg


def _recall(res):
    pos = [r for r in res.records if r.scored and r.true_label.is_attack]
    return sum(r.pred_label.is_attack for r in pos) / len(pos), pos


def test_gnss_jamming_detected_as_navigation_denial():
    res = run_session(_cfg(dos={"mode": "gnss_jamming"}), "dos", seed=5, model_path=None)
    rec, pos = _recall(res)
    assert rec > 0.9
    assert {r.pred_label for r in pos if r.pred_label.is_attack} == {AttackType.DOS}
    neg = [r for r in res.records if r.scored and not r.true_label.is_attack]
    assert not any(r.pred_label.is_attack for r in neg)


def test_gcs_replay_is_a_documented_known_gap():
    """A replayed command from the legitimate GCS id is invisible without signing."""
    res = run_session(_cfg(command_injection={"mode": "gcs_replay"}), "command_injection",
                      seed=5, model_path=None)
    rec, _ = _recall(res)
    assert rec == 0.0


def test_composite_attack_multilabel_ground_truth():
    cfg = _cfg(dos={"start_s": 45.0, "duration_s": 20.0})
    atk = build_attack("gps_spoofing+dos", cfg.attacks, np.random.default_rng(0))
    assert isinstance(atk, CompositeAttack)
    assert atk.labels(42.0) == {AttackType.GPS_SPOOFING}
    assert atk.labels(50.0) == {AttackType.GPS_SPOOFING, AttackType.DOS}
    assert atk.labels(80.0) == frozenset()
    assert atk.label(50.0) is AttackType.GPS_SPOOFING  # first component = primary
    res = run_session(cfg, "gps_spoofing+dos", seed=5, model_path=None)
    both = [r for r in res.records if r.scored and len(r.true_set) == 2]
    assert both and all(set(r.true_set) == {"GPS_SPOOFING", "DOS"} for r in both)
    covered = [set(r.true_set) <= ({r.pred_label.value} | set(r.pred_secondary)) for r in both]
    assert np.mean(covered) > 0.5


def test_composite_with_firmware_gets_shared_firmware_dir():
    cfg = _cfg(firmware_integrity={"start_s": 40.0})
    res = run_session(cfg, "telemetry_manipulation+firmware_integrity", seed=5, model_path=None)
    fw = [r for r in res.records if r.t > 75.0 and r.scored]  # telemetry window over, firmware on
    assert fw and np.mean([r.pred_label is AttackType.FIRMWARE_INTEGRITY for r in fw]) > 0.9


def test_link_impairment_off_by_default_and_fifo_preserves_order():
    cfg = load_config()
    a = [len(t.messages) for _, t in zip(range(200), SimulatedTelemetrySource(cfg, seed=3).stream(), strict=False)]
    cfg2 = copy.deepcopy(cfg)
    cfg2.simulation["link"] = {"mean_delay_ms": 0.0, "loss_prob": 0.0}
    b = [len(t.messages) for _, t in zip(range(200), SimulatedTelemetrySource(cfg2, seed=3).stream(), strict=False)]
    assert a == b
    cfg3 = copy.deepcopy(cfg)
    cfg3.simulation["link"] = {"mean_delay_ms": 30.0, "loss_prob": 0.05, "fifo": True}
    last = -1.0
    n = 0
    for _, tick in zip(range(300), SimulatedTelemetrySource(cfg3, seed=3).stream(), strict=False):
        for m in tick.messages:
            assert m.recv_time >= last - 1e-12
            last = m.recv_time
            n += 1
    assert 0 < n < 1.1 * sum(a) * 1.5  # frames still flow (minus ~5 % loss)


def test_extended_grid_is_deterministic_and_seed_disjoint():
    g1 = ext.build_grid(seeds_per_mode=1, n_benign=2, combo_seeds=1, n_link=1)
    g2 = ext.build_grid(seeds_per_mode=1, n_benign=2, combo_seeds=1, n_link=1)
    assert [(s.key, s.seed, round(s.speed, 6)) for s in g1] == [(s.key, s.seed, round(s.speed, 6)) for s in g2]
    seeds = {s.seed for s in g1}
    assert seeds.isdisjoint(range(101, 125)) and 42 not in seeds
    n_modes = sum(len(v) for v in ext.MODES.values())
    assert sum(s.kind == "single" for s in g1) == n_modes
    spec = next(s for s in g1 if s.key == "gps_spoofing:sudden_offset")
    cfg = ext.session_config(load_config(), spec)
    assert cfg.attacks["gps_spoofing"]["mode"] == "sudden_offset"
    assert cfg.attacks["gps_spoofing"]["start_s"] == spec.onset
    assert cfg.simulation["seed"] == spec.seed and cfg.simulation["route"] == spec.route


def test_extended_summary_counts_grace_and_combos():
    def rec(t, true, pred, grace=0, true_set="", sec=""):
        return {"t": t, "true": true, "true_set": true_set or ("" if true == "BENIGN" else true),
                "pred": pred, "secondary": sec, "threat": int(pred != "BENIGN"),
                "in_grace": grace, "warm": int(t < 5)}

    single = {"spec": {"kind": "single", "scenario": "dos"}, "key": "dos:flood",
              "time_to_detect_s": 0.0, "compute_ms_mean": 1.0, "compute_ms_p95": 2.0,
              "records": [rec(1, "BENIGN", "DOS"), rec(10, "DOS", "DOS"), rec(11, "DOS", "BENIGN"),
                          rec(12, "BENIGN", "DOS", grace=1), rec(20, "BENIGN", "BENIGN")]}
    combo = {"spec": {"kind": "combo", "scenario": "dos+gps_spoofing"}, "key": "dos+gps_spoofing",
             "time_to_detect_s": 0.0, "compute_ms_mean": 1.0, "compute_ms_p95": 2.0,
             "records": [rec(10, "DOS", "DOS", true_set="DOS|GPS_SPOOFING", sec="GPS_SPOOFING"),
                         rec(11, "DOS", "DOS", true_set="DOS|GPS_SPOOFING")]}
    s = ext.summarise([single, combo])
    g5, g0 = s["binary_grace5"], s["binary_grace0"]
    assert (g5["tp"], g5["fn"], g5["fp"], g5["tn"]) == (1, 1, 0, 1)  # warm-up + grace excluded
    assert (g0["tp"], g0["fn"], g0["fp"], g0["tn"]) == (1, 1, 1, 1)  # grace tick counted as FP
    c = s["combos"]["dos+gps_spoofing"]
    assert c["binary_recall"] == 1.0 and c["full_coverage_when_both_active"] == 0.5
