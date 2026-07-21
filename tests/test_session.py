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
