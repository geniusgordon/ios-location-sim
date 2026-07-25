import asyncio

import pytest

from ios_loc.presets import DEFAULT_PACES
from ios_loc.session import SessionLost
from ios_loc.web.models import WalkState, WalkStatus
from ios_loc.web.service import StartSpec, WalkAlreadyRunning, WalkService
from tests.conftest import SQUARE, FakeRouteClient, FakeSession, VirtualClock


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
        pace=DEFAULT_PACES["walk"],
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
            t for t in asyncio.all_tasks() - tasks_before - {asyncio.current_task()} if not t.done()
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
    # Exactly at capacity: nothing ever drained the queue, so drop-oldest must
    # have kept it full throughout, not emptied it. `<= 4` alone would also
    # pass for a queue that dropped everything -- only the exact count plus
    # the newest-survives check below actually pins down drop-oldest behaviour.
    assert len(messages) == 4
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


async def test_a_routing_failure_during_start_resets_to_idle_with_an_error():
    """Before the fix, everything between `self._state = STARTING` and the
    drive task being published sat outside the try/except that resets state on
    failure, so a routing failure (or any other error in that window) left the
    service wedged in STARTING forever with no `error` set (Finding 1)."""
    from ios_loc.routing import RoutingError

    route_client = FakeRouteClient(error=RoutingError("valhalla said no"))
    service, _ = make_service(route_client=route_client)

    with pytest.raises(RoutingError):
        await service.start(spec())

    status = service.status()
    assert status.state is WalkState.IDLE
    assert status.error is not None
    assert "valhalla said no" in status.error

    # The service must still be usable afterwards -- not permanently wedged.
    route_client.error = None
    await service.start(spec(duration_s=1.0))
    await service.wait_finished()
    assert service.status().state is WalkState.FINISHED


async def test_a_failed_start_broadcasts_the_error():
    """`start()` sets self._error before raising, but a live WebSocket client
    only learns about state through `_broadcast`. Before the fix, the failure
    path returned (via `raise`) before reaching the single `_broadcast` call at
    the end of `start()`, so a subscribed client never heard about the failed
    run at all -- only a subsequent `GET /api/walk` would reveal it."""
    from ios_loc.routing import RoutingError

    route_client = FakeRouteClient(error=RoutingError("valhalla said no"))
    service, _ = make_service(route_client=route_client)

    with service.subscribe() as queue:
        with pytest.raises(RoutingError):
            await service.start(spec())
        messages = _drain(queue)

    assert messages, "a subscriber must be told a start() failed"
    last = messages[-1]
    assert last["type"] == "state"
    assert last["state"] == WalkState.IDLE.value
    assert last["error"] is not None
    assert "valhalla said no" in last["error"]


async def test_stop_clears_a_lingering_error_with_no_run():
    """A failed start() leaves self._error set with self._run at None. Before
    the fix, `stop()` returned immediately when `run is None`, so the only way
    to clear that error was a later *successful* start() -- `DELETE /api/walk`
    could not dismiss it, leaving a GUI stuck showing a stale failure."""
    from ios_loc.routing import RoutingError

    route_client = FakeRouteClient(error=RoutingError("valhalla said no"))
    service, _ = make_service(route_client=route_client)

    with pytest.raises(RoutingError):
        await service.start(spec())
    assert service.status().error is not None

    await service.stop()
    assert service.status().error is None
    assert service.status().state is WalkState.IDLE


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


async def test_the_final_broadcast_carries_the_authoritative_stats():
    """A WebSocket-only consumer must learn the final numbers without having
    to re-`GET /api/walk` (Finding 3): the terminal broadcast carries `stats`
    alongside `state`, not just a bare state message."""
    service, _ = make_service()
    with service.subscribe() as queue:
        await service.start(spec(duration_s=3.0))
        await service.wait_finished()
        messages = _drain(queue)

    final = messages[-1]
    assert final["type"] == "state"
    assert final["state"] == "finished"
    assert final["stats"] == service.status().stats.model_dump()
    assert final["stats"]["ticks"] == 3


async def test_the_final_broadcast_reflects_the_true_tick_count_on_session_lost():
    """`run.ticks` (incremented in `_on_fix`, i.e. only on a *successful* set())
    and `run_walk`'s own `ticks` (incremented *before* `session.set()`, so it
    counts the failing attempt too) diverge by one when a tick ends in
    `SessionLost`. The terminal broadcast must carry the authoritative
    `run_walk` count, not the one `_on_fix` last saw -- so it can legitimately
    jump by more than one fix's worth relative to the last per-fix broadcast.
    """
    session = FakeSession(fail_with=SessionLost("device unreachable"), fail_on=3)
    service, _ = make_service(session=session)
    with service.subscribe() as queue:
        await service.start(spec(duration_s=10.0))
        await service.wait_finished()
        messages = _drain(queue)

    fixes = [m for m in messages if m["type"] == "fix"]
    # Only 2 fixes ever reached _on_fix -- the 3rd tick's set() failed before
    # on_fix could run.
    assert len(fixes) == 2
    assert fixes[-1]["stats"]["ticks"] == 2

    final = messages[-1]
    assert final["type"] == "state"
    assert final["state"] == "error"
    # The authoritative final count includes the failed 3rd attempt.
    assert final["stats"]["ticks"] == 3
    assert final["stats"] == service.status().stats.model_dump()


async def test_a_slow_set_reports_reconnecting():
    """The watchdog must drive its own polling off the injected clock/sleep,
    not real wall time -- so a test can force a "stall" deterministically
    without ever actually waiting in real time.

    `SlowSession.set()` blocks on a real `asyncio.Event` (a pure concurrency
    gate, not a timer) until the test releases it, standing in for a
    `session.set()` stuck mid-reconnect. While it's blocked, the tick loop
    (inside `run_walk`) is itself suspended awaiting that very call, so it
    advances no virtual time at all -- only the watchdog's own polling loop
    can, which is exactly the situation `_watch_stalls` exists to detect.
    Pumping the event loop with bare `asyncio.sleep(0)` yields (no real delay)
    must be enough for the watchdog to notice and flip the state.
    """
    gate = asyncio.Event()

    class SlowSession(FakeSession):
        async def set(self, lat, lon, deadline=None):
            await gate.wait()
            await super().set(lat, lon)

    service, _ = make_service(session=SlowSession(), stall_threshold_s=1.0)
    with service.subscribe() as queue:
        await service.start(spec(duration_s=5.0))
        # No real waiting: just pump the loop so the watchdog's own virtual
        # sleeps get a chance to run while `set()` sits blocked on the gate.
        for _ in range(10):
            await asyncio.sleep(0)
        assert service.status().state is WalkState.RECONNECTING
        gate.set()
        await service.wait_finished()
        states = [m["state"] for m in _drain(queue) if m["type"] == "state"]
    assert "reconnecting" in states


async def test_pin_holds_the_session_and_reports_pinned():
    session = FakeSession()
    service, _ = make_service(session=session)
    status = await service.pin(48.858666, 2.293991)
    assert status.state is WalkState.PINNED
    assert status.fix is not None
    assert (status.fix.lat, status.fix.lon) == (48.858666, 2.293991)
    assert status.fix.speed_mps == 0
    assert status.fix.distance_m == 0
    assert status.stats is None
    assert status.route == []
    # The session is held open (set once, never stopped) until stop().
    assert session.sets == [(48.858666, 2.293991)]
    assert session.stopped is False


async def test_stop_clears_a_pin():
    session = FakeSession()
    service, _ = make_service(session=session)
    await service.pin(48.858666, 2.293991)
    await service.stop()
    assert session.stopped is True
    assert session.cleared is True
    assert service.status().state is WalkState.IDLE


async def test_re_pinning_reuses_the_open_session():
    session = FakeSession()
    service, _ = make_service(session=session)
    await service.pin(48.858666, 2.293991)
    await service.pin(25.0, 121.0)
    # One session, two sets, still open.
    assert session.start_calls == 1
    assert session.sets == [(48.858666, 2.293991), (25.0, 121.0)]
    assert session.stopped is False


async def test_pin_while_walking_is_refused():
    gate = asyncio.Event()
    session = FakeSession(start_gate=gate)
    service, _ = make_service(session=session)
    # Start a walk and leave it mid-connect so a walk is unambiguously active.
    task = asyncio.create_task(service.start(spec()))
    await session.entered_start.wait()
    gate.set()
    await task
    with pytest.raises(WalkAlreadyRunning):
        await service.pin(48.858666, 2.293991)
    await service.stop()


async def test_pin_passes_a_bounded_deadline_to_set():
    # Without a deadline, session.set()'s max_attempts=0 retries forever and
    # the HTTP request would never return -- pin() must bound it the same
    # way run_walk bounds a walk's set() calls.
    session = FakeSession()
    service, _ = make_service(session=session, pin_timeout_s=8.0)
    await service.pin(48.858666, 2.293991)
    assert session.set_deadlines == [8.0]  # VirtualClock starts at 0.0


async def test_pin_fails_fast_when_set_reports_session_lost():
    class LostSession(FakeSession):
        async def set(self, lat, lon, deadline=None):
            await super().set(lat, lon, deadline=deadline)
            raise SessionLost("device unreachable at deadline")

    session = LostSession()
    service, _ = make_service(session=session)
    with pytest.raises(SessionLost):
        await service.pin(48.858666, 2.293991)
    assert service.status().state is WalkState.IDLE
    assert service.status().error is not None
    assert "SessionLost" in service.status().error
    # The half-open session must not linger as the held pin.
    assert service._pin_session is None


async def test_pin_tears_down_the_session_on_device_failure():
    session = FakeSession(fail_with=RuntimeError("device unreachable"), fail_on=1)
    service, _ = make_service(session=session)
    with pytest.raises(RuntimeError):
        await service.pin(48.858666, 2.293991)
    # The half-open session was cleaned up, and the service is idle with the
    # failure recorded.
    assert session.stopped is True
    assert service.status().state is WalkState.IDLE
    assert service.status().error is not None


async def test_pin_over_a_finished_run_clears_the_stale_run():
    session = FakeSession()
    service, _ = make_service(session=session)
    await service.start(spec(duration_s=5.0))
    await service.wait_finished()
    assert service.status().state is WalkState.FINISHED

    # No intervening stop() -- pin() must not let the leftover finished run
    # shadow the pin in status().
    status = await service.pin(48.858666, 2.293991)
    assert status.state is WalkState.PINNED
    assert status.fix is not None
    assert (status.fix.lat, status.fix.lon) == (48.858666, 2.293991)
    assert status.route == []
    assert status.trail == []

    status = service.status()
    assert status.state is WalkState.PINNED
    assert (status.fix.lat, status.fix.lon) == (48.858666, 2.293991)
    assert status.route == []
    assert status.trail == []

    await service.stop()
    status = service.status()
    assert status.state is WalkState.IDLE
    assert status.route == []


async def test_starting_a_walk_replaces_a_pin():
    pin_session = FakeSession()
    walk_session = FakeSession()
    sessions = iter([pin_session, walk_session])
    service, _ = make_service(session=pin_session)
    service._session_factory = lambda: next(sessions)  # pin gets one, walk the next
    await service.pin(48.858666, 2.293991)
    await service.start(spec())
    # The pinned session was released (stopped, not cleared) and the walk owns
    # its own session now.
    assert pin_session.stopped is True
    assert pin_session.cleared is False
    assert service.status().state is WalkState.WALKING
    await service.stop()
