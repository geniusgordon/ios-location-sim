"""Finding the device through a running tunneld, with actionable errors."""

from __future__ import annotations

from contextlib import asynccontextmanager

from pymobiledevice3.exceptions import TunneldConnectionError
from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation
from pymobiledevice3.tunneld.api import get_tunneld_device_by_udid, get_tunneld_devices

TUNNELD_HINT = "start it with:  sudo pymobiledevice3 remote tunneld -d"


class DiscoveryError(Exception):
    """Could not reach a device."""


class TunneldNotRunning(DiscoveryError):
    pass


class NoDeviceFound(DiscoveryError):
    pass


async def find_device(udid: str | None = None):
    """Return a connected RemoteServiceDiscoveryService for the target device."""
    try:
        if udid:
            rsd = await get_tunneld_device_by_udid(udid)
            if rsd is None:
                raise NoDeviceFound(f"tunneld reports no tunnel for udid {udid!r}")
            return rsd

        devices = await get_tunneld_devices()
    except TunneldConnectionError as exc:
        raise TunneldNotRunning(f"tunneld is not running — {TUNNELD_HINT}") from exc

    if not devices:
        raise NoDeviceFound(
            "tunneld is running but has no active tunnels — "
            "unlock the device, confirm it is trusted, and check Developer Mode is on"
        )
    return devices[0]


@asynccontextmanager
async def open_simulation(udid: str | None = None):
    """Yield a live LocationSimulation, closing the whole stack on exit."""
    rsd = await find_device(udid)
    try:
        async with DvtProvider(rsd) as dvt, LocationSimulation(dvt) as sim:
            yield sim
    finally:
        await rsd.close()
