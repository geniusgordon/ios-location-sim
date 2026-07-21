"""The async tick loop that drives a Walker into a LocationSession."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass


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
    next_deadline = start
    ticks = 0

    while True:
        if duration_s is not None and (clock() - start) >= duration_s:
            break
        if walker.finished:
            break

        fix = walker.advance(tick_s)
        ticks += 1
        await session.set(fix.lat, fix.lon)
        if on_fix is not None:
            on_fix(fix)

        if walker.finished:
            break

        next_deadline += tick_s
        remaining = next_deadline - clock()
        await sleep(max(remaining, 0.0))

    return WalkStats(
        elapsed_s=walker.elapsed_s,
        distance_m=walker.distance_m,
        laps=walker.laps,
        reconnects=session.reconnects,
        ticks=ticks,
    )
