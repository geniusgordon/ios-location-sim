"""`resolve_walk` — and specifically that a pace can never move a route.

Pace and costing were one field until they were split apart. The failure mode
that split fixed is silent: picking `bike` for its speed also re-planned the
route onto cycleways, and nothing in the output said so. These tests pin the
independence in both directions so it cannot quietly re-couple.
"""

import pytest

from ios_loc.presets import (
    DEFAULT_COSTING,
    DEFAULT_PACES,
    ConfigError,
    Preset,
    resolve_walk,
)

TWO = [(25.0, 121.0), (25.1, 121.1)]


def resolve(**overrides):
    """`resolve_walk` with the boring arguments filled in."""
    kwargs = dict(
        preset=None,
        waypoints=TWO,
        path=None,
        pace=None,
        speed=None,
        costing=None,
        loop=None,
        paces=DEFAULT_PACES,
        presets={},
    )
    kwargs.update(overrides)
    return resolve_walk(**kwargs)


# -- a pace decides speed, and only speed ------------------------------------


def test_an_adhoc_route_defaults_to_the_default_costing():
    assert resolve().costing == DEFAULT_COSTING


@pytest.mark.parametrize("pace", sorted(DEFAULT_PACES))
def test_no_pace_changes_the_costing_of_an_adhoc_route(pace):
    resolved = resolve(pace=pace)
    assert resolved.pace.name == pace
    assert resolved.costing == DEFAULT_COSTING


def test_the_bike_pace_is_faster_but_still_pedestrian():
    # The exact case that used to re-route silently.
    walk = resolve(pace="walk")
    bike = resolve(pace="bike")
    assert bike.pace.speed > walk.pace.speed
    assert bike.costing == walk.costing == DEFAULT_COSTING


def test_an_explicit_costing_does_not_change_the_pace():
    resolved = resolve(costing="auto")
    assert resolved.costing == "auto"
    assert resolved.pace == DEFAULT_PACES["walk"]


# -- a preset carries its own costing ----------------------------------------


def preset_config(**kwargs):
    preset = Preset(name="riverside", waypoints=TWO, **kwargs)
    return {"preset": "riverside", "waypoints": None, "presets": {"riverside": preset}}


def test_a_preset_supplies_the_costing_it_was_saved_with():
    resolved = resolve(**preset_config(costing="bicycle"))
    assert resolved.costing == "bicycle"
    assert resolved.preset_name == "riverside"


def test_an_explicit_costing_overrides_the_presets_own():
    assert resolve(**preset_config(costing="bicycle"), costing="auto").costing == "auto"


def test_overriding_a_presets_pace_leaves_its_costing_alone():
    # Walking a route that was planned for bicycles is a legitimate request;
    # it must not silently re-plan the route as a side effect.
    resolved = resolve(**preset_config(costing="bicycle", pace="bike"), pace="walk")
    assert resolved.pace.name == "walk"
    assert resolved.costing == "bicycle"


def test_a_preset_saved_without_a_costing_falls_back_to_the_default():
    assert resolve(**preset_config()).costing == DEFAULT_COSTING


# -- the surrounding rules still hold ----------------------------------------


def test_speed_override_still_hits_the_ceiling():
    with pytest.raises(ValueError, match="ceiling"):
        resolve(speed=30.0)


def test_an_unknown_pace_is_a_config_error():
    with pytest.raises(ConfigError, match="unknown pace"):
        resolve(pace="sprint")


# -- a literal path skips routing entirely ------------------------------------


def test_a_path_resolves_to_a_literal_walk():
    resolved = resolve(waypoints=None, path=TWO)
    assert resolved.waypoints == TWO
    assert resolved.literal is True
    assert resolved.preset_name is None


def test_waypoints_and_presets_are_not_literal():
    assert resolve().literal is False
    assert resolve(**preset_config()).literal is False


def test_a_path_still_defaults_pace_and_loop_like_adhoc_waypoints():
    resolved = resolve(waypoints=None, path=TWO)
    assert resolved.pace.name == "walk"
    assert resolved.loop is False


def test_a_path_needs_at_least_two_points():
    with pytest.raises(ValueError, match="at least 2"):
        resolve(waypoints=None, path=[(25.0, 121.0)])


def test_a_path_still_validates_coordinate_range():
    with pytest.raises(ValueError, match="out of range"):
        resolve(waypoints=None, path=[(200.0, 121.0), (25.1, 121.1)])


def test_preset_and_path_together_is_rejected():
    with pytest.raises(ValueError, match="exactly one"):
        resolve(**preset_config(), path=TWO)


def test_waypoints_and_path_together_is_rejected():
    with pytest.raises(ValueError, match="exactly one"):
        resolve(path=TWO)


def test_none_of_preset_waypoints_or_path_is_rejected():
    with pytest.raises(ValueError, match="needs a preset"):
        resolve(waypoints=None)
