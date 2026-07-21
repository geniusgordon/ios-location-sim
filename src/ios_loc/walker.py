"""
The movement model. Pure and synchronous by design.

`advance(dt)` never sleeps and never does I/O, so a three-hour run can be verified
in a unit test in milliseconds. The caller owns the clock; freezing the walk during
a device outage is simply a matter of not calling `advance()`.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from ios_loc.path import Coord, Path
from ios_loc.presets import MAX_SPEED_MPS, Profile

_METRES_PER_DEGREE_LAT = 111_320.0


@dataclass(frozen=True)
class Fix:
    """One emitted position sample."""

    elapsed_s: float
    lat: float
    lon: float
    distance_m: float
    speed_mps: float
    paused: bool


class Walker:
    """Advances a simulated position along a `Path` according to a `Profile`.

    Two behaviours are deliberate and load-bearing, not oversights:

    - `distance_m` is the cumulative total distance travelled and is never
      wrapped or reset, even across laps. This is what the CLI reports to the
      user as "total distance walked"; wrapping it to the path length would
      under-report a long multi-lap walk by however many laps were completed.
    - With `loop=True`, a genuinely closed path (start ~= end) wraps by simple
      modulo arithmetic, while an open path (e.g. an out-and-back straight
      line) instead bounces back and forth along itself. Teleporting from the
      far end of an open path straight back to the start would put a
      discontinuous jump in the emitted track; bouncing keeps every emitted
      step within the speed ceiling.
    """

    def __init__(
        self,
        path: Path,
        profile: Profile,
        *,
        loop: bool = False,
        rng: random.Random | None = None,
        scatter_m: float = 3.0,
    ) -> None:
        self.path = path
        self.profile = profile
        self.loop = loop
        self.scatter_m = scatter_m
        self._rng = rng if rng is not None else random.Random()

        self.distance_m = 0.0
        self.elapsed_s = 0.0
        self.laps = 0
        self.finished = False
        self._pause_remaining_s = 0.0

    def advance(self, dt: float) -> Fix:
        """Advance the simulation by `dt` seconds and return the position to emit."""
        self.elapsed_s += dt

        speed = self._tick_speed(dt)
        if speed > 0.0 and not self.finished:
            self.distance_m += speed * dt
            self._apply_bounds()

        lat, lon = self._emit_position()
        return Fix(
            elapsed_s=self.elapsed_s,
            lat=lat,
            lon=lon,
            distance_m=self.distance_m,
            speed_mps=speed,
            paused=self._pause_remaining_s > 0.0,
        )

    # -- internals -------------------------------------------------------

    def _tick_speed(self, dt: float) -> float:
        if self._pause_remaining_s > 0.0:
            self._pause_remaining_s = max(0.0, self._pause_remaining_s - dt)
            return 0.0

        if self._rng.random() < self.profile.pause_per_min * dt / 60.0:
            self._pause_remaining_s = self._rng.uniform(
                self.profile.pause_min_s, self.profile.pause_max_s
            )
            return 0.0

        speed = self.profile.speed * self._rng.gauss(1.0, self.profile.jitter)
        # Clamp against the ceiling using the *jittered* value, not the base.
        return min(max(speed, 0.0), MAX_SPEED_MPS)

    def _apply_bounds(self) -> None:
        length = self.path.length_m
        if self.loop:
            # `distance_m` is the total distance travelled and is never wrapped
            # or reset — that is what lets a long walk keep accumulating past
            # any number of laps. Only the derived position (see
            # `_position_distance`) folds it back onto the path.
            self.laps = int(self.distance_m // length)
        elif self.distance_m >= length:
            self.distance_m = length
            self.finished = True

    def _position_distance(self) -> float:
        """Map the cumulative `distance_m` onto the path's [0, length] range.

        A closed-loop path (start ~= end) wraps cleanly with a plain modulo.
        An open path (e.g. an out-and-back straight line) instead bounces
        back and forth, since wrapping it would teleport from the far end
        straight back to the start.
        """
        length = self.path.length_m
        if not self.loop:
            return self.distance_m
        if self.path.is_closed_loop:
            return self.distance_m % length
        cycle = self.distance_m % (2 * length)
        return cycle if cycle <= length else 2 * length - cycle

    def _emit_position(self) -> Coord:
        lat, lon = self.path.position_at(self._position_distance())
        if self.scatter_m <= 0.0:
            return lat, lon
        # Gaussian scatter applied to the emitted position only; `distance_m` is
        # never perturbed, so noise cannot corrupt accumulated progress.
        dlat = self._rng.gauss(0.0, self.scatter_m) / _METRES_PER_DEGREE_LAT
        cos_lat = max(math.cos(math.radians(lat)), 1e-6)
        dlon = self._rng.gauss(0.0, self.scatter_m) / (_METRES_PER_DEGREE_LAT * cos_lat)
        return lat + dlat, lon + dlon
