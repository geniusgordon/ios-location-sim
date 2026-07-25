import pathlib

import pytest

from ios_loc.presets import (
    DEFAULT_COSTING,
    ConfigError,
    Preset,
    delete_preset,
    load_config,
    save_preset,
)

CONFIG_WITH_COMMENTS = """\
# my hand-written config — this comment must survive
[paces.jog]
speed = 2.6  # trailing comment

[presets.old]
waypoints = [[25.0, 121.0], [25.1, 121.1]]
pace = "jog"
"""


def test_saving_into_a_missing_file_creates_it(tmp_path):
    path = tmp_path / "nested" / "config.toml"
    save_preset(path, Preset(name="new", waypoints=[(25.0, 121.0), (25.1, 121.1)]))

    _, presets = load_config(path)
    assert presets["new"].waypoints == [(25.0, 121.0), (25.1, 121.1)]
    assert presets["new"].pace == "walk"
    assert presets["new"].loop is False
    assert presets["new"].costing == DEFAULT_COSTING


def test_a_presets_costing_round_trips_through_the_file(tmp_path):
    # The costing describes the saved geometry, so it has to survive the file --
    # a route drawn as `bicycle` that reloads as `pedestrian` re-plans into a
    # different polyline than the one the user saved.
    path = tmp_path / "config.toml"
    save_preset(
        path,
        Preset(name="cycleway", waypoints=[(1.0, 2.0), (3.0, 4.0)], costing="bicycle"),
    )

    _, presets = load_config(path)
    assert presets["cycleway"].costing == "bicycle"
    # ...and it is independent of the pace, which stayed at its default.
    assert presets["cycleway"].pace == "walk"


def test_saving_preserves_paces_and_comments_verbatim(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(CONFIG_WITH_COMMENTS)

    save_preset(path, Preset(name="new", waypoints=[(1.0, 2.0), (3.0, 4.0)], pace="jog"))

    text = path.read_text()
    assert "# my hand-written config — this comment must survive" in text
    assert "speed = 2.6  # trailing comment" in text

    paces, presets = load_config(path)
    assert paces["jog"].speed == 2.6
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
    # "pace = \"jog\"" (and anything after it) leak through untouched.
    path = tmp_path / "config.toml"
    path.write_text(
        "[paces.jog]\n"
        'speed = 2.6\n'
        'jitter = 0.1\n'
        "\n"
        "[presets.old]\n"
        "waypoints = [\n"
        "    [25.0, 121.0],\n"
        "    [25.1, 121.1]\n"
        "]\n"
        'pace = "jog"\n'
    )

    save_preset(path, Preset(name="new", waypoints=[(1.0, 2.0), (3.0, 4.0)]))

    paces, presets = load_config(path)
    assert set(presets) == {"old", "new"}
    assert paces["jog"].speed == 2.6


def test_a_quoted_key_containing_a_bracket_does_not_truncate_the_header_match(tmp_path):
    # A quoted TOML key may legally contain "]"; a naive "everything up to the
    # first ']'" scan would treat that as the end of the header and misread
    # the rest of the line.
    path = tmp_path / "config.toml"
    path.write_text('[paces."my]pace"]\nspeed = 1.5\n')

    paces, _ = load_config(path)
    assert paces['my]pace'].speed == 1.5

    save_preset(path, Preset(name="new", waypoints=[(1.0, 2.0), (3.0, 4.0)]))

    text = path.read_text()
    assert '[paces."my]pace"]' in text
    paces, presets = load_config(path)
    assert paces['my]pace'].speed == 1.5
    assert set(presets) == {"new"}


def test_crlf_line_endings_round_trip(tmp_path):
    path = tmp_path / "config.toml"
    path.write_bytes(
        b"# a windows-authored config\r\n"
        b"[paces.jog]\r\n"
        b"speed = 2.6  # trailing comment\r\n"
        b'jitter = 0.1\r\n'
        b"\r\n"
        b"[presets.old]\r\n"
        b"waypoints = [[25.0, 121.0], [25.1, 121.1]]\r\n"
    )

    save_preset(path, Preset(name="new", waypoints=[(1.0, 2.0), (3.0, 4.0)]))

    raw = path.read_bytes()
    # The preserved head (everything outside [presets.*]) must keep its
    # original CRLF bytes verbatim -- not just "the comment is present
    # somewhere", but the literal "\r\n" sequence around it. (The very last
    # kept line's own trailing newline is deliberately normalized by the
    # pre-existing `rstrip()` before the regenerated [presets.*] block is
    # appended, same as for an LF file, so we assert on lines that are not
    # the last one -- the bug this test guards against is universal-newline
    # translation on read/write, not that intentional normalization.)
    assert b"# a windows-authored config\r\n" in raw
    assert b"[paces.jog]\r\n" in raw
    assert b"speed = 2.6  # trailing comment\r\n" in raw

    text = path.read_text()
    assert "# a windows-authored config" in text
    paces, presets = load_config(path)
    assert paces["jog"].speed == 2.6
    assert set(presets) == {"old", "new"}


def test_an_unknown_pace_is_rejected_before_writing(tmp_path):
    path = tmp_path / "config.toml"
    with pytest.raises(ConfigError):
        save_preset(path, Preset(name="bad", waypoints=[(1.0, 2.0), (3.0, 4.0)], pace="nope"))
    assert not path.exists()


def test_an_unknown_pace_leaves_an_existing_file_byte_identical(tmp_path):
    path = tmp_path / "config.toml"
    path.write_bytes(CONFIG_WITH_COMMENTS.encode())
    before = path.read_bytes()

    with pytest.raises(ConfigError):
        save_preset(path, Preset(name="bad", waypoints=[(1.0, 2.0), (3.0, 4.0)], pace="nope"))

    assert path.read_bytes() == before


def test_a_presets_parent_table_with_no_children_is_dropped(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[paces.jog]\nspeed = 2.6\n\n[presets]\n")

    save_preset(path, Preset(name="new", waypoints=[(1.0, 2.0), (3.0, 4.0)]))

    paces, presets = load_config(path)
    assert paces["jog"].speed == 2.6
    assert set(presets) == {"new"}


def test_a_preset_table_as_the_last_thing_in_the_file_is_fully_dropped(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        "[paces.jog]\n"
        "speed = 2.6\n"
        "\n"
        "[presets.old]\n"
        "waypoints = [[25.0, 121.0], [25.1, 121.1]]\n"
        'pace = "jog"\n'
    )

    save_preset(path, Preset(name="new", waypoints=[(1.0, 2.0), (3.0, 4.0)]))

    paces, presets = load_config(path)
    assert paces["jog"].speed == 2.6
    assert set(presets) == {"old", "new"}


def test_save_preset_cannot_repair_existing_invalid_config_with_unknown_pace_reference(
    tmp_path,
):
    """Verify documented limitation: save_preset raises ConfigError if the existing
    config file references a pace that no longer exists, and leaves the file untouched.

    This documents that save_preset validates its *own* preset before writing, but
    cannot repair a file that is *already* broken. The file must be fixed by hand.
    """
    path = tmp_path / "config.toml"
    # Create a config with a preset that references a pace we'll delete
    path.write_text(
        "[presets.old]\n"
        "waypoints = [[25.0, 121.0], [25.1, 121.1]]\n"
        'pace = "jog"\n'
    )
    broken_bytes = path.read_bytes()

    # Now try to save a valid new preset. This should fail because load_config
    # will reject the existing preset's unknown pace reference (jog doesn't exist).
    with pytest.raises(ConfigError) as exc_info:
        save_preset(path, Preset(name="new", waypoints=[(1.0, 2.0), (3.0, 4.0)]))

    # Verify the error names the offending entry
    assert "preset" in str(exc_info.value).lower()
    assert "old" in str(exc_info.value)

    # Verify the file is left byte-identical
    assert path.read_bytes() == broken_bytes


def test_deleting_a_preset_leaves_paces_and_comments_intact(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(CONFIG_WITH_COMMENTS)
    save_preset(path, Preset(name="keep", waypoints=[(1.0, 2.0), (3.0, 4.0)], pace="jog"))

    delete_preset(path, "old")

    paces, presets = load_config(path)
    assert set(presets) == {"keep"}
    assert paces["jog"].speed == 2.6
    assert "# my hand-written config — this comment must survive" in path.read_text()


def test_deleting_the_last_preset_leaves_no_presets_header(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(CONFIG_WITH_COMMENTS)

    delete_preset(path, "old")

    _, presets = load_config(path)
    assert presets == {}
    assert "[presets" not in path.read_text()
    assert "speed = 2.6  # trailing comment" in path.read_text()


def test_deleting_an_unknown_preset_raises_and_writes_nothing(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(CONFIG_WITH_COMMENTS)
    before = path.read_text()

    with pytest.raises(KeyError):
        delete_preset(path, "nope")

    assert path.read_text() == before
