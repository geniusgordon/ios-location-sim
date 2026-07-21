"""Owns at most one running walk. Asyncio only — no HTTP types cross this line."""

from __future__ import annotations

import asyncio
import collections
import logging
import random
import time
from dataclasses import dataclass, field

from ios_loc.path import Coord, Path
from ios_loc.presets import Profile
from ios_loc.runner import run_walk
from ios_loc.walker import Walker
from ios_loc.web.models import FixOut, StatsOut, WalkState, WalkStatus

logger = logging.getLogger(__name__)


class WalkAlreadyRunning(RuntimeError):
    """A run is already in progress; the device accepts only one."""


@dataclass
class StartSpec:
    waypoints: list[Coord]
    costing: str
    profile: Profile
    loop: bool = False
    duration_s: float | None = None
    scatter_m: float = 3.0
    preset_name: str | None = None


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
    ) -> None:
        self._route_client = route_client
        self._session_factory = session_factory
        self._trail_len = trail_len
        self._queue_size = queue_size
        self._tick_s = tick_s
        self._clock = clock
        self._sleep = sleep
        self._rng = rng if rng is not None else random.Random()

        self._run: _Run | None = None
        self._state = WalkState.IDLE
        self._error: str | None = None
        self._subscribers: set[asyncio.Queue] = set()

    # -- public ----------------------------------------------------------

    def status(self) -> WalkStatus:
        run = self._run
        if run is None:
            return WalkStatus(state=self._state, error=self._error)
        return WalkStatus(
            state=self._state,
            error=self._error,
            fix=run.latest_fix,
            stats=run.stats,
            route=[[lat, lon] for lat, lon in run.path.coords],
            trail=list(run.trail),
            preset_name=run.spec.preset_name,
            profile=run.spec.profile.name,
            loop=run.spec.loop,
            length_m=run.path.length_m,
        )

    async def start(self, spec: StartSpec) -> WalkStatus:
        if self._run is not None:
            raise WalkAlreadyRunning("a walk is already running")

        self._state = WalkState.STARTING
        self._error = None
        # RouteClient.route() is synchronous `requests`; keep it off the loop.
        path = await asyncio.to_thread(self._route_client.route, spec.waypoints, spec.costing)

        walker = Walker(path, spec.profile, loop=spec.loop, rng=self._rng, scatter_m=spec.scatter_m)
        session = self._session_factory()
        run = _Run(
            walker=walker,
            session=session,
            path=path,
            spec=spec,
            trail=collections.deque(maxlen=self._trail_len),
        )
        self._run = run

        try:
            await session.start()
        except BaseException:
            self._run = None
            self._state = WalkState.IDLE
            raise

        self._state = WalkState.WALKING
        run.task = asyncio.create_task(self._drive(run), name="ios-loc-walk")
        self._broadcast({"type": "state", "state": self._state.value, "error": None})
        return self.status()

    async def stop(self) -> None:
        run = self._run
        if run is None:
            return
        if run.task is not None:
            run.task.cancel()
            try:
                await run.task
            except asyncio.CancelledError:
                pass
        await self._teardown(run)
        self._run = None
        self._state = WalkState.IDLE
        self._error = None
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
            run.stats = StatsOut.from_stats(stats)
            self._state = WalkState.FINISHED
        except asyncio.CancelledError:
            raise
        except BaseException as exc:  # noqa: BLE001 — reported, never swallowed
            logger.exception("walk failed")
            self._state = WalkState.ERROR
            self._error = f"{type(exc).__name__}: {exc}"
        finally:
            if self._state in (WalkState.FINISHED, WalkState.ERROR):
                await self._teardown(run)
                self._broadcast(
                    {"type": "state", "state": self._state.value, "error": self._error}
                )

    async def _teardown(self, run: _Run) -> None:
        try:
            await run.session.stop(clear=True)
        except Exception as exc:  # noqa: BLE001 — teardown must not mask the result
            logger.warning("could not stop the session cleanly: %s", exc)

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
                "state": self._state.value,
            }
        )

    def _broadcast(self, message: dict) -> None:
        """Push to every subscriber, dropping the oldest message when a queue is
        full. A stalled browser tab must never slow the tick loop."""
        for queue in self._subscribers:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
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
