import random
import pytest
from ios_loc.path import Path, haversine_m
from ios_loc.presets import DEFAULT_PROFILES, MAX_SPEED_MPS, Profile
from ios_loc.walker import Walker

WALK = DEFAULT_PROFILES["walk"]


def straight_path(length_deg=0.01):
    # ~1.1 km north-south line at the equator.
    return Path([(0.0, 0.0), (length_deg, 0.0)])


def no_pause(profile: Profile) -> Profile:
    from dataclasses import replace

    return replace(profile, pause_per_min=0.0)


def test_distance_accumulates_at_base_speed_without_jitter():
    profile = no_pause(Profile(**{**WALK.__dict__, "jitter": 0.0}))
    w = Walker(straight_path(), profile, rng=random.Random(0), scatter_m=0.0)
    for _ in range(100):
        w.advance(1.0)
    assert w.distance_m == pytest.approx(130.0, rel=1e-6)  # 100 s * 1.3 m/s


def test_elapsed_tracks_total_dt():
    w = Walker(straight_path(), no_pause(WALK), rng=random.Random(0))
    for _ in range(60):
        fix = w.advance(1.0)
    assert fix.elapsed_s == pytest.approx(60.0)


def test_speed_never_exceeds_ceiling_even_with_extreme_jitter():
    hot = Profile(
        name="hot",
        speed=MAX_SPEED_MPS,
        jitter=5.0,  # absurd, to stress the clamp
        pause_per_min=0.0,
        pause_min_s=1,
        pause_max_s=2,
        costing="bicycle",
    )
    w = Walker(straight_path(1.0), hot, loop=True, rng=random.Random(1))
    for _ in range(10_000):
        fix = w.advance(1.0)
        assert fix.speed_mps <= MAX_SPEED_MPS + 1e-9


def test_speed_is_never_negative():
    profile = no_pause(Profile(**{**WALK.__dict__, "jitter": 3.0}))
    w = Walker(straight_path(1.0), profile, loop=True, rng=random.Random(2))
    for _ in range(5_000):
        assert w.advance(1.0).speed_mps >= 0.0


def test_positions_never_teleport():
    # Scatter off, so this pins the movement model itself deterministically:
    # no step may ever exceed the speed ceiling.
    w = Walker(straight_path(1.0), WALK, loop=True, rng=random.Random(3), scatter_m=0.0)
    prev = None
    for _ in range(2_000):
        fix = w.advance(1.0)
        cur = (fix.lat, fix.lon)
        if prev is not None:
            assert haversine_m(prev, cur) <= MAX_SPEED_MPS * 1.0 + 1e-6
        prev = cur


def test_scatter_stays_within_a_sane_envelope():
    # With scatter on, consecutive points differ by the true step PLUS the
    # difference of two independent 2-axis Gaussians (~sqrt(2)*sigma per axis).
    # Bound at 10*sigma so a Gaussian tail can never flake the suite.
    scatter = 3.0
    w = Walker(straight_path(1.0), WALK, loop=True, rng=random.Random(3), scatter_m=scatter)
    prev = None
    for _ in range(2_000):
        fix = w.advance(1.0)
        cur = (fix.lat, fix.lon)
        if prev is not None:
            assert haversine_m(prev, cur) <= MAX_SPEED_MPS * 1.0 + 10 * scatter
        prev = cur


def test_jitter_produces_varying_speed():
    w = Walker(straight_path(1.0), no_pause(WALK), loop=True, rng=random.Random(4), scatter_m=0.0)
    speeds = {round(w.advance(1.0).speed_mps, 6) for _ in range(200)}
    assert len(speeds) > 100  # not a constant


def test_pauses_occur_and_freeze_distance():
    always_pause = Profile(**{**WALK.__dict__, "pause_per_min": 60.0})
    w = Walker(straight_path(1.0), always_pause, loop=True, rng=random.Random(5), scatter_m=0.0)
    saw_pause = False
    for _ in range(300):
        before = w.distance_m
        fix = w.advance(1.0)
        if fix.paused:
            saw_pause = True
            assert fix.speed_mps == 0.0
            assert w.distance_m == pytest.approx(before)
    assert saw_pause


def test_loop_wraps_without_discontinuity():
    path = straight_path(0.001)  # ~111 m
    profile = no_pause(Profile(**{**WALK.__dict__, "jitter": 0.0}))
    w = Walker(path, profile, loop=True, rng=random.Random(6), scatter_m=0.0)
    prev = None
    for _ in range(500):
        fix = w.advance(1.0)
        cur = (fix.lat, fix.lon)
        if prev is not None:
            assert haversine_m(prev, cur) <= MAX_SPEED_MPS * 1.0 + 1e-6
        prev = cur
    assert w.laps >= 2


def test_non_loop_finishes_at_end_of_path():
    path = straight_path(0.0005)  # ~55 m
    profile = no_pause(Profile(**{**WALK.__dict__, "jitter": 0.0}))
    w = Walker(path, profile, loop=False, rng=random.Random(7), scatter_m=0.0)
    for _ in range(200):
        w.advance(1.0)
    assert w.finished
    assert w.distance_m == pytest.approx(path.length_m)


def test_scatter_perturbs_position_but_not_distance():
    profile = no_pause(Profile(**{**WALK.__dict__, "jitter": 0.0}))
    clean = Walker(straight_path(1.0), profile, loop=True, rng=random.Random(8), scatter_m=0.0)
    noisy = Walker(straight_path(1.0), profile, loop=True, rng=random.Random(8), scatter_m=5.0)
    for _ in range(50):
        a, b = clean.advance(1.0), noisy.advance(1.0)
    # Distance bookkeeping is identical...
    assert clean.distance_m == pytest.approx(noisy.distance_m)
    # ...but the emitted positions differ.
    assert (a.lat, a.lon) != (b.lat, b.lon)


def test_800m_loop_at_walking_pace_takes_about_ten_minutes():
    # A behavioural sanity check on the whole model: 800 m / 1.3 m/s ~= 615 s.
    path = straight_path(0.0036)  # ~400 m out, 800 m round trip when looped
    w = Walker(path, no_pause(WALK), loop=True, rng=random.Random(9), scatter_m=0.0)
    elapsed = 0.0
    while w.distance_m < 800.0:
        w.advance(1.0)
        elapsed += 1.0
        assert elapsed < 1200, "walker is implausibly slow"
    assert 550 < elapsed < 700


def test_distance_m_is_cumulative_not_wrapped():
    # The CLI reports this as total distance walked, so it must not reset each
    # lap: 600 s at 1.3 m/s is 780 m however short the underlying path is.
    profile = no_pause(Profile(**{**WALK.__dict__, "jitter": 0.0}))
    w = Walker(straight_path(0.001), profile, loop=True, rng=random.Random(0), scatter_m=0.0)
    for _ in range(600):
        w.advance(1.0)
    assert w.distance_m == pytest.approx(780.0, rel=1e-6)
    assert w.laps >= 5


def test_open_path_loop_retraces_instead_of_teleporting():
    # An A->B route with --loop must bounce B->A->B, never jump back to A.
    profile = no_pause(Profile(**{**WALK.__dict__, "jitter": 0.0}))
    w = Walker(straight_path(0.001), profile, loop=True, rng=random.Random(0), scatter_m=0.0)
    lats = [w.advance(1.0).lat for _ in range(400)]
    peak = lats.index(max(lats))
    assert max(lats) > 0.0009, "should reach the far end of the route"
    assert min(lats[peak:]) < 0.0005, "should retrace back toward the start"
    for a, b in zip(lats, lats[1:]):
        assert abs(b - a) < 0.0001, "no positional jump at the turnaround"


def test_closed_loop_wraps_without_reversing():
    # A genuinely closed route wraps seamlessly by modulo, with no bounce.
    path = Path([(0.0, 0.0), (0.001, 0.0), (0.001, 0.001), (0.0, 0.0)])
    assert path.is_closed_loop
    profile = no_pause(Profile(**{**WALK.__dict__, "jitter": 0.0}))
    w = Walker(path, profile, loop=True, rng=random.Random(0), scatter_m=0.0)
    prev = None
    for _ in range(500):
        fix = w.advance(1.0)
        cur = (fix.lat, fix.lon)
        if prev is not None:
            assert haversine_m(prev, cur) <= MAX_SPEED_MPS + 1e-6
        prev = cur
    assert w.laps >= 1
