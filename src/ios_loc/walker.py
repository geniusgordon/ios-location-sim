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
from ios_loc.presets import MAX_SPEED_MPS, Pace

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
    """Advances a simulated position along a `Path` according to a `Pace`.

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
        pace: Pace,
        *,
        loop: bool = False,
        rng: random.Random | None = None,
        scatter_m: float = 3.0,
    ) -> None:
        self.path = path
        self.pace = pace
        self.loop = loop
        self.scatter_m = scatter_m
        self._rng = rng if rng is not None else random.Random()

        self.distance_m = 0.0
        self.elapsed_s = 0.0
        self.laps = 0
        self.finished = False
        self._pause_remaining_s = 0.0
        self._reroute_offset_m = 0.0

    def advance(self, dt: float) -> Fix:
        """Advance the simulation by `dt` seconds and return the position to emit."""
        self.elapsed_s += dt

        speed = 0.0 if self.finished else self._tick_speed(dt)
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

    def reroute(self, new_path: Path) -> None:
        """Swap in a newly-computed path starting at the walker's current
        live position, without disturbing the cumulative `distance_m`
        counter (still the total ever walked, still never wrapped/reset).

        Path-relative position (`_position_distance`/`_apply_bounds`) is
        rebased to start at 0 on `new_path` by recording the current
        `distance_m` as the new offset, so the very next `advance()` emits
        `new_path.coords[0]` -- continuous with the live fix `new_path` was
        built from, no jump.

        Synchronous and non-awaiting, like `advance()` -- safe to call
        between ticks from the same event-loop task that owns the walker.
        Neither method ever yields to the loop, so the two can never
        interleave; calling this from a second task/thread would race.
        """
        self.path = new_path
        self._reroute_offset_m = self.distance_m
        self.finished = False

    # -- internals -------------------------------------------------------

    def _tick_speed(self, dt: float) -> float:
        """
        Effective average speed across this tick, in m/s.

        Returns an average rather than an instantaneous value so a tick only
        partly consumed by a pause still credits the walking portion. At the
        normal 1 Hz tick a pause always spans the whole tick, so this reduces to
        either 0.0 or the jittered speed; the distinction only matters for an
        unusually large `dt`.
        """
        moving_s = dt

        # Consume any pause already in progress.
        if self._pause_remaining_s > 0.0:
            paused = min(self._pause_remaining_s, moving_s)
            self._pause_remaining_s -= paused
            moving_s -= paused

        if moving_s > 0.0:
            # Poisson arrival: probability of at least one pause beginning during
            # `moving_s`. The previous linear form (rate * dt) exceeds 1.0 for a
            # large dt and forced a pause on every such tick, discarding the
            # whole interval's distance.
            rate_per_s = self.pace.pause_per_min / 60.0
            if self._rng.random() < 1.0 - math.exp(-rate_per_s * moving_s):
                pause = self._rng.uniform(self.pace.pause_min_s, self.pace.pause_max_s)
                consumed = min(pause, moving_s)
                self._pause_remaining_s = pause - consumed
                moving_s -= consumed

        if moving_s <= 0.0:
            return 0.0

        speed = self.pace.speed * self._rng.gauss(1.0, self.pace.jitter)
        # Clamp against the ceiling using the *jittered* value, not the base.
        speed = min(max(speed, 0.0), MAX_SPEED_MPS)
        return speed * (moving_s / dt)

    def _apply_bounds(self) -> None:
        length = self.path.length_m
        # `distance_m - _reroute_offset_m` is how far the walker has moved
        # along the *current* path -- `_reroute_offset_m` is 0 until a
        # `reroute()` rebases it, so this is just `distance_m` for a walk
        # that was never rerouted.
        travelled = self.distance_m - self._reroute_offset_m
        if self.loop:
            # `distance_m` is the total distance travelled and is never wrapped
            # or reset — that is what lets a long walk keep accumulating past
            # any number of laps. Only the derived position (see
            # `_position_distance`) folds it back onto the path.
            lengths = travelled / length
            # On a bouncing open route a lap is a full out-and-back, i.e. two path
            # lengths; on a closed route one length is one lap.
            self.laps = int(lengths) if self.path.is_closed_loop else int(lengths / 2)
        elif travelled >= length:
            self.distance_m = self._reroute_offset_m + length
            self.finished = True

    def _position_distance(self) -> float:
        """Map the cumulative `distance_m` onto the path's [0, length] range.

        A closed-loop path (start ~= end) wraps cleanly with a plain modulo.
        An open path (e.g. an out-and-back straight line) instead bounces
        back and forth, since wrapping it would teleport from the far end
        straight back to the start.
        """
        length = self.path.length_m
        travelled = self.distance_m - self._reroute_offset_m
        if not self.loop:
            return travelled
        if self.path.is_closed_loop:
            return travelled % length
        cycle = travelled % (2 * length)
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
