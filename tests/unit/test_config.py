"""Config loading: defaults, YAML merge, resilience to missing files."""

from aegisflight.config import AegisConfig, load_config


def test_defaults_without_yaml(tmp_path):
    cfg = AegisConfig.load(tmp_path)  # empty dir -> pure defaults
    assert cfg.simulation["seed"] == 42
    assert cfg.detector["fusion"]["threat_threshold"] == 0.45
    assert set(cfg.attacks) >= {"gps_spoofing", "dos", "firmware_integrity"}


def test_repo_config_loads():
    cfg = load_config()
    assert cfg.simulation["sample_rate_hz"] == 10.0
    assert "protocol" in cfg.detector
    assert cfg.message_rates["ATTITUDE"] == 1


def test_yaml_overrides_defaults(tmp_path):
    (tmp_path / "simulation.yaml").write_text("seed: 7\ncruise_alt_m: 99\n")
    cfg = AegisConfig.load(tmp_path)
    assert cfg.simulation["seed"] == 7
    assert cfg.simulation["cruise_alt_m"] == 99
    # untouched keys keep defaults
    assert cfg.simulation["sample_rate_hz"] == 10.0
