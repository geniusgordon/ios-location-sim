"""Owns at most one running walk. Asyncio only — no HTTP types cross this line."""

from __future__ import annotations

import asyncio
import collections
import contextlib
import logging
import random
import time
from dataclasses import dataclass, field

from ios_loc.path import Coord, Path
from ios_loc.presets import Pace
from ios_loc.routing import RoutingError
from ios_loc.runner import run_walk
from ios_loc.session import SessionLost
from ios_loc.walker import Walker
from ios_loc.web.models import FixOut, StatsOut, WalkState, WalkStatus

logger = logging.getLogger(__name__)


class WalkAlreadyRunning(RuntimeError):
    """A run is already in progress; the device accepts only one."""


class RerouteNotRunning(RuntimeError):
    """A reroute needs a live walk with at least one fix to rebase from."""


@dataclass
class StartSpec:
    waypoints: list[Coord]
    costing: str
    pace: Pace
    loop: bool = False
    duration_s: float | None = None
    scatter_m: float = 3.0
    preset_name: str | None = None
    # True when `waypoints` is a literal path to walk exactly as given --
    # `start()` skips the Valhalla routing call entirely.
    literal: bool = False


@dataclass
class _Run:
    """Everything belonging to the current walk. Discarded wholesale on stop."""

    walker: Walker
    session: object
    path: Path
    spec: StartSpec
    task: asyncio.Task | None = None
    trail: collections.deque = field(default_factory=collections.deque)
    latest_fix: FixOut | None = None
    stats: StatsOut | None = None
    ticks: int = 0
    torn_down: bool = False
    watchdog: asyncio.Task | None = None


class _WatchedSession:
    """Wraps a LocationSession so the service can see what the tick loop hides.

    `run_walk` catches SessionLost and returns normally, and a stalled `set()`
    is invisible from outside. Both matter to the UI, so record them here rather
    than modifying runner.py or session.py.
    """

    def __init__(self, inner, clock) -> None:
        self._inner = inner
        self._clock = clock
        self.lost_error: BaseException | None = None
        self.inflight_since: float | None = None
        # Signals the watchdog that a `set()` call has just started, so it can
        # wake up and start polling. It carries no timing information itself --
        # only `inflight_since` does -- it exists purely so the watchdog can
        # block (consuming no clock time at all) instead of polling on a fixed
        # period for the entire life of the walk, which would race the tick
        # loop's own use of the same injected clock/sleep (see `_watch_stalls`).
        self._inflight_event = asyncio.Event()

    @property
    def reconnects(self) -> int:
        return getattr(self._inner, "reconnects", 0)

    async def start(self, attempts: int = 3) -> None:
        await self._inner.start(attempts=attempts)

    async def stop(self, clear: bool = True) -> None:
        await self._inner.stop(clear=clear)

    async def set(self, lat: float, lon: float, deadline=None) -> None:
        self.inflight_since = self._clock()
        self._inflight_event.set()
        try:
            await self._inner.set(lat, lon, deadline=deadline)
        except SessionLost as exc:
            self.lost_error = exc
            raise
        finally:
            self.inflight_since = None

    async def wait_for_inflight(self) -> None:
        """Block until a `set()` call has started, consuming no clock time."""
        await self._inflight_event.wait()
        self._inflight_event.clear()


class WalkService:
    def __init__(
        self,
        *,
        route_client,
        session_factory,
        trail_len: int = 120,
        queue_size: int = 64,
        tick_s: float = 1.0,
        clock=time.monotonic,
        sleep=asyncio.sleep,
        rng=None,
        stall_threshold_s: float = 2.0,
        pin_timeout_s: float = 8.0,
    ) -> None:
        self._route_client = route_client
        self._session_factory = session_factory
        self._trail_len = trail_len
        self._queue_size = queue_size
        self._tick_s = tick_s
        self._clock = clock
        self._sleep = sleep
        self._rng = rng if rng is not None else random.Random()
        self._stall_threshold_s = stall_threshold_s
        # `pin()` has no run duration to derive a deadline from, unlike a walk
        # (whose deadline comes from `run_walk`'s own tick loop) -- without
        # one, session.set()'s max_attempts=0 retries forever and the HTTP
        # request never returns its 503.
        self._pin_timeout_s = pin_timeout_s

        self._run: _Run | None = None
        self._state = WalkState.IDLE
        self._error: str | None = None
        # A held "set location" pin: one open session, no tick loop. Separate
        # from self._run because a pin has no walker, path, trail, or stats.
        self._pin_session: object | None = None
        self._pin_fix: FixOut | None = None
        self._subscribers: set[asyncio.Queue] = set()
        # Serializes start()/stop() against each other end-to-end -- including
        # the await on session.start() and the teardown -- so neither method
        # can observe or mutate self._run mid-transition. _drive() never
        # acquires this lock, so stop() awaiting a cancelled run.task while
        # holding it cannot deadlock.
        self._lock = asyncio.Lock()

    # -- public ----------------------------------------------------------

    def status(self) -> WalkStatus:
        run = self._run
        if run is None:
            if self._pin_fix is not None:
                return WalkStatus(state=self._state, error=self._error, fix=self._pin_fix)
            return WalkStatus(state=self._effective_state(), error=self._error)
        return WalkStatus(
            state=self._effective_state(),
            error=self._error,
            fix=run.latest_fix,
            stats=run.stats,
            route=[[lat, lon] for lat, lon in run.path.coords],
            trail=list(run.trail),
            preset_name=run.spec.preset_name,
            pace=run.spec.pace.name,
            loop=run.spec.loop,
            length_m=run.path.length_m,
        )

    async def start(self, spec: StartSpec) -> WalkStatus:
        async with self._lock:
            run = self._run
            if run is not None and run.task is not None and not run.task.done():
                raise WalkAlreadyRunning("a walk is already running")

            # Starting a walk supersedes a pin: hand the device to the walk.
            # The walk opens its own session, so the pinned one must be closed
            # here or it leaks (two owners of one device).
            if self._pin_session is not None:
                pin_session = self._pin_session
                self._pin_session = None
                self._pin_fix = None
                try:
                    await pin_session.stop(clear=False)
                except Exception as exc:  # noqa: BLE001 — must not block the start
                    logger.warning("could not release the pin before starting: %s", exc)

            self._state = WalkState.STARTING
            self._error = None
            try:
                if spec.literal:
                    # Already the final path -- no Valhalla call to make.
                    path = Path(spec.waypoints)
                else:
                    # RouteClient.route() is synchronous `requests`; keep it off the loop.
                    path = await asyncio.to_thread(
                        self._route_client.route, spec.waypoints, spec.costing
                    )

                walker = Walker(
                    path, spec.pace, loop=spec.loop, rng=self._rng, scatter_m=spec.scatter_m
                )
                session = _WatchedSession(self._session_factory(), self._clock)
                run = _Run(
                    walker=walker,
                    session=session,
                    path=path,
                    spec=spec,
                    trail=collections.deque(maxlen=self._trail_len),
                )
                self._run = run

                await session.start()

                self._state = WalkState.WALKING
                run.task = asyncio.create_task(self._drive(run), name="ios-loc-walk")
                run.watchdog = asyncio.create_task(self._watch_stalls(run), name="ios-loc-stall")
            except BaseException as exc:
                # Anything from here to "the drive task is published" — a
                # routing failure, a bad Walker/session construction, a failed
                # device connect — must not leave the service wedged in
                # STARTING forever with no explanation.
                self._run = None
                self._state = WalkState.IDLE
                self._error = f"{type(exc).__name__}: {exc}"
                if isinstance(exc, (RoutingError, ValueError)):
                    logger.warning("walk start failed: %s", exc)
                else:
                    logger.exception("walk start failed")
                self._broadcast({"type": "state", "state": self._state.value, "error": self._error})
                raise
            self._broadcast({"type": "state", "state": self._state.value, "error": None})
            return self.status()

    async def reroute(self, waypoints: list[Coord]) -> WalkStatus:
        """Extend the running walk ahead of its current live position.

        `waypoints` are only the newly-appended points -- this always routes
        `[current_fix, *waypoints]`, discarding whatever remained of the
        original plan (if the user wants the old destination too, they
        re-click it). A looping walk is refused: a route computed from an
        arbitrary live position is never a closed course, so "keep looping"
        has no sane meaning once rerouted.

        `Walker.reroute()` is synchronous and never awaits, so calling it
        here — on the same event-loop task, between two `run_walk` ticks —
        can never race the tick loop's own `advance()` calls.
        """
        async with self._lock:
            run = self._run
            if run is None or run.task is None or run.task.done():
                raise RerouteNotRunning("no walk is currently running")
            if run.spec.loop:
                raise RerouteNotRunning("cannot reroute a looping walk")
            fix = run.latest_fix
            if fix is None:
                raise RerouteNotRunning("the walk has not produced a fix yet")
            current = (fix.lat, fix.lon)
            new_path = await asyncio.to_thread(
                self._route_client.route, [current, *waypoints], run.spec.costing
            )
            run.walker.reroute(new_path)
            run.path = new_path
            self._broadcast(
                {
                    "type": "route",
                    "route": [[lat, lon] for lat, lon in new_path.coords],
                    "length_m": new_path.length_m,
                }
            )
            return self.status()

    async def pin(self, lat: float, lon: float) -> WalkStatus:
        """Hold the device at a fixed point — the GUI equivalent of `ios-loc set`.

        Owns the device like a walk does, so it takes the same lock and refuses
        to run while a walk is active. Starting a walk later simply replaces the
        pin (a pin holds no accumulated state worth protecting).
        """
        async with self._lock:
            run = self._run
            if run is not None and run.task is not None and not run.task.done():
                raise WalkAlreadyRunning("a walk is already running")
            try:
                if self._pin_session is None:
                    session = self._session_factory()
                    await session.start()
                    self._pin_session = session
                await self._pin_session.set(lat, lon, deadline=self._clock() + self._pin_timeout_s)
            except BaseException as exc:
                # A half-open session must not leak. Clear the device, drop the
                # session, record the failure, and let the original exception
                # propagate so the API maps it (programming error -> 500,
                # device failure -> 503).
                if self._pin_session is not None:
                    try:
                        await self._pin_session.stop(clear=True)
                    except Exception as teardown_exc:  # noqa: BLE001 — teardown must not mask the cause
                        logger.warning(
                            "could not clear the device after a failed pin: %s", teardown_exc
                        )
                    self._pin_session = None
                self._pin_fix = None
                self._state = WalkState.IDLE
                self._error = f"{type(exc).__name__}: {exc}"
                self._broadcast({"type": "state", "state": self._state.value, "error": self._error})
                raise
            self._pin_fix = FixOut(
                elapsed_s=0.0, lat=lat, lon=lon, distance_m=0.0, speed_mps=0.0, paused=False
            )
            self._state = WalkState.PINNED
            self._error = None
            # A leftover finished/errored run must not shadow the pin in
            # status(): status() prefers self._run whenever it is set, so a
            # stale run (task already done, already torn down by _drive's
            # finally) would report the OLD walk's route/trail/stats/fix
            # under state=PINNED instead of the pin itself.
            self._run = None
            # A "fix" message (not "state") so the store's fix channel fires and
            # the map's live dot moves to the pin. Stats are zero: a pin has no
            # elapsed time, distance, or laps.
            self._broadcast(
                {
                    "type": "fix",
                    "fix": self._pin_fix.model_dump(),
                    "stats": StatsOut(
                        elapsed_s=0.0, distance_m=0.0, laps=0, reconnects=0, ticks=0
                    ).model_dump(),
                    "state": self._state.value,
                }
            )
            return self.status()

    async def stop(self) -> None:
        async with self._lock:
            # A held pin is torn down here too -- one Stop button for both.
            if self._pin_session is not None:
                session = self._pin_session
                self._pin_session = None
                self._pin_fix = None
                # A leftover finished/errored run must not shadow IDLE in
                # status(): if the pin was set over a stale run, status()
                # would keep reporting that run's route/trail after this
                # stop() otherwise.
                self._run = None
                self._state = WalkState.IDLE
                self._error = None
                try:
                    await session.stop(clear=True)
                except Exception as exc:  # noqa: BLE001 — teardown must not raise
                    logger.warning("could not stop the pin session cleanly: %s", exc)
                self._broadcast({"type": "state", "state": self._state.value, "error": None})
                return
            run = self._run
            if run is None:
                # Nothing running, but a previous failed start() may have left
                # self._error set with no run to ever clear it -- DELETE
                # /api/walk must still be able to dismiss that stale failure.
                if self._error is not None:
                    self._state = WalkState.IDLE
                    self._error = None
                    self._broadcast({"type": "state", "state": self._state.value, "error": None})
                return
            task = run.task
            # Publish the "stopped" state before awaiting anything further, so
            # an unlocked status() reader can see self._run is already None
            # during the cancel/teardown window.
            self._run = None
            self._state = WalkState.IDLE
            self._error = None
            if run.watchdog is not None:
                run.watchdog.cancel()
            if task is not None:
                task.cancel()
                # CancelledError is expected: we just cancelled the task above.
                # The cancellation is self-inflicted and is the normal shutdown path.
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            await self._teardown(run)
            self._broadcast({"type": "state", "state": self._state.value, "error": None})

    async def wait_finished(self) -> None:
        """Await the current run's completion. Returns immediately when idle."""
        run = self._run
        if run is not None and run.task is not None:
            await asyncio.wait([run.task])

    def subscribe(self):
        """Context manager yielding a bounded queue of broadcast messages."""
        return _Subscription(self)

    # -- internals -------------------------------------------------------

    async def _drive(self, run: _Run) -> None:
        try:
            stats = await run_walk(
                run.walker,
                run.session,
                duration_s=run.spec.duration_s,
                tick_s=self._tick_s,
                on_fix=lambda fix: self._on_fix(run, fix),
                clock=self._clock,
                sleep=self._sleep,
            )
            # Authoritative: `run_walk`'s own `ticks` counts a tick as soon as
            # `walker.advance()` runs, *before* `session.set()` is awaited, so
            # a tick that ends in SessionLost is still counted here even
            # though `_on_fix` (and so `run.ticks`, from the last per-fix
            # broadcast) never saw it -- `on_fix` only runs after a
            # *successful* `set()`. That means this final count can
            # legitimately be one higher than the last "fix" message's
            # `stats.ticks` when the run ends on a lost session. That's
            # correct, not a bug: this is the count that actually reached the
            # device.
            run.stats = StatsOut.from_stats(stats)
            lost = getattr(run.session, "lost_error", None)
            if lost is not None:
                self._state = WalkState.ERROR
                self._error = f"{type(lost).__name__}: {lost}"
            else:
                self._state = WalkState.FINISHED
        except asyncio.CancelledError:
            raise
        except BaseException as exc:  # noqa: BLE001 — reported, never swallowed
            logger.exception("walk failed")
            self._state = WalkState.ERROR
            self._error = f"{type(exc).__name__}: {exc}"
        finally:
            if run.watchdog is not None:
                run.watchdog.cancel()
            if self._state in (WalkState.FINISHED, WalkState.ERROR):
                # A natural finish sticks: the device keeps the last simulated
                # fix instead of snapping back to real GPS. An error still
                # clears, since something went wrong and a stuck fake
                # position on top of an unclean state isn't a guarantee worth
                # making.
                await self._teardown(run, clear=self._state is WalkState.ERROR)
                # Carry the authoritative final stats alongside the terminal
                # state so a WebSocket-only consumer learns the real numbers
                # without having to re-`GET /api/walk`.
                self._broadcast(
                    {
                        "type": "state",
                        "state": self._state.value,
                        "error": self._error,
                        "stats": run.stats.model_dump() if run.stats is not None else None,
                    }
                )

    def _effective_state(self) -> WalkState:
        """WALKING becomes RECONNECTING while a set() has been in flight too long."""
        run = self._run
        if self._state is not WalkState.WALKING or run is None:
            return self._state
        since = getattr(run.session, "inflight_since", None)
        if since is not None and (self._clock() - since) >= self._stall_threshold_s:
            return WalkState.RECONNECTING
        return self._state

    async def _watch_stalls(self, run: _Run) -> None:
        """Broadcast state changes that produce no fix, e.g. a mid-run reconnect.

        Polls on `self._sleep` -- the same injected clock/sleep the tick loop
        uses -- so tests can drive this deterministically with a virtual
        clock. But it only polls *while a `set()` call is actually in
        flight*: the rest of the time it blocks on `wait_for_inflight()`,
        which consumes no clock time at all. That matters because during a
        genuine stall the tick loop is itself suspended inside that same
        `set()` call and advances no virtual time -- so the watchdog's own
        polling is the only thing moving the clock, which is exactly what's
        needed to notice the stall. Polling unconditionally on a fixed period
        for the whole life of the walk, instead, would race the tick loop's
        own `sleep()` calls between ticks and double-advance a shared virtual
        clock, corrupting tick counts in every other test.
        """
        last = self._effective_state()
        session = run.session
        try:
            while True:
                await session.wait_for_inflight()
                while session.inflight_since is not None:
                    current = self._effective_state()
                    if current is not last:
                        last = current
                        self._broadcast(
                            {"type": "state", "state": current.value, "error": self._error}
                        )
                    if session.inflight_since is None:
                        break
                    await self._sleep(self._stall_threshold_s / 2)
                current = self._effective_state()
                if current is not last:
                    last = current
                    self._broadcast({"type": "state", "state": current.value, "error": self._error})
        except asyncio.CancelledError:
            raise

    async def _teardown(self, run: _Run, *, clear: bool = True) -> None:
        """Stop the session -- exactly once, on success -- optionally clearing
        the device's simulated location.

        `clear=False` closes the tunnel/session as normal but leaves the last
        simulated fix in place on the device: this is how a naturally
        finished walk "sticks" instead of snapping back to real GPS. Every
        other caller (explicit Stop, an errored walk, a pin teardown) keeps
        the default `clear=True`.

        The flag is set only *after* `session.stop()` returns, not before the
        await. If this call is cancelled while suspended inside that await
        (e.g. a concurrent stop() cancelling the drive task mid-teardown),
        CancelledError propagates -- deliberately uncaught here -- and
        `torn_down` stays False, so whoever calls `_teardown` next actually
        retries the stop instead of finding a no-op. A regular (non-cancel)
        failure is logged and still counts as "done": retrying it here would
        not fix a real device/tunnel failure, and that path already has its
        own reconnect logic in session.py.
        """
        if run.torn_down:
            return
        try:
            await run.session.stop(clear=clear)
        except Exception as exc:  # noqa: BLE001 — teardown must not mask the result
            logger.warning("could not stop the session cleanly: %s", exc)
        run.torn_down = True

    def _on_fix(self, run: _Run, fix) -> None:
        out = FixOut.from_fix(fix)
        run.latest_fix = out
        run.trail.append(out)
        run.ticks += 1
        run.stats = StatsOut(
            elapsed_s=run.walker.elapsed_s,
            distance_m=run.walker.distance_m,
            laps=run.walker.laps,
            reconnects=getattr(run.session, "reconnects", 0),
            ticks=run.ticks,
        )
        self._broadcast(
            {
                "type": "fix",
                "fix": out.model_dump(),
                "stats": run.stats.model_dump(),
                "state": self._effective_state().value,
            }
        )

    def _broadcast(self, message: dict) -> None:
        """Push to every subscriber, dropping the oldest message when a queue is
        full. A stalled browser tab must never slow the tick loop."""
        for queue in self._subscribers:
            if queue.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:  # pragma: no cover — defensive
                logger.debug("subscriber queue still full; dropping message")


class _Subscription:
    def __init__(self, service: WalkService) -> None:
        self._service = service
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=service._queue_size)

    def __enter__(self) -> asyncio.Queue:
        self._service._subscribers.add(self.queue)
        return self.queue

    def __exit__(self, *exc_info) -> None:
        self._service._subscribers.discard(self.queue)
