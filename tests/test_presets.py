import pytest
from ios_loc.presets import (
    DEFAULT_PROFILES,
    MAX_SPEED_MPS,
    ConfigError,
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


def test_preset_referencing_unknown_profile_is_rejected(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[presets.x]\nwaypoints = [[25.0, 121.0], [25.1, 121.1]]\nprofile = "typoo"\n'
    )
    with pytest.raises(ConfigError, match="unknown profile"):
        load_config(cfg)


def test_preset_can_reference_a_profile_defined_in_the_same_file(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[profiles.jog]\nspeed = 2.6\n\n'
        '[presets.x]\nwaypoints = [[25.0, 121.0], [25.1, 121.1]]\nprofile = "jog"\n'
    )
    _profiles, presets = load_config(cfg)
    assert presets["x"].profile == "jog"


def test_missing_waypoints_names_the_preset(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('[presets.home]\nprofile = "walk"\n')
    with pytest.raises(ConfigError, match="home"):
        load_config(cfg)


def test_flat_waypoint_list_is_rejected(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("[presets.x]\nwaypoints = [25.0, 121.0]\n")
    with pytest.raises(ConfigError):
        load_config(cfg)


def test_three_element_waypoint_is_rejected(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("[presets.x]\nwaypoints = [[25.0, 121.0, 10.0], [25.1, 121.1]]\n")
    with pytest.raises(ConfigError, match="waypoint 0"):
        load_config(cfg)


def test_out_of_range_coordinates_are_rejected(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("[presets.x]\nwaypoints = [[999.0, 121.0], [25.1, 121.1]]\n")
    with pytest.raises(ConfigError, match="out of range"):
        load_config(cfg)


def test_non_numeric_speed_names_the_profile(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('[profiles.broken]\nspeed = "fast"\n')
    with pytest.raises(ConfigError, match="broken"):
        load_config(cfg)


def test_inverted_pause_range_is_rejected():
    with pytest.raises(ValueError, match="pause_min_s"):
        Profile(
            name="bad", speed=1.3, jitter=0.08, pause_per_min=0.1,
            pause_min_s=30, pause_max_s=5, costing="pedestrian",
        )


def test_negative_jitter_is_rejected():
    with pytest.raises(ValueError, match="jitter"):
        Profile(
            name="bad", speed=1.3, jitter=-0.5, pause_per_min=0.1,
            pause_min_s=5, pause_max_s=30, costing="pedestrian",
        )


def test_negative_pause_per_min_is_rejected():
    with pytest.raises(ValueError, match="pause_per_min"):
        Profile(
            name="bad", speed=1.3, jitter=0.08, pause_per_min=-1.0,
            pause_min_s=5, pause_max_s=30, costing="pedestrian",
        )
