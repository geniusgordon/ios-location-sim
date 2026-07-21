import asyncio
import time

import pytest

from ios_loc.path import Path
from ios_loc.presets import DEFAULT_PROFILES
from ios_loc.session import SessionLost
from ios_loc.web.models import WalkState, WalkStatus
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
    """A LocationSession-shaped double. `fail_with` raises on the Nth set().

    `start_gate`, if given, makes `start()` a slow, controllable connect: it
    signals `entered_start` the instant it's called (so a test can know it is
    "mid-connect" without guessing timing) and then blocks until the gate is
    set.
    """

    def __init__(self, fail_with=None, fail_on=None, start_gate=None, stop_gate=None):
        self.sets = []
        self.reconnects = 0
        self.started = False
        self.stopped = False
        self.cleared = None
        self.stop_calls = 0
        self.start_calls = 0
        self._fail_with = fail_with
        self._fail_on = fail_on
        self._start_gate = start_gate
        self.entered_start = asyncio.Event()
        # `stop_gate`, if given, makes the *first* stop() call block until the
        # gate resolves (or is cancelled out from under it) -- so a test can
        # suspend a teardown mid-`await` without guessing timing. Only the
        # first call blocks: a retried stop() after a cancelled attempt must
        # proceed and actually clear the device, which is the whole point of
        # the interrupted-teardown test.
        self._stop_gate = stop_gate
        self._stop_gate_consumed = False
        self.entered_stop = asyncio.Event()

    async def start(self, attempts=3):
        self.start_calls += 1
        self.entered_start.set()
        if self._start_gate is not None:
            await self._start_gate.wait()
        self.started = True

    async def stop(self, clear=True):
        self.entered_stop.set()
        if self._stop_gate is not None and not self._stop_gate_consumed:
            self._stop_gate_consumed = True
            await self._stop_gate.wait()
        self.stop_calls += 1
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


async def test_finished_walk_can_be_restarted_without_stop():
    service, session = make_service()
    await service.start(spec(duration_s=5.0))
    await service.wait_finished()
    assert service.status().state is WalkState.FINISHED

    # No intervening stop() — a finished run must not permanently block start().
    await service.start(spec(duration_s=3.0))
    await service.wait_finished()

    status = service.status()
    assert status.state is WalkState.FINISHED
    assert status.stats.ticks == 3
    # The second walk actually drove the session again (5 ticks from the first
    # walk, plus 3 more from the second).
    assert len(session.sets) == 8


async def test_status_reports_finished_stats_until_next_start():
    service, _ = make_service()
    await service.start(spec(duration_s=5.0))
    await service.wait_finished()

    status = service.status()
    assert status.state is WalkState.FINISHED
    assert status.stats is not None
    assert status.stats.ticks == 5
    assert status.fix is not None


async def test_stop_after_natural_finish_does_not_stop_session_twice():
    service, session = make_service()
    await service.start(spec(duration_s=5.0))
    await service.wait_finished()
    assert session.stop_calls == 1

    await service.stop()
    assert session.stop_calls == 1
    assert service.status().state is WalkState.IDLE


async def test_second_start_while_genuinely_running_still_refused():
    service, _ = make_service()
    await service.start(spec(duration_s=5.0))
    with pytest.raises(WalkAlreadyRunning):
        await service.start(spec(duration_s=5.0))
    await service.stop()


async def test_concurrent_start_calls_exactly_one_wins():
    """Two overlapping POST /api/walk: exactly one call should win.

    Before the fix, `start()`'s guard reads `self._run` before the loser has
    published its own `_Run`, so both calls can race past it, each build its
    own walker/session, and both end up creating a drive task -- the second
    one unreachable from status()/stop() forever.
    """
    gate = asyncio.Event()
    sessions = []

    def factory():
        s = FakeSession(start_gate=gate)
        sessions.append(s)
        return s

    clock = VirtualClock()
    service = WalkService(
        route_client=FakeRouteClient(),
        session_factory=factory,
        clock=clock,
        sleep=clock.sleep,
    )

    async def release_gate():
        # Wait until the first start() call has actually begun connecting...
        while not sessions or not sessions[0].entered_start.is_set():
            await asyncio.sleep(0)
        # ...then give a second, racing start() call room to either join the
        # race (bug) or be rejected outright (fixed) before we unblock either.
        for _ in range(5):
            await asyncio.sleep(0)
        gate.set()

    results = await asyncio.gather(
        service.start(spec(duration_s=5.0)),
        service.start(spec(duration_s=5.0)),
        release_gate(),
        return_exceptions=True,
    )
    outcomes = results[:2]
    successes = [r for r in outcomes if isinstance(r, WalkStatus)]
    failures = [r for r in outcomes if isinstance(r, WalkAlreadyRunning)]

    assert len(successes) == 1, "exactly one concurrent start() call should win"
    assert len(failures) == 1, "the loser must raise WalkAlreadyRunning"
    assert len(sessions) == 1, "the loser must never build a second device session"
    assert sessions[0].started is True

    await service.wait_finished()
    status = service.status()
    assert status.state is WalkState.FINISHED
    assert status.stats.ticks == 5
    assert len(sessions[0].sets) == 5, "exactly one drive loop should have run"

    await service.stop()


async def test_stop_racing_a_slow_connecting_start_leaves_a_consistent_state():
    """DELETE racing a POST that is still awaiting session.start().

    Before the fix, `stop()` sees `run.task is None` (it's only assigned
    after `session.start()` returns), skips the cancel, tears the session
    down, and reports IDLE -- but the in-flight start() resumes regardless,
    publishes a task, and flips the state back to WALKING with `self._run`
    left at None. The result is a live, unreachable drive loop with the
    service reporting the wrong (or at least an inconsistent) state.
    """
    gate = asyncio.Event()
    session = FakeSession(start_gate=gate)
    clock = VirtualClock()
    service = WalkService(
        route_client=FakeRouteClient(),
        session_factory=lambda: session,
        clock=clock,
        sleep=clock.sleep,
    )

    tasks_before = asyncio.all_tasks()

    async def stop_then_release():
        # Don't touch stop() until start() is genuinely mid-connect.
        await session.entered_start.wait()
        stop_task = asyncio.create_task(service.stop())
        await asyncio.sleep(0)  # let stop() queue up (on the lock, once fixed)
        gate.set()  # let the in-flight session.start() finally resolve
        await stop_task

    try:
        await asyncio.gather(service.start(spec()), stop_then_release())

        # Give any orphaned drive loop a few virtual ticks to reveal itself.
        for _ in range(3):
            await asyncio.sleep(0)

        status = service.status()
        assert status.state is WalkState.IDLE, (
            "service must not report a state that contradicts self._run"
        )
        assert session.stop_calls == 1, "the session must be stopped exactly once"

        orphans = {
            t
            for t in asyncio.all_tasks() - tasks_before - {asyncio.current_task()}
            if not t.done()
        }
        assert not orphans, "a drive loop survived stop() with no way to reach it"
    finally:
        for t in asyncio.all_tasks() - tasks_before - {asyncio.current_task()}:
            if not t.done():
                t.cancel()


async def test_subscribers_receive_one_message_per_fix():
    service, _ = make_service()
    with service.subscribe() as queue:
        await service.start(spec(duration_s=3.0))
        await service.wait_finished()
        messages = _drain(queue)

    fixes = [m for m in messages if m["type"] == "fix"]
    assert len(fixes) == 3
    assert fixes[0]["fix"]["elapsed_s"] == 1.0
    assert fixes[-1]["stats"]["ticks"] == 3


async def test_a_full_queue_drops_oldest_and_never_blocks_the_walk():
    service, session = make_service(queue_size=4)
    with service.subscribe() as queue:
        await service.start(spec(duration_s=20.0))
        await service.wait_finished()
        messages = _drain(queue)

    # The run completes all 20 ticks regardless of the stalled subscriber.
    assert len(session.sets) == 20
    assert len(messages) <= 4
    # What survives is the newest, not the oldest.
    assert messages[-1]["type"] == "state"
    assert messages[-1]["state"] == "finished"


async def test_unsubscribing_removes_the_queue():
    service, _ = make_service()
    with service.subscribe() as queue:
        pass
    assert queue not in service._subscribers


def _drain(queue):
    out = []
    while not queue.empty():
        out.append(queue.get_nowait())
    return out


async def test_device_lost_is_reported_as_an_error_not_a_clean_finish():
    session = FakeSession(fail_with=SessionLost("device unreachable"), fail_on=3)
    service, _ = make_service(session=session)
    await service.start(spec(duration_s=10.0))
    await service.wait_finished()

    status = service.status()
    assert status.state is WalkState.ERROR
    assert "unreachable" in status.error


async def test_programming_errors_end_the_run_and_surface_the_type():
    session = FakeSession(fail_with=TypeError("bad argument"), fail_on=2)
    service, _ = make_service(session=session)
    await service.start(spec(duration_s=10.0))
    await service.wait_finished()

    status = service.status()
    assert status.state is WalkState.ERROR
    assert "TypeError" in status.error
    assert len(session.sets) == 2  # it did not retry the bug


async def test_teardown_interrupted_mid_await_is_retried_not_skipped():
    """A concurrent stop() cancelling the drive task while it is suspended
    inside its own natural-finish teardown must not leave the device
    un-cleared.

    Sequence: the walk finishes naturally, so `_drive`'s `finally` calls
    `_teardown`, which calls `session.stop()` and blocks (the gate). While
    it's blocked, a `service.stop()` call (e.g. the user hitting stop right
    as the walk ends) cancels the still-running drive task. That delivers
    CancelledError into the suspended `session.stop()` call -- the clear
    never happened on this attempt. `service.stop()` then calls `_teardown`
    again itself; that second call must actually retry the clear rather than
    finding `torn_down` already (wrongly) latched.
    """
    gate = asyncio.Event()
    session = FakeSession(stop_gate=gate)
    service, _ = make_service(session=session)

    await service.start(spec(duration_s=1.0))
    # Let the walk run to its natural finish; _drive's own finally then calls
    # _teardown, which calls session.stop() and suspends inside the gate.
    await session.entered_stop.wait()
    assert session.cleared is None, "the first, blocked stop() call has not completed yet"

    # A concurrent DELETE /api/walk cancels the still-running drive task
    # while it is suspended in that very await.
    await service.stop()

    assert session.cleared is True, "the interrupted teardown must be retried, not skipped"
    assert service.status().state is WalkState.IDLE


async def test_a_slow_set_reports_reconnecting():
    class SlowSession(FakeSession):
        async def set(self, lat, lon, deadline=None):
            await asyncio.sleep(0.2)
            await super().set(lat, lon)

    # Real time, not the virtual clock: the stall is measured in wall seconds
    # precisely because the tick loop is frozen and advances no virtual time.
    service, _ = make_service(
        session=SlowSession(),
        stall_threshold_s=0.05,
        clock=time.monotonic,
        sleep=asyncio.sleep,
    )
    with service.subscribe() as queue:
        await service.start(spec(duration_s=1.0))
        await asyncio.sleep(0.12)
        assert service.status().state is WalkState.RECONNECTING
        await service.wait_finished()
        states = [m["state"] for m in _drain(queue) if m["type"] == "state"]
    assert "reconnecting" in states
