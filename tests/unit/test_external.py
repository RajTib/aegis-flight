"""External-data adapters: provenance, selection, ULog/tlog replay, ALFA labels.

These tests never touch the network or real datasets: they use tiny synthetic
inputs so the adapters' *mechanics* (units, timing, segmentation, labelling,
exclusions) are pinned down.
"""

from __future__ import annotations

import struct

import numpy as np
import pytest

from aegisflight.config import load_config
from aegisflight.core.enums import AttackType
from aegisflight.external import alfa, px4_review, realdata, tlog_adapter, ulog_adapter
from aegisflight.external.provenance import download, read_manifest, sha256_file, write_manifest

# --------------------------------------------------------------------------- #
# provenance
# --------------------------------------------------------------------------- #


def test_download_file_url_records_sha256(tmp_path):
    src = tmp_path / "src.bin"
    src.write_bytes(b"aegis" * 100)
    rec = download(src.resolve().as_uri(), tmp_path / "out" / "copy.bin")
    assert rec.bytes == 500
    assert rec.sha256 == sha256_file(src)
    man = write_manifest(tmp_path / "m.json", {"name": "x"}, [rec], extra={"seed": 1})
    doc = read_manifest(man)
    assert doc["files"][0]["sha256"] == rec.sha256 and doc["seed"] == 1


# --------------------------------------------------------------------------- #
# PX4 Flight Review selection protocol
# --------------------------------------------------------------------------- #


def _entry(i, **kw):
    e = {"log_id": f"id{i:03d}", "sys_hw": "PX4_FMU_V5", "mav_type": "Quadrotor",
         "rating": "good", "error_labels": [], "estimator": "EKF2", "duration_s": 600,
         "log_date": "2025-05-01"}
    e.update(kw)
    return e


def test_px4_selection_rules_and_determinism():
    db = [_entry(i) for i in range(30)] + [
        _entry(100, sys_hw="PX4_SITL"), _entry(101, mav_type="Fixed Wing"),
        _entry(102, rating=""), _entry(103, error_labels=[1]), _entry(104, duration_s=30),
        _entry(105, log_date="2019-01-01"), _entry(106, estimator="LPE"), _entry(107, sys_hw="")]
    v1 = px4_review.SELECTION_V1
    a, n_el = px4_review.select_logs(db, 10, seed=7, sel=v1)
    b, _ = px4_review.select_logs(list(reversed(db)), 10, seed=7, sel=v1)
    assert n_el == 30
    assert [x["log_id"] for x in a] == [x["log_id"] for x in b]  # order-independent
    assert all(int(x["log_id"][2:]) < 30 for x in a)


def test_px4_selection_v2_rejects_hitl_and_dedups_vehicles():
    db = [_entry(i, rating="", vehicle_uuid=f"veh{i % 5}", num_logged_errors=0) for i in range(20)]
    db += [_entry(50, airframe_name="HIL Quadcopter X"), _entry(51, sys_autostart_id=1001),
           _entry(52, num_logged_errors=3), _entry(53, rating="crash_pilot")]
    picked, n_el = px4_review.select_logs(db, 50, seed=1, sel=px4_review.SELECTION_V2)
    assert n_el == 5  # one per vehicle_uuid; HITL/errors/crash excluded
    assert len({p["vehicle_uuid"] for p in picked}) == 5


# --------------------------------------------------------------------------- #
# ULog navigation replay (synthetic ULogFlight, no pyulog needed)
# --------------------------------------------------------------------------- #


def _flight(hw="PX4_FMU_V6X", hitl=0, baro_offset=40.0, n=600):
    t = np.arange(n) * 0.1  # 10 Hz estimator topics, 60 s
    lat0, lon0 = 47.0, 8.0
    vn = np.full(n, 5.0)
    north = np.cumsum(vn) * 0.1
    lat = lat0 + np.degrees(north / 6_371_000.0)
    lon = np.full(n, lon0)
    alt = np.full(n, 500.0)
    q = {"q[0]": np.ones(n), "q[1]": np.zeros(n), "q[2]": np.zeros(n), "q[3]": np.zeros(n)}
    gi = np.arange(0, n, 2)  # GNSS at 5 Hz
    series = {
        "vehicle_local_position": {"t": t, "vx": vn, "vy": np.zeros(n), "vz": np.zeros(n),
                                   "z": np.full(n, -20.0), "ref_alt": np.full(n, 480.0)},
        "vehicle_global_position": {"t": t, "lat": lat, "lon": lon, "alt": alt},
        "vehicle_gps_position": {"t": t[gi], "lat": (lat[gi] * 1e7).astype(np.int64),
                                 "lon": (lon[gi] * 1e7).astype(np.int64),
                                 "alt": (alt[gi] * 1e3).astype(np.int64),
                                 "vel_n_m_s": vn[gi], "vel_e_m_s": np.zeros(len(gi)),
                                 "fix_type": np.full(len(gi), 3)},
        "vehicle_air_data": {"t": t, "baro_alt_meter": alt + baro_offset},
        "vehicle_attitude": {"t": t, **q},
        "vehicle_land_detected": {"t": np.array([0.0, 5.0]), "landed": np.array([1, 0])},
    }
    return ulog_adapter.ULogFlight(path="synthetic", info={"ver_hw": hw},
                                   params={"SYS_HITL": hitl}, series=series)


def test_ulog_simulation_builds_are_flagged():
    assert _flight(hw="PX4_SITL").is_simulation
    assert _flight(hitl=1).is_simulation
    assert not _flight().is_simulation


def test_ulog_replay_units_and_no_duplicate_fixes():
    fl = _flight()
    ticks = list(ulog_adapter.replay_ticks(fl, "independent_sensors"))
    gpi = [m for _, ms in ticks for m in ms if m.msgname == "GLOBAL_POSITION_INT"]
    # 5 Hz GNSS, 0.2 s decisions -> at most one fix per decision, none duplicated
    assert len(gpi) <= len(ticks)
    assert len({m.fields["lat"] for m in gpi}) == len(gpi)
    assert gpi[0].fields["vx"] == 500  # cm/s
    vfr = [m for _, ms in ticks for m in ms if m.msgname == "VFR_HUD"]
    assert vfr[0].fields["alt"] == pytest.approx(540.0)  # raw pressure altitude (offset kept)


def test_ulog_bias_corrected_mapping_removes_constant_baro_offset():
    fl = _flight(baro_offset=40.0)
    cfg = load_config()
    ticks = list(ulog_adapter.replay_ticks(fl, "independent_sensors_biascorr"))
    rows = realdata.score_ulog_flight(ticks, lambda t: t > 5.0, cfg, bundle=None)
    air = [r for r in rows if r["airborne"]]
    assert max(r["gps_baro_alt_diff_m"] for r in air) < 1.0
    raw = realdata.score_ulog_flight(list(ulog_adapter.replay_ticks(fl, "independent_sensors")),
                                     lambda t: t > 5.0, cfg, bundle=None)
    assert min(r["gps_baro_alt_diff_m"] for r in raw if r["airborne"]) > 30.0


def test_ulog_px4_mapping_speed_channels_are_degenerate():
    """Under PX4 telemetry semantics GPS speed and VFR groundspeed are the same EKF value."""
    fl = _flight()
    rows = realdata.score_ulog_flight(list(ulog_adapter.replay_ticks(fl, "px4_telemetry")),
                                      lambda t: t > 5.0, load_config(), bundle=None)
    assert max(r["gps_vfr_speed_diff_ms"] for r in rows if r["airborne"]) < 0.05


def test_ulog_invalid_estimator_samples_are_not_emitted():
    fl = _flight()
    lp = fl.series["vehicle_local_position"]
    lp["v_xy_valid"] = np.ones(len(lp["t"]), dtype=bool)
    lp["v_xy_valid"][100:300] = False            # t in [10, 30) s invalid
    lp["vx"] = lp["vx"].copy()
    lp["vx"][100:300] = 600.0                     # garbage while invalid
    for mp in ("px4_telemetry", "independent_sensors"):
        ticks = list(ulog_adapter.replay_ticks(fl, mp))
        bad = [m for t, ms in ticks if 10.5 < t < 29.5 for m in ms
               if m.msgname == "VFR_HUD" or (mp == "px4_telemetry" and m.msgname == "GLOBAL_POSITION_INT")]
        assert bad == []
        rows = realdata.score_ulog_flight(ticks, lambda t: t > 5.0, load_config(), bundle=None)
        assert max(r["gps_vfr_speed_diff_ms"] for r in rows) < 100.0


def test_ulog_airborne_mask_and_requirements():
    fl = _flight()
    m = ulog_adapter.airborne_mask(fl, np.array([1.0, 6.0]))
    assert m.tolist() == [False, True]
    del fl.series["vehicle_air_data"]
    assert "vehicle_air_data" in ulog_adapter.missing_requirements(fl, "independent_sensors")
    assert ulog_adapter.missing_requirements(fl, "px4_telemetry") == []
    with pytest.raises(ValueError):
        list(ulog_adapter.replay_ticks(fl, "bogus"))


def test_flight_metrics_rates():
    cfg = load_config()
    rows = [{"airborne": True, "physics_triggered": i < 2, "physics_evidence": [],
             "pos_residual_m": 20.0 if i == 0 else 1.0, "gps_vfr_speed_diff_ms": 0.0,
             "gps_baro_alt_diff_m": 0.0, "alt_rate_ms": 0.0, "accel_ms2": 0.0,
             "yaw_course_diff_deg": 90.0, "groundspeed_ms": 5.0} for i in range(10)]
    m = realdata.flight_metrics(rows, cfg.detector["physics"])
    assert m["physics_trigger_rate"] == pytest.approx(0.2)
    assert m["exceed_pos_residual_m"] == pytest.approx(0.1)
    assert m["exceed_yaw_course_diff_deg"] == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# tlog replay
# --------------------------------------------------------------------------- #


def _write_tlog(path, frames):
    """frames: list of (unix_ts, pymavlink message). Standard tlog = 8-byte BE µs + frame."""
    from pymavlink.dialects.v20 import common as mav

    m = mav.MAVLink(None, srcSystem=1, srcComponent=1)
    with open(path, "wb") as fh:
        for ts, msg in frames:
            fh.write(struct.pack(">Q", int(ts * 1e6)) + msg.pack(m))
            m.seq = (m.seq + 1) % 256


def test_tlog_iter_segments_and_ticks(tmp_path):
    from pymavlink.dialects.v20 import common as mav

    hb = mav.MAVLink_heartbeat_message(2, 3, 0, 0, 4, 3)
    base = 1_700_000_000.0
    times = [base + 0.05 * i for i in range(40)] + [base + 500 + 0.05 * i for i in range(20)]
    p = tmp_path / "x.tlog"
    _write_tlog(p, [(t, hb) for t in times])
    envs = list(tlog_adapter.iter_tlog(p))
    assert len(envs) == 60 and envs[0].msgname == "HEARTBEAT"
    segs = tlog_adapter.segments(iter(envs))
    assert len(segs) == 2 and segs[0][0] == pytest.approx(base, abs=1e-3)
    assert [len(s) for _, s in segs] == [40, 20]
    ticks = list(tlog_adapter.tlog_ticks(segs[0][1]))
    for tk in ticks:  # causality: no frame delivered before it was received
        assert all(m.recv_time <= tk.t + 1e-9 for m in tk.messages)
    assert sum(len(tk.messages) for tk in ticks) == 40
    assert all(tk.label is AttackType.BENIGN for tk in ticks)


def test_simulated_flight_roundtrips_through_tlog(tmp_path):
    """Simulator -> MAVLink bytes -> .tlog -> replay reproduces the benign verdicts."""
    from aegisflight.benchmark.runner import run_session
    from aegisflight.sources.stream import SimulatedTelemetrySource

    cfg = load_config()
    p = tmp_path / "sim.tlog"
    base = 1_700_000_000.0
    # Write the exact wire bytes the simulator produces, with tlog timestamps.
    src = SimulatedTelemetrySource(cfg, attack=None, seed=3)
    with open(p, "wb") as fh:
        for state_tick, state in enumerate(src.sim.run()):
            for pkt in src.encoder.encode_tick(state, state_tick):
                fh.write(struct.pack(">Q", int((base + pkt.send_time) * 1e6)) + pkt.data)
    (seg_t0, envs), = tlog_adapter.segments(tlog_adapter.iter_tlog(p))
    rows = realdata.score_tlog_flight(tlog_adapter.tlog_ticks(envs), cfg, model_path=None)
    direct = run_session(cfg, "benign", seed=3, model_path=None)
    assert len(rows) == pytest.approx(len(direct.records), abs=2)
    assert sum(r["threat"] for r in rows) == 0
    assert sum(r.threat for r in direct.records) == 0


# --------------------------------------------------------------------------- #
# ALFA ground-truth index
# --------------------------------------------------------------------------- #


def _csv(path, rows, header="%time,field.data"):
    path.write_text(header + "\n" + "\n".join(",".join(map(str, r)) for r in rows) + "\n")


def test_alfa_index_and_labels(tmp_path):
    root = tmp_path / "processed"
    for name, onset in (("carbonZ_2018-01-01-00-00-00_no_failure", None),
                        ("carbonZ_2018-01-01-00-10-00_engine_failure", 1_000_150)):
        d = root / name
        d.mkdir(parents=True)
        t0 = 1_000_000 if "no_failure" in name else 1_000_100
        _csv(d / f"{name}-mavros-global_position-global.csv",
             [(int((t0 + i) * 1e9), 0) for i in range(100)])
        if onset:
            _csv(d / f"{name}-failure_status-engines.csv",
                 [(int(onset * 1e9), 1), (int((onset + 1) * 1e9), 1)])
    seqs = alfa.index_sequences(root)
    kinds = {s.kind for s in seqs}
    assert kinds == {"no_failure", "fault"}
    assert alfa.label_at(seqs, 1_000_050) == "benign_gt"      # inside no-failure window
    assert alfa.label_at(seqs, 1_000_120) == "benign_gt"      # fault seq, before onset
    assert alfa.label_at(seqs, 1_000_160) == "fault"          # after onset
    assert alfa.label_at(seqs, 2_000_000) == "unlabelled"


def test_alfa_overlapping_recordings_counted_once():
    a = {"file": "a", "rows": [{"t_unix": float(t)} for t in range(0, 100)]}
    b = {"file": "b", "rows": [{"t_unix": float(t)} for t in range(50, 120)]}  # overlaps a
    out, dropped = alfa.dedup_overlapping_recordings([b, a])
    kept = sorted(r["t_unix"] for f in out for r in f["rows"])
    assert dropped == 50 and kept == [float(t) for t in range(0, 120)]


def test_alfa_dedup_respects_clock_jump_segments():
    jump = {"file": "j", "rows": [{"t_unix": 0.0, "seg": 0}, {"t_unix": 1.0, "seg": 0},
                                  {"t_unix": 1000.0, "seg": 1}, {"t_unix": 1001.0, "seg": 1},
                                  {"t_unix": 1002.0, "seg": 1}]}
    other = {"file": "o", "rows": [{"t_unix": 500.0, "seg": 0}]}  # inside the jump gap
    out, dropped = alfa.dedup_overlapping_recordings([jump, other])
    assert dropped == 0 and sum(len(f["rows"]) for f in out) == 6
