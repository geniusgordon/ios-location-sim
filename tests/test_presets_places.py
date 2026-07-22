import pytest

from ios_loc.presets import ConfigError, Place, delete_place, load_config, load_places, save_place

CONFIG = """\
[places.home]
point = [25.033, 121.565]

[places."my office"]
point = [25.041, 121.544]
"""


def test_loading_places_from_a_missing_file_is_empty(tmp_path):
    assert load_places(tmp_path / "nope.toml") == {}


def test_loading_places_reads_every_table(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(CONFIG)

    places = load_places(path)
    assert set(places) == {"home", "my office"}
    assert places["home"] == Place(name="home", point=(25.033, 121.565))


def test_a_config_with_no_places_table_loads_as_empty(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[presets.a]\nwaypoints = [[1.0, 2.0], [3.0, 4.0]]\n')
    assert load_places(path) == {}


def test_a_place_missing_its_point_is_a_config_error(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[places.home]\n")
    with pytest.raises(ConfigError, match="point"):
        load_places(path)


@pytest.mark.parametrize(
    "raw",
    ['point = [25.0]', 'point = "here"', 'point = [25.0, "x"]'],
)
def test_a_malformed_point_is_a_config_error(tmp_path, raw):
    path = tmp_path / "config.toml"
    path.write_text(f"[places.home]\n{raw}\n")
    with pytest.raises(ConfigError, match="home"):
        load_places(path)


def test_an_out_of_range_point_is_a_config_error(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[places.home]\npoint = [125.0, 121.0]\n")
    with pytest.raises(ConfigError, match="out of range"):
        load_places(path)


MIXED_CONFIG = """\
# hand-written header — must survive
[profiles.jog]
speed = 2.6  # trailing comment

[presets.old]
waypoints = [[25.0, 121.0], [25.1, 121.1]]
profile = "jog"

[places.home]
point = [25.033, 121.565]
"""


def test_saving_a_place_into_a_missing_file_creates_it(tmp_path):
    path = tmp_path / "nested" / "config.toml"
    save_place(path, Place(name="home", point=(25.0, 121.0)))
    assert load_places(path)["home"].point == (25.0, 121.0)


def test_saving_a_place_preserves_presets_profiles_and_comments(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(MIXED_CONFIG)

    save_place(path, Place(name="office", point=(1.0, 2.0)))

    text = path.read_text()
    assert "# hand-written header — must survive" in text
    assert "speed = 2.6  # trailing comment" in text
    profiles, presets = load_config(path)
    assert profiles["jog"].speed == 2.6
    assert presets["old"].waypoints == [(25.0, 121.0), (25.1, 121.1)]
    assert set(load_places(path)) == {"home", "office"}


def test_saving_an_existing_place_name_replaces_it(tmp_path):
    path = tmp_path / "config.toml"
    save_place(path, Place(name="home", point=(1.0, 2.0)))
    save_place(path, Place(name="home", point=(3.0, 4.0)))
    places = load_places(path)
    assert list(places) == ["home"]
    assert places["home"].point == (3.0, 4.0)


def test_saving_an_out_of_range_place_writes_nothing(tmp_path):
    path = tmp_path / "config.toml"
    with pytest.raises(ConfigError, match="out of range"):
        save_place(path, Place(name="bad", point=(125.0, 0.0)))
    assert not path.exists()


def test_deleting_a_place_leaves_the_rest_intact(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(MIXED_CONFIG)
    save_place(path, Place(name="office", point=(1.0, 2.0)))

    delete_place(path, "home")

    assert set(load_places(path)) == {"office"}
    _, presets = load_config(path)
    assert set(presets) == {"old"}


def test_deleting_the_last_place_leaves_no_places_header(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(MIXED_CONFIG)

    delete_place(path, "home")

    assert load_places(path) == {}
    assert "[places" not in path.read_text()
    assert "# hand-written header — must survive" in path.read_text()


def test_deleting_an_unknown_place_raises_and_writes_nothing(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(MIXED_CONFIG)
    before = path.read_text()

    with pytest.raises(KeyError):
        delete_place(path, "nope")

    assert path.read_text() == before


def test_a_place_write_preserves_crlf_line_endings(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(MIXED_CONFIG.replace("\n", "\r\n"), newline="")

    save_place(path, Place(name="office", point=(1.0, 2.0)))

    assert "# hand-written header — must survive\r\n" in path.read_text(newline="")


def test_a_failed_place_write_leaves_no_temp_file(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_text(MIXED_CONFIG)

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("ios_loc.presets.os.replace", boom)
    with pytest.raises(OSError):
        save_place(path, Place(name="office", point=(1.0, 2.0)))

    assert list(tmp_path.glob("*.tmp")) == []
