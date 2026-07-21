"""The async tick loop that drives a Walker into a LocationSession."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from ios_loc.session import SessionLost

logger = logging.getLogger(__name__)


@dataclass
class WalkStats:
    elapsed_s: float
    distance_m: float
    laps: int
    reconnects: int
    ticks: int


async def run_walk(
    walker,
    session,
    *,
    duration_s: float | None = None,
    tick_s: float = 1.0,
    on_fix=None,
    clock=time.monotonic,
    sleep=asyncio.sleep,
) -> WalkStats:
    """
    Drive `walker` into `session`, one fix per `tick_s`.

    Ticks are scheduled against absolute deadlines rather than by sleeping a fixed
    amount, so per-tick work cannot accumulate into lost distance over a long run.

    `walker.advance()` is called exactly once per tick. `session.set()` may block
    while it reconnects, and the walk clock does not advance during that time — an
    outage costs distance rather than producing a position jump.
    """
    start = clock()
    deadline = None if duration_s is None else start + duration_s
    next_deadline = start
    ticks = 0

    while True:
        if duration_s is not None and (clock() - start) >= duration_s:
            break
        if walker.finished:
            break

        fix = walker.advance(tick_s)
        ticks += 1
        try:
            await session.set(fix.lat, fix.lon, deadline=deadline)
        except SessionLost:
            logger.warning("device unreachable; ending the walk at its deadline")
            break
        if on_fix is not None:
            on_fix(fix)

        if walker.finished:
            break

        next_deadline += tick_s
        now = clock()
        if now - next_deadline > tick_s:
            # We fell more than a whole tick behind, which means session.set()
            # blocked on a reconnect. Forfeit the lost wall time instead of
            # firing one tick per lost second: an outage must cost distance,
            # never produce a position jump.
            next_deadline = now
        await sleep(max(next_deadline - now, 0.0))

    return WalkStats(
        elapsed_s=walker.elapsed_s,
        distance_m=walker.distance_m,
        laps=walker.laps,
        reconnects=session.reconnects,
        ticks=ticks,
    )
