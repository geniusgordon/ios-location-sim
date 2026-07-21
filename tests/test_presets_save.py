import pathlib

import pytest

from ios_loc.presets import ConfigError, Preset, load_config, save_preset

CONFIG_WITH_COMMENTS = """\
# my hand-written config — this comment must survive
[profiles.jog]
speed = 2.6  # trailing comment
costing = "pedestrian"

[presets.old]
waypoints = [[25.0, 121.0], [25.1, 121.1]]
profile = "jog"
"""


def test_saving_into_a_missing_file_creates_it(tmp_path):
    path = tmp_path / "nested" / "config.toml"
    save_preset(path, Preset(name="new", waypoints=[(25.0, 121.0), (25.1, 121.1)]))

    _, presets = load_config(path)
    assert presets["new"].waypoints == [(25.0, 121.0), (25.1, 121.1)]
    assert presets["new"].profile == "walk"
    assert presets["new"].loop is False


def test_saving_preserves_profiles_and_comments_verbatim(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(CONFIG_WITH_COMMENTS)

    save_preset(path, Preset(name="new", waypoints=[(1.0, 2.0), (3.0, 4.0)], profile="jog"))

    text = path.read_text()
    assert "# my hand-written config — this comment must survive" in text
    assert "speed = 2.6  # trailing comment" in text

    profiles, presets = load_config(path)
    assert profiles["jog"].speed == 2.6
    assert set(presets) == {"old", "new"}


def test_saving_an_existing_name_replaces_it(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(CONFIG_WITH_COMMENTS)

    save_preset(path, Preset(name="old", waypoints=[(9.0, 9.0), (8.0, 8.0)], loop=True))

    _, presets = load_config(path)
    assert len(presets) == 1
    assert presets["old"].waypoints == [(9.0, 9.0), (8.0, 8.0)]
    assert presets["old"].loop is True


def test_a_preset_needing_two_waypoints_is_rejected_before_writing(tmp_path):
    path = tmp_path / "config.toml"
    with pytest.raises(ConfigError):
        save_preset(path, Preset(name="bad", waypoints=[(1.0, 2.0)]))
    assert not path.exists()


def test_the_written_file_is_reloadable_after_two_saves(tmp_path):
    path = tmp_path / "config.toml"
    save_preset(path, Preset(name="a", waypoints=[(1.0, 2.0), (3.0, 4.0)]))
    save_preset(path, Preset(name="b", waypoints=[(5.0, 6.0), (7.0, 8.0)], loop=True))

    _, presets = load_config(path)
    assert set(presets) == {"a", "b"}
    assert presets["b"].loop is True


def test_multiline_array_with_no_trailing_comma_on_last_element_is_not_mistaken_for_a_header(
    tmp_path,
):
    # The last element of a multi-line array, with no trailing comma, looks
    # exactly like "[<content>]" — the same shape as a table header. If the
    # stripper is fooled by it, it stops dropping mid-[presets.old] and lets
    # "profile = \"jog\"" (and anything after it) leak through untouched.
    path = tmp_path / "config.toml"
    path.write_text(
        "[profiles.jog]\n"
        'speed = 2.6\n'
        'costing = "pedestrian"\n'
        "\n"
        "[presets.old]\n"
        "waypoints = [\n"
        "    [25.0, 121.0],\n"
        "    [25.1, 121.1]\n"
        "]\n"
        'profile = "jog"\n'
    )

    save_preset(path, Preset(name="new", waypoints=[(1.0, 2.0), (3.0, 4.0)]))

    profiles, presets = load_config(path)
    assert set(presets) == {"old", "new"}
    assert profiles["jog"].speed == 2.6


def test_a_quoted_key_containing_a_bracket_does_not_truncate_the_header_match(tmp_path):
    # A quoted TOML key may legally contain "]"; a naive "everything up to the
    # first ']'" scan would treat that as the end of the header and misread
    # the rest of the line.
    path = tmp_path / "config.toml"
    path.write_text('[profiles."my]profile"]\nspeed = 1.5\n')

    profiles, _ = load_config(path)
    assert profiles['my]profile'].speed == 1.5

    save_preset(path, Preset(name="new", waypoints=[(1.0, 2.0), (3.0, 4.0)]))

    text = path.read_text()
    assert '[profiles."my]profile"]' in text
    profiles, presets = load_config(path)
    assert profiles['my]profile'].speed == 1.5
    assert set(presets) == {"new"}


def test_crlf_line_endings_round_trip(tmp_path):
    path = tmp_path / "config.toml"
    path.write_bytes(
        b"# a windows-authored config\r\n"
        b"[profiles.jog]\r\n"
        b"speed = 2.6\r\n"
        b"\r\n"
        b"[presets.old]\r\n"
        b'waypoints = [[25.0, 121.0], [25.1, 121.1]]\r\n'
    )

    save_preset(path, Preset(name="new", waypoints=[(1.0, 2.0), (3.0, 4.0)]))

    text = path.read_text()
    assert "# a windows-authored config" in text
    profiles, presets = load_config(path)
    assert profiles["jog"].speed == 2.6
    assert set(presets) == {"old", "new"}


def test_a_presets_parent_table_with_no_children_is_dropped(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[profiles.jog]\nspeed = 2.6\n\n[presets]\n")

    save_preset(path, Preset(name="new", waypoints=[(1.0, 2.0), (3.0, 4.0)]))

    profiles, presets = load_config(path)
    assert profiles["jog"].speed == 2.6
    assert set(presets) == {"new"}


def test_a_preset_table_as_the_last_thing_in_the_file_is_fully_dropped(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        "[profiles.jog]\n"
        "speed = 2.6\n"
        "\n"
        "[presets.old]\n"
        "waypoints = [[25.0, 121.0], [25.1, 121.1]]\n"
        'profile = "jog"\n'
    )

    save_preset(path, Preset(name="new", waypoints=[(1.0, 2.0), (3.0, 4.0)]))

    profiles, presets = load_config(path)
    assert profiles["jog"].speed == 2.6
    assert set(presets) == {"old", "new"}
