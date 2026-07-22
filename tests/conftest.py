"""Shared test doubles for the web layer -- used by both test_web_service.py
(the service in isolation) and test_web_api.py (the FastAPI wiring around it),
so neither module reaches into the other's internals for its fakes."""

import asyncio

from ios_loc.path import Path

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
        self.set_deadlines = []
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
        self.set_deadlines.append(deadline)
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
