import pytest
from pymobiledevice3.exceptions import TunneldConnectionError

from ios_loc import discovery
from ios_loc.discovery import NoDeviceFound, TunneldNotRunning, find_device


class FakeRsd:
    def __init__(self, udid):
        self.udid = udid
        self.closed = False

    async def close(self):
        self.closed = True


async def test_tunneld_down_raises_actionable_error(monkeypatch):
    async def boom(*a, **k):
        raise TunneldConnectionError()

    monkeypatch.setattr(discovery, "get_tunneld_devices", boom)
    with pytest.raises(TunneldNotRunning) as exc:
        await find_device()
    # The message must tell the user exactly how to fix it.
    assert "tunneld" in str(exc.value)


async def test_no_devices_raises(monkeypatch):
    async def none(*a, **k):
        return []

    monkeypatch.setattr(discovery, "get_tunneld_devices", none)
    with pytest.raises(NoDeviceFound):
        await find_device()


async def test_returns_first_device(monkeypatch):
    async def two(*a, **k):
        return [FakeRsd("aaa"), FakeRsd("bbb")]

    monkeypatch.setattr(discovery, "get_tunneld_devices", two)
    rsd = await find_device()
    assert rsd.udid == "aaa"


async def test_udid_selects_specific_device(monkeypatch):
    target = FakeRsd("bbb")

    async def by_udid(udid, *a, **k):
        return target if udid == "bbb" else None

    monkeypatch.setattr(discovery, "get_tunneld_device_by_udid", by_udid)
    assert await find_device("bbb") is target


async def test_unknown_udid_raises(monkeypatch):
    async def by_udid(udid, *a, **k):
        return None

    monkeypatch.setattr(discovery, "get_tunneld_device_by_udid", by_udid)
    with pytest.raises(NoDeviceFound):
        await find_device("zzz")
