import pytest
from typer.testing import CliRunner

from ios_loc.cli import app, parse_duration, parse_waypoint

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
    assert "at least 2" in result.stdout
