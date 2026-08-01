import pytest
from typer.testing import CliRunner

from ios_loc import cli
from ios_loc.cli import app, parse_duration, parse_waypoint
from ios_loc.routing import RoutingError

runner = CliRunner()


def test_parse_waypoint_accepts_lat_comma_lon():
    assert parse_waypoint("25.033,121.5654") == (25.033, 121.5654)


def test_parse_waypoint_tolerates_whitespace():
    assert parse_waypoint(" 25.033 , 121.5654 ") == (25.033, 121.5654)


def test_parse_waypoint_rejects_garbage():
    with pytest.raises(ValueError):
        parse_waypoint("taipei")


def test_parse_waypoint_rejects_out_of_range():
    with pytest.raises(ValueError):
        parse_waypoint("125.0,121.0")


@pytest.mark.parametrize(
    "text,expected",
    [("30s", 30.0), ("15m", 900.0), ("3h", 10800.0), ("90", 90.0)],
)
def test_parse_duration(text, expected):
    assert parse_duration(text) == expected


def test_parse_duration_rejects_garbage():
    with pytest.raises(ValueError):
        parse_duration("soon")


def test_help_lists_all_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("doctor", "walk", "set", "clear", "presets"):
        assert command in result.stdout


def test_walk_rejects_fewer_than_two_waypoints():
    result = runner.invoke(app, ["walk", "--via", "25.033,121.565"])
    assert result.exit_code != 0
    assert result.stdout.strip() == (
        "a route needs at least 2 waypoints — pass --via 'lat,lon' twice"
    )


def test_walk_rejects_no_arguments():
    result = runner.invoke(app, ["walk"])
    assert result.exit_code != 0
    assert result.stdout.strip() == (
        "a walk needs a preset, at least 2 waypoints, or a path — pass --via 'lat,lon' twice"
    )


def test_walk_rejects_preset_and_via_together(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("[presets.home]\nwaypoints = [[25.0, 121.0], [25.1, 121.1]]\n")
    result = runner.invoke(app, ["walk", "home", "--via", "25.0,121.0", "--config", str(cfg)])
    assert result.exit_code != 0
    assert result.stdout.strip() == "pass either a preset name or --via waypoints, not both"


def test_walk_rejects_preset_and_via_together_even_when_via_is_malformed(tmp_path):
    # The preset/--via conflict is the more useful message: it must be reported
    # even when the (irrelevant, since it will be rejected anyway) --via value
    # is not a parseable waypoint. Pins the check-before-parse ordering.
    cfg = tmp_path / "config.toml"
    cfg.write_text("[presets.home]\nwaypoints = [[25.0, 121.0], [25.1, 121.1]]\n")
    result = runner.invoke(app, ["walk", "home", "--via", "garbage", "--config", str(cfg)])
    assert result.exit_code != 0
    assert result.stdout.strip() == "pass either a preset name or --via waypoints, not both"


def test_walk_help_exposes_no_clear_and_no_loop():
    result = runner.invoke(app, ["walk", "--help"])
    assert result.exit_code == 0
    assert "--no-clear" in result.stdout
    assert "--no-loop" in result.stdout


def test_bad_log_path_reports_cleanly(tmp_path):
    # A file where a directory is expected: mkdir must fail, not traceback.
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file")
    result = runner.invoke(
        app,
        [
            "walk",
            "--via",
            "25.033,121.565",
            "--via",
            "25.038,121.568",
            "--log",
            str(blocker / "sub" / "run.log"),
        ],
    )
    assert result.exit_code != 0
    assert "Traceback" not in result.stdout


class _FakeValhallaClient:
    """Captures the `base_url` it was built with, then fails routing --
    enough to verify what `walk` passed to `ValhallaClient` without needing a
    real device session."""

    captured_base_url: str | None = None

    def __init__(self, base_url, offline=False):
        type(self).captured_base_url = base_url

    def route(self, waypoints, costing):
        raise RoutingError("stop here -- routing is not under test")


def test_walk_valhalla_url_falls_back_to_the_config_table(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "ValhallaClient", _FakeValhallaClient)
    config = tmp_path / "config.toml"
    config.write_text('[valhalla]\nbase_url = "http://config-server:8002"\n')

    result = runner.invoke(
        app,
        ["walk", "--via", "25.0,121.0", "--via", "25.1,121.1", "--config", str(config)],
    )

    assert result.exit_code != 0
    assert _FakeValhallaClient.captured_base_url == "http://config-server:8002"


def test_walk_valhalla_url_flag_overrides_the_config_table(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "ValhallaClient", _FakeValhallaClient)
    config = tmp_path / "config.toml"
    config.write_text('[valhalla]\nbase_url = "http://config-server:8002"\n')

    result = runner.invoke(
        app,
        [
            "walk",
            "--via",
            "25.0,121.0",
            "--via",
            "25.1,121.1",
            "--config",
            str(config),
            "--valhalla-url",
            "http://flag-server:9000",
        ],
    )

    assert result.exit_code != 0
    assert _FakeValhallaClient.captured_base_url == "http://flag-server:9000"
