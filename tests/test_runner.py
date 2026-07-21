import random
import pytest
from contextlib import asynccontextmanager

from ios_loc.path import Path
from ios_loc.presets import DEFAULT_PROFILES
from ios_loc.runner import run_walk
from ios_loc.session import LocationSession
from ios_loc.walker import Walker


class VirtualClock:
    """A monotonic clock that only advances when sleep() is awaited."""

    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    async def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += max(seconds, 0.0)


class RecordingSim:
    def __init__(self, fail_on=()):
        self.fail_on = set(fail_on)
        self.sets = []
        self.cleared = False
        self._n = 0

    async def set(self, lat, lon):
        self._n += 1
        if self._n in self.fail_on:
            raise ConnectionError("dropped")
        self.sets.append((lat, lon))

    async def clear(self):
        self.cleared = True


def make_session(sim, sleep):
    @asynccontextmanager
    async def opener():
        yield sim

    return LocationSession(opener, sleep=sleep)


def make_walker(loop=True):
    path = Path([(0.0, 0.0), (0.01, 0.0)])
    return Walker(path, DEFAULT_PROFILES["walk"], loop=loop, rng=random.Random(0), scatter_m=0.0)


async def test_runs_for_the_requested_duration():
    clock = VirtualClock()
    sim = RecordingSim()
    session = make_session(sim, clock.sleep)
    await session.start()
    stats = await run_walk(
        make_walker(), session, duration_s=60.0, clock=clock, sleep=clock.sleep
    )
    assert stats.ticks == 60
    assert len(sim.sets) == 60


async def test_ticks_are_anchored_to_absolute_deadlines():
    """Slow per-tick work must shorten the next sleep, not extend the walk."""
    clock = VirtualClock()
    sim = RecordingSim()

    async def slow_set(lat, lon):
        clock.now += 0.3  # simulate 300 ms of work inside the tick
        sim.sets.append((lat, lon))

    sim.set = slow_set
    session = make_session(sim, clock.sleep)
    await session.start()
    await run_walk(make_walker(), session, duration_s=10.0, clock=clock, sleep=clock.sleep)
    # Each sleep compensates for the 0.3 s spent working.
    assert all(s == pytest.approx(0.7, abs=0.01) for s in clock.sleeps[1:10])


async def test_walk_clock_freezes_during_an_outage():
    """A reconnect must not advance the walker — that would be a teleport."""
    clock = VirtualClock()
    sim = RecordingSim(fail_on={5})
    session = make_session(sim, clock.sleep)
    await session.start()
    walker = make_walker()
    stats = await run_walk(
        walker, session, duration_s=20.0, clock=clock, sleep=clock.sleep
    )
    assert session.reconnects == 1
    # 20 ticks requested; the walker advanced exactly once per tick, no extra.
    assert stats.ticks == 20
    assert walker.distance_m == pytest.approx(stats.distance_m)
    # Distance reflects 20 ticks of walking, not the wall time lost to backoff.
    assert stats.distance_m < 20 * 1.3 * 1.5


async def test_stops_when_a_non_looping_walker_finishes():
    clock = VirtualClock()
    sim = RecordingSim()
    session = make_session(sim, clock.sleep)
    await session.start()
    path = Path([(0.0, 0.0), (0.0005, 0.0)])  # ~55 m
    walker = Walker(
        path, DEFAULT_PROFILES["walk"], loop=False, rng=random.Random(0), scatter_m=0.0
    )
    stats = await run_walk(walker, session, duration_s=None, clock=clock, sleep=clock.sleep)
    assert walker.finished
    assert stats.ticks < 120


async def test_on_fix_callback_receives_every_fix():
    clock = VirtualClock()
    sim = RecordingSim()
    session = make_session(sim, clock.sleep)
    await session.start()
    seen = []
    await run_walk(
        make_walker(),
        session,
        duration_s=5.0,
        clock=clock,
        sleep=clock.sleep,
        on_fix=seen.append,
    )
    assert len(seen) == 5
    assert seen[-1].elapsed_s == pytest.approx(5.0)
