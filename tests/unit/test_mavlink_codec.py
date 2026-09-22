"""MAVLink codec: encode/decode round-trip and sequence handling."""

from aegisflight.config import load_config
from aegisflight.mavlink import MavlinkDecoder, MavlinkEncoder
from aegisflight.simulator import FlightSimulator, SimulatorConfig


def _one_tick_messages(tick=600):
    cfg = load_config()
    states = FlightSimulator(SimulatorConfig.from_config(cfg.simulation)).run_list()
    enc = MavlinkEncoder(cfg.message_rates, cfg.simulation["noise"], seed=42)
    dec = MavlinkDecoder()
    msgs = {}
    for k in range(tick, tick + 10):
        for pkt in enc.encode_tick(states[k], k):
            for env in dec.decode(pkt.data, pkt.send_time):
                msgs.setdefault(env.msgname, env)
    return states[tick], msgs


def test_all_six_message_types_present():
    _, msgs = _one_tick_messages()
    assert set(msgs) >= {
        "HEARTBEAT", "GLOBAL_POSITION_INT", "ATTITUDE",
        "VFR_HUD", "SYS_STATUS", "GPS_RAW_INT",
    }


def test_position_roundtrip_within_noise():
    state, msgs = _one_tick_messages()
    gp = msgs["GLOBAL_POSITION_INT"].fields
    assert abs(gp["lat"] / 1e7 - state.lat) < 1e-4  # ~ few metres of GPS noise
    assert abs(gp["lon"] / 1e7 - state.lon) < 1e-4


def test_source_ids_are_vehicle():
    _, msgs = _one_tick_messages()
    for env in msgs.values():
        assert env.sysid == 1
        assert env.compid == 1


def test_baro_and_gps_alt_are_independent_channels():
    state, msgs = _one_tick_messages()
    gps_alt = msgs["GLOBAL_POSITION_INT"].fields["alt"] / 1000.0
    baro_alt = msgs["VFR_HUD"].fields["alt"]
    # both track true altitude but via different (noisy) channels
    assert abs(gps_alt - state.alt_msl) < 5.0
    assert abs(baro_alt - state.baro_alt) < 5.0
