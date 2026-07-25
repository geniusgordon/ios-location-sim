"""Maps `discovery.find_device`'s outcomes to a `DeviceStatus` for the GUI.

Kept in the web layer deliberately: `discovery.py` must not know about web
models, so the mapping lives here instead of there.
"""

from __future__ import annotations

import contextlib

from ios_loc.discovery import NoDeviceFound, TunneldNotRunning
from ios_loc.session import _PROGRAMMING_ERRORS
from ios_loc.web.models import DeviceStatus


async def probe_device(find_device, udid: str | None = None) -> DeviceStatus:
    """Check reachability without starting a walk or a pin.

    Opens (and always closes) an RSD connection the same way `doctor` does --
    a close failure must not flip an otherwise-successful probe to
    "disconnected". Programming errors (`TypeError`, `AttributeError`, ...)
    are not device dropouts and are left to propagate rather than being
    reported as a fake "disconnected" status -- same rule as `session.set()`
    and the API's start/pin handlers.
    """
    try:
        rsd = await find_device(udid)
    except TunneldNotRunning as exc:
        return DeviceStatus(connected=False, reason="tunneld_down", detail=str(exc))
    except NoDeviceFound as exc:
        return DeviceStatus(connected=False, reason="no_device", detail=str(exc))
    except _PROGRAMMING_ERRORS:
        raise
    except Exception as exc:  # noqa: BLE001 — reported as a status, not raised
        return DeviceStatus(connected=False, reason="error", detail=f"{type(exc).__name__}: {exc}")

    detail = f"iOS {rsd.product_version}"
    # A close failure must not flip the result.
    with contextlib.suppress(Exception):
        await rsd.close()
    return DeviceStatus(connected=True, reason="ok", detail=detail)
