import pytest
from ios_loc.presets import (
    DEFAULT_PROFILES,
    MAX_SPEED_MPS,
    Profile,
    load_config,
)


def test_ceiling_is_20_kmh():
    assert MAX_SPEED_MPS == pytest.approx(5.56, abs=0.01)
    assert MAX_SPEED_MPS * 3.6 == pytest.approx(20.0, abs=0.05)


def test_builtin_profiles_exist_and_are_under_the_ceiling():
    assert set(DEFAULT_PROFILES) >= {"walk", "bike"}
    for profile in DEFAULT_PROFILES.values():
        assert profile.speed <= MAX_SPEED_MPS


def test_walk_and_bike_select_different_costing():
    assert DEFAULT_PROFILES["walk"].costing == "pedestrian"
    assert DEFAULT_PROFILES["bike"].costing == "bicycle"


def test_profile_rejects_speed_over_ceiling():
    with pytest.raises(ValueError):
        Profile(
            name="car",
            speed=30.0,
            jitter=0.1,
            pause_per_min=0.0,
            pause_min_s=5,
            pause_max_s=10,
            costing="auto",
        )


def test_missing_config_file_yields_defaults(tmp_path):
    profiles, presets = load_config(tmp_path / "nope.toml")
    assert profiles == DEFAULT_PROFILES
    assert presets == {}


def test_config_adds_profile_and_preset(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
[profiles.jog]
speed = 2.6
jitter = 0.1
pause_per_min = 0.01
pause_min_s = 5
pause_max_s = 20
costing = "pedestrian"

[presets.home-loop]
waypoints = [[25.033, 121.5654], [25.038, 121.568], [25.033, 121.5654]]
profile = "walk"
loop = true
"""
    )
    profiles, presets = load_config(cfg)
    assert profiles["jog"].speed == pytest.approx(2.6)
    assert profiles["walk"] == DEFAULT_PROFILES["walk"]  # builtins still present
    preset = presets["home-loop"]
    assert preset.loop is True
    assert preset.profile == "walk"
    assert preset.waypoints[0] == (25.033, 121.5654)


def test_config_profile_over_ceiling_is_rejected(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('[profiles.fast]\nspeed = 12.0\ncosting = "auto"\n')
    with pytest.raises(ValueError):
        load_config(cfg)
