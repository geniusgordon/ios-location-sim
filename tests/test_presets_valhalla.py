from ios_loc.presets import load_valhalla_url
from ios_loc.routing import DEFAULT_VALHALLA_URL


def test_loading_the_url_from_a_missing_file_is_the_default(tmp_path):
    assert load_valhalla_url(tmp_path / "nope.toml") == DEFAULT_VALHALLA_URL


def test_a_config_with_no_valhalla_table_is_the_default(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[presets.a]\nwaypoints = [[1.0, 2.0], [3.0, 4.0]]\n")
    assert load_valhalla_url(path) == DEFAULT_VALHALLA_URL


def test_a_valhalla_table_with_no_base_url_is_the_default(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[valhalla]\n")
    assert load_valhalla_url(path) == DEFAULT_VALHALLA_URL


def test_loading_a_configured_base_url(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[valhalla]\nbase_url = "http://localhost:8002"\n')
    assert load_valhalla_url(path) == "http://localhost:8002"
