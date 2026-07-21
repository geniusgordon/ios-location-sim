import asyncio

import pytest

from ios_loc.path import Path
from ios_loc.presets import DEFAULT_PROFILES
from ios_loc.web.models import WalkState
from ios_loc.web.service import StartSpec, WalkAlreadyRunning, WalkService

SQUARE = [(25.000, 121.000), (25.002, 121.000), (25.002, 121.002), (25.000, 121.002)]


class FakeRouteClient:
    """Stands in for ValhallaClient. Records calls, never touches the network."""

    def __init__(self, coords=None, error=None):
        self.coords = coords or SQUARE
        self.error = error
        self.calls = []

    def route(self, waypoints, costing):
        self.calls.append((list(waypoints), costing))
        if self.error is not None:
            raise self.error
        return Path(self.coords)


class FakeSession:
    """A LocationSession-shaped double. `fail_with` raises on the Nth set()."""

    def __init__(self, fail_with=None, fail_on=None):
        self.sets = []
        self.reconnects = 0
        self.started = False
        self.stopped = False
        self.cleared = None
        self._fail_with = fail_with
        self._fail_on = fail_on

    async def start(self, attempts=3):
        self.started = True

    async def stop(self, clear=True):
        self.stopped = True
        self.cleared = clear

    async def set(self, lat, lon, deadline=None):
        self.sets.append((lat, lon))
        if self._fail_with is not None and len(self.sets) == self._fail_on:
            raise self._fail_with


class VirtualClock:
    """Monotonic time that only advances when sleep() is awaited.

    Same shape as the one in tests/test_runner.py, with one difference: it yields
    to the event loop after advancing. Without that yield an unbounded walk would
    spin the loop and starve every other task in the test.
    """

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    async def sleep(self, seconds):
        self.now += max(seconds, 0.0)
        await asyncio.sleep(0)


def make_service(session=None, route_client=None, **kwargs):
    """Build a service on virtual time unless the caller overrides clock/sleep."""
    session = session or FakeSession()
    clock = VirtualClock()
    kwargs.setdefault("clock", clock)
    kwargs.setdefault("sleep", clock.sleep)
    return (
        WalkService(
            route_client=route_client or FakeRouteClient(),
            session_factory=lambda: session,
            **kwargs,
        ),
        session,
    )


def spec(**kwargs):
    return StartSpec(
        waypoints=[SQUARE[0], SQUARE[-1]],
        costing="pedestrian",
        profile=DEFAULT_PROFILES["walk"],
        **kwargs,
    )


async def test_idle_before_anything_starts():
    service, _ = make_service()
    assert service.status().state is WalkState.IDLE


async def test_start_runs_the_walk_to_its_duration():
    service, session = make_service()
    await service.start(spec(duration_s=5.0))
    await service.wait_finished()

    status = service.status()
    assert status.state is WalkState.FINISHED
    assert status.stats.ticks == 5
    assert len(session.sets) == 5
    assert session.stopped is True


async def test_status_exposes_the_routed_polyline():
    service, _ = make_service()
    await service.start(spec(duration_s=1.0))
    await service.wait_finished()
    assert service.status().route == [[lat, lon] for lat, lon in SQUARE]


async def test_second_start_while_running_is_refused():
    service, _ = make_service()
    await service.start(spec(duration_s=5.0))
    with pytest.raises(WalkAlreadyRunning):
        await service.start(spec(duration_s=5.0))
    await service.stop()


async def test_stop_ends_the_run_and_clears_the_device():
    service, session = make_service()
    await service.start(spec())  # no duration — runs until stopped
    await service.stop()
    assert service.status().state is WalkState.IDLE
    assert session.cleared is True
