"""
The only module that can fail because of hardware.

All reconnect logic lives here, so when the tunnel dies at hour three there is
exactly one place to look.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack

logger = logging.getLogger(__name__)


class SessionLost(Exception):
    """The device could not be reached after the allowed number of attempts."""


class LocationSession:
    def __init__(
        self,
        opener,
        *,
        max_backoff_s: float = 30.0,
        max_attempts: int = 0,  # 0 == retry forever
        sleep=asyncio.sleep,
    ) -> None:
        self._opener = opener
        self._max_backoff_s = max_backoff_s
        self._max_attempts = max_attempts
        self._sleep = sleep
        self._stack: AsyncExitStack | None = None
        self._sim = None
        self.reconnects = 0

    async def start(self) -> None:
        await self._open()

    async def stop(self, clear: bool = True) -> None:
        if self._sim is not None and clear:
            try:
                await self._sim.clear()
            except Exception as exc:
                logger.warning("could not clear simulated location: %s", exc)
        await self._close()

    async def set(self, lat: float, lon: float) -> None:
        """Push a coordinate, reconnecting and retrying if the device drops out."""
        attempt = 0
        backoff = 1.0
        while True:
            try:
                await self._sim.set(lat, lon)
                return
            except Exception as exc:
                attempt += 1
                if self._max_attempts and attempt > self._max_attempts:
                    raise SessionLost(
                        f"device unreachable after {self._max_attempts} attempts"
                    ) from exc
                logger.warning(
                    "device error (%s); reconnecting in %.0fs", exc, backoff
                )
                await self._close()
                await self._sleep(backoff)
                backoff = min(backoff * 2, self._max_backoff_s)
                try:
                    await self._open()
                    self.reconnects += 1
                except Exception as reopen_exc:
                    logger.warning("reconnect failed: %s", reopen_exc)

    # -- internals -------------------------------------------------------

    async def _open(self) -> None:
        stack = AsyncExitStack()
        self._sim = await stack.enter_async_context(self._opener())
        self._stack = stack

    async def _close(self) -> None:
        if self._stack is not None:
            try:
                await self._stack.aclose()
            except Exception as exc:
                logger.debug("error while closing session: %s", exc)
        self._stack = None
        self._sim = None
