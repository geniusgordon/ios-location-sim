"""Unit tests for the web-layer device-connectivity probe."""

import pytest

from ios_loc.discovery import NoDeviceFound, TunneldNotRunning
from ios_loc.web.device import probe_device
from ios_loc.web.models import DeviceStatus


class FakeRsd:
    def __init__(self, product_version="17.5"):
        self.product_version = product_version
        self.closed = False

    async def close(self):
        self.closed = True


async def test_probe_reports_connected_on_success():
    rsd = FakeRsd("17.5")

    async def find_device(udid=None):
        return rsd

    status = await probe_device(find_device)
    assert status == DeviceStatus(connected=True, reason="ok", detail="iOS 17.5")
    assert rsd.closed is True


async def test_probe_close_failure_does_not_flip_the_result():
    class BrokenCloseRsd(FakeRsd):
        async def close(self):
            raise RuntimeError("already gone")

    rsd = BrokenCloseRsd("17.0")

    async def find_device(udid=None):
        return rsd

    status = await probe_device(find_device)
    assert status.connected is True
    assert status.reason == "ok"


async def test_probe_maps_tunneld_not_running():
    async def find_device(udid=None):
        raise TunneldNotRunning("tunneld is not running — start it")

    status = await probe_device(find_device)
    assert status.connected is False
    assert status.reason == "tunneld_down"
    assert "tunneld" in status.detail


async def test_probe_maps_no_device_found():
    async def find_device(udid=None):
        raise NoDeviceFound("no active tunnels")

    status = await probe_device(find_device)
    assert status.connected is False
    assert status.reason == "no_device"
    assert "no active tunnels" in status.detail


async def test_probe_maps_other_exceptions_to_error():
    async def find_device(udid=None):
        raise RuntimeError("boom")

    status = await probe_device(find_device)
    assert status.connected is False
    assert status.reason == "error"
    assert "RuntimeError" in status.detail
    assert "boom" in status.detail


async def test_probe_passes_udid_through():
    seen = {}

    async def find_device(udid=None):
        seen["udid"] = udid
        return FakeRsd()

    await probe_device(find_device, udid="abc123")
    assert seen["udid"] == "abc123"
