"""
The only module that can fail because of hardware.

All reconnect logic lives here, so when the tunnel dies at hour three there is
exactly one place to look.
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import AsyncExitStack

logger = logging.getLogger(__name__)

# Errors that indicate a bug rather than a device dropout. Retrying these
# forever would silently consume an overnight run on a defect that can never
# succeed on a later attempt.
_PROGRAMMING_ERRORS = (TypeError, AttributeError, NameError, ImportError)


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
        clock=time.monotonic,
    ) -> None:
        self._opener = opener
        self._max_backoff_s = max_backoff_s
        self._max_attempts = max_attempts
        self._sleep = sleep
        self._clock = clock
        self._stack: AsyncExitStack | None = None
        self._sim = None
        self.reconnects = 0
        self._backoff = 1.0

    async def start(self, attempts: int = 3) -> None:
        """
        Open the session, retrying briefly so a tunnel that is still coming up
        does not kill the run before it begins.

        Bounded rather than infinite: at launch someone is watching, so a device
        that simply is not there should fail fast with the real error.
        """
        last_error: BaseException | None = None
        for attempt in range(1, attempts + 1):
            try:
                await self._open()
                self._backoff = 1.0
                return
            except Exception as exc:
                last_error = exc
                if attempt == attempts:
                    break
                logger.warning("could not open session (%s); retrying", exc)
                await self._sleep(self._backoff)
                self._backoff = min(self._backoff * 2, self._max_backoff_s)
        assert last_error is not None
        raise last_error

    async def stop(self, clear: bool = True) -> None:
        if self._sim is not None and clear:
            try:
                await self._sim.clear()
            except Exception as exc:
                logger.warning("could not clear simulated location: %s", exc)
        await self._close()

    async def set(self, lat: float, lon: float, deadline: float | None = None) -> None:
        """
        Push a coordinate, reconnecting and retrying if the device drops out.

        Backoff lives on the instance, not this call, so a tunnel that flaps
        once per tick still escalates instead of retrying every second forever.
        """
        attempt = 0
        last_error: BaseException | None = None

        while True:
            if self._sim is not None:
                try:
                    await self._sim.set(lat, lon)
                    self._backoff = 1.0  # healthy again
                    return
                except _PROGRAMMING_ERRORS:
                    raise  # a bug will never succeed on retry
                except Exception as exc:
                    last_error = exc
                    logger.warning("device error (%s); reconnecting", exc)
                    await self._close()

            attempt += 1
            if self._max_attempts and attempt > self._max_attempts:
                raise SessionLost(
                    f"device unreachable after {self._max_attempts} attempts"
                ) from last_error

            if deadline is not None and self._clock() >= deadline:
                raise SessionLost(
                    "device still unreachable at the end of the requested run"
                ) from last_error

            await self._sleep(self._backoff)
            self._backoff = min(self._backoff * 2, self._max_backoff_s)
            try:
                await self._open()
                self.reconnects += 1
            except Exception as exc:
                last_error = exc
                logger.warning("reconnect failed: %s", exc)

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
