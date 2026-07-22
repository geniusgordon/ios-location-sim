import pytest

from ios_loc.presets import ConfigError, Place, load_places

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
