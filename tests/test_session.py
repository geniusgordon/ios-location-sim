import pytest
from contextlib import asynccontextmanager

from ios_loc.session import LocationSession, SessionLost


class FakeSim:
    def __init__(self, fail_times=0):
        self.fail_times = fail_times
        self.sets = []
        self.cleared = False

    async def set(self, lat, lon):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise ConnectionError("device went away")
        self.sets.append((lat, lon))

    async def clear(self):
        self.cleared = True


def opener_for(sims):
    """Yields each sim in turn on successive opens."""
    it = iter(sims)

    @asynccontextmanager
    async def opener():
        yield next(it)

    return opener


async def collect_sleeps():
    slept = []

    async def sleep(seconds):
        slept.append(seconds)

    return slept, sleep


async def test_set_forwards_to_sim():
    sim = FakeSim()
    session = LocationSession(opener_for([sim]))
    await session.start()
    await session.set(25.0, 121.0)
    assert sim.sets == [(25.0, 121.0)]


async def test_reconnects_after_failure_and_retries_the_set():
    broken, good = FakeSim(fail_times=1), FakeSim()
    slept, sleep = await collect_sleeps()
    session = LocationSession(opener_for([broken, good]), sleep=sleep)
    await session.start()
    await session.set(25.0, 121.0)
    assert good.sets == [(25.0, 121.0)]
    assert session.reconnects == 1


async def test_backoff_grows_then_caps():
    sims = [FakeSim(fail_times=1) for _ in range(8)] + [FakeSim()]
    slept, sleep = await collect_sleeps()
    session = LocationSession(opener_for(sims), max_backoff_s=30.0, sleep=sleep)
    await session.start()
    await session.set(1.0, 2.0)
    assert slept[:4] == [1.0, 2.0, 4.0, 8.0]
    assert max(slept) <= 30.0


async def test_gives_up_after_max_attempts():
    sims = [FakeSim(fail_times=1) for _ in range(5)]
    slept, sleep = await collect_sleeps()
    session = LocationSession(opener_for(sims), max_attempts=3, sleep=sleep)
    await session.start()
    with pytest.raises(SessionLost):
        await session.set(1.0, 2.0)


async def test_stop_clears_by_default():
    sim = FakeSim()
    session = LocationSession(opener_for([sim]))
    await session.start()
    await session.stop()
    assert sim.cleared


async def test_stop_can_leave_location_in_place():
    sim = FakeSim()
    session = LocationSession(opener_for([sim]))
    await session.start()
    await session.stop(clear=False)
    assert not sim.cleared


async def test_session_lost_preserves_the_real_error():
    # A dead run must report why the device went away, not an internal
    # AttributeError from dereferencing a None session.
    sim = FakeSim(fail_times=99)
    opened = [0]

    @asynccontextmanager
    async def opener():
        opened[0] += 1
        if opened[0] > 1:
            raise OSError("tunneld gone away")
        yield sim

    slept, sleep = await collect_sleeps()
    session = LocationSession(opener, max_attempts=4, sleep=sleep)
    await session.start()
    with pytest.raises(SessionLost) as exc_info:
        await session.set(25.0, 121.0)
    cause = exc_info.value.__cause__
    assert isinstance(cause, OSError), f"real cause masked by {type(cause).__name__}"
    assert "tunneld" in str(cause)


async def test_programming_errors_are_not_retried_forever():
    # max_attempts=0 means retry forever; a bug must still surface immediately.
    class BuggySim:
        async def set(self, lat, lon):
            raise TypeError("bad coordinate type")

        async def clear(self):
            pass

    slept, sleep = await collect_sleeps()
    session = LocationSession(opener_for([BuggySim()]), sleep=sleep)
    await session.start()
    with pytest.raises(TypeError):
        await session.set(25.0, 121.0)
    assert slept == [], "a programming error must not trigger backoff"


async def test_backoff_escalates_within_a_sustained_outage():
    # While the device stays down, one set() call keeps looping internally and
    # backoff must escalate and cap rather than retrying every second forever.
    sim = FakeSim()
    opened = [0]

    @asynccontextmanager
    async def opener():
        opened[0] += 1
        if opened[0] <= 6:
            raise OSError("device still down")
        yield sim

    slept, sleep = await collect_sleeps()
    session = LocationSession(opener_for([sim]), sleep=sleep)
    await session.start()
    session._opener = opener  # device drops after a healthy start
    session._sim = None
    await session.set(25.0, 121.0)
    assert slept[:4] == [1.0, 2.0, 4.0, 8.0], f"backoff did not escalate: {slept}"
    assert max(slept) <= 30.0


async def test_backoff_resets_after_a_healthy_send():
    # Two separate blips, each starting from 1s. An isolated dropout must not
    # inherit escalated backoff from an unrelated earlier one - fast recovery is
    # the right response to a transient failure.
    class Controlled:
        def __init__(self):
            self.fail_next = False
            self.sets = []

        async def set(self, lat, lon):
            if self.fail_next:
                self.fail_next = False
                raise ConnectionError("blip")
            self.sets.append((lat, lon))

        async def clear(self):
            pass

    sim = Controlled()
    slept, sleep = await collect_sleeps()
    session = LocationSession(opener_for([sim, sim, sim]), sleep=sleep)
    await session.start()
    sim.fail_next = True
    await session.set(25.0, 121.0)  # blip -> sleeps 1.0, reconnects, succeeds
    await session.set(25.0, 121.0)  # healthy
    sim.fail_next = True
    await session.set(25.0, 121.0)  # second blip -> 1.0 again, not 2.0
    assert slept == [1.0, 1.0], f"backoff did not reset after success: {slept}"
    assert len(sim.sets) == 3


async def test_start_retries_a_slow_tunnel():
    sim = FakeSim()
    attempts = [0]

    @asynccontextmanager
    async def opener():
        attempts[0] += 1
        if attempts[0] < 3:
            raise OSError("tunnel still coming up")
        yield sim

    slept, sleep = await collect_sleeps()
    session = LocationSession(opener, sleep=sleep)
    await session.start()
    await session.set(25.0, 121.0)
    assert sim.sets == [(25.0, 121.0)]


async def test_set_gives_up_at_its_deadline():
    class Clock:
        def __init__(self):
            self.now = 0.0

        def __call__(self):
            return self.now

    clock = Clock()

    async def sleep(seconds):
        clock.now += seconds

    @asynccontextmanager
    async def opener():
        raise OSError("device gone")
        yield  # pragma: no cover

    sim = FakeSim()

    @asynccontextmanager
    async def first_ok():
        yield sim

    session = LocationSession(first_ok, sleep=sleep, clock=clock)
    await session.start()
    session._opener = opener
    session._sim = None
    with pytest.raises(SessionLost):
        await session.set(25.0, 121.0, deadline=100.0)
    assert clock.now >= 100.0


async def test_start_reraises_the_original_error_when_device_absent():
    # The CLI catches DiscoveryError subclasses, so start() must not swap the type.
    @asynccontextmanager
    async def opener():
        raise OSError("no device")
        yield  # pragma: no cover

    slept, sleep = await collect_sleeps()
    session = LocationSession(opener, sleep=sleep)
    with pytest.raises(OSError, match="no device"):
        await session.start()
