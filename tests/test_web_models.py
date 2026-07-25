from ios_loc.presets import Preset
from ios_loc.runner import WalkStats
from ios_loc.walker import Fix
from ios_loc.web.models import FixOut, PresetOut, StatsOut, WalkState, WalkStatus


def test_fix_out_carries_every_field():
    fix = Fix(elapsed_s=12.0, lat=25.033, lon=121.565, distance_m=15.6, speed_mps=1.3, paused=False)
    out = FixOut.from_fix(fix)
    assert out.model_dump() == {
        "elapsed_s": 12.0,
        "lat": 25.033,
        "lon": 121.565,
        "distance_m": 15.6,
        "speed_mps": 1.3,
        "paused": False,
    }


def test_stats_out_carries_every_field():
    stats = WalkStats(elapsed_s=60.0, distance_m=78.0, laps=1, reconnects=2, ticks=60)
    out = StatsOut.from_stats(stats)
    assert out.model_dump() == {
        "elapsed_s": 60.0,
        "distance_m": 78.0,
        "laps": 1,
        "reconnects": 2,
        "ticks": 60,
    }


def test_preset_out_flattens_waypoints_to_lists():
    preset = Preset(name="home", waypoints=[(25.0, 121.0), (25.1, 121.1)], pace="bike", loop=True)
    out = PresetOut.from_preset(preset)
    assert out.model_dump() == {
        "name": "home",
        "waypoints": [[25.0, 121.0], [25.1, 121.1]],
        "pace": "bike",
        "loop": True,
        # A saved route owns its costing; `bike` as a pace does not imply one.
        "costing": "pedestrian",
    }


def test_idle_status_has_no_fix_or_stats():
    status = WalkStatus(state=WalkState.IDLE)
    assert status.state == "idle"
    assert status.fix is None
    assert status.stats is None
    assert status.route == []
    assert status.trail == []
    assert status.error is None
