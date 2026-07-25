import pytest

from ios_loc.presets import (
    DEFAULT_PACES,
    MAX_SPEED_MPS,
    ConfigError,
    Pace,
    load_config,
)


def test_ceiling_is_20_kmh():
    assert pytest.approx(5.56, abs=0.01) == MAX_SPEED_MPS
    assert pytest.approx(20.0, abs=0.05) == MAX_SPEED_MPS * 3.6


def test_builtin_paces_exist_and_are_under_the_ceiling():
    assert set(DEFAULT_PACES) >= {"walk", "bike"}
    for pace in DEFAULT_PACES.values():
        assert pace.speed <= MAX_SPEED_MPS


def test_a_pace_carries_no_costing():
    # The whole point of the pace/costing split: picking `bike` for its speed
    # must not be able to re-route anything. If a costing ever reappears on
    # Pace, resolve_walk will start inheriting it again and the two settings
    # silently re-couple.
    assert not hasattr(DEFAULT_PACES["walk"], "costing")
    assert DEFAULT_PACES["bike"].speed > DEFAULT_PACES["walk"].speed


def test_pace_rejects_speed_over_ceiling():
    with pytest.raises(ValueError):
        Pace(
            name="car",
            speed=30.0,
            jitter=0.1,
            pause_per_min=0.0,
            pause_min_s=5,
            pause_max_s=10,
        )


def test_missing_config_file_yields_defaults(tmp_path):
    paces, presets = load_config(tmp_path / "nope.toml")
    assert paces == DEFAULT_PACES
    assert presets == {}


def test_config_adds_pace_and_preset(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
[paces.jog]
speed = 2.6
jitter = 0.1
pause_per_min = 0.01
pause_min_s = 5
pause_max_s = 20

[presets.home-loop]
waypoints = [[25.033, 121.5654], [25.038, 121.568], [25.033, 121.5654]]
pace = "walk"
loop = true
"""
    )
    paces, presets = load_config(cfg)
    assert paces["jog"].speed == pytest.approx(2.6)
    assert paces["walk"] == DEFAULT_PACES["walk"]  # builtins still present
    preset = presets["home-loop"]
    assert preset.loop is True
    assert preset.pace == "walk"
    assert preset.waypoints[0] == (25.033, 121.5654)


def test_config_pace_over_ceiling_is_rejected(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("[paces.fast]\nspeed = 12.0\n")
    with pytest.raises(ValueError):
        load_config(cfg)


def test_preset_referencing_unknown_pace_is_rejected(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('[presets.x]\nwaypoints = [[25.0, 121.0], [25.1, 121.1]]\npace = "typoo"\n')
    with pytest.raises(ConfigError, match="unknown pace"):
        load_config(cfg)


def test_preset_can_reference_a_pace_defined_in_the_same_file(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        "[paces.jog]\nspeed = 2.6\n\n"
        '[presets.x]\nwaypoints = [[25.0, 121.0], [25.1, 121.1]]\npace = "jog"\n'
    )
    _paces, presets = load_config(cfg)
    assert presets["x"].pace == "jog"


def test_missing_waypoints_names_the_preset(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('[presets.home]\npace = "walk"\n')
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


def test_non_numeric_speed_names_the_pace(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('[paces.broken]\nspeed = "fast"\n')
    with pytest.raises(ConfigError, match="broken"):
        load_config(cfg)


def test_inverted_pause_range_is_rejected():
    with pytest.raises(ValueError, match="pause_min_s"):
        Pace(
            name="bad",
            speed=1.3,
            jitter=0.08,
            pause_per_min=0.1,
            pause_min_s=30,
            pause_max_s=5,
        )


def test_negative_jitter_is_rejected():
    with pytest.raises(ValueError, match="jitter"):
        Pace(
            name="bad",
            speed=1.3,
            jitter=-0.5,
            pause_per_min=0.1,
            pause_min_s=5,
            pause_max_s=30,
        )


def test_negative_pause_per_min_is_rejected():
    with pytest.raises(ValueError, match="pause_per_min"):
        Pace(
            name="bad",
            speed=1.3,
            jitter=0.08,
            pause_per_min=-1.0,
            pause_min_s=5,
            pause_max_s=30,
        )
