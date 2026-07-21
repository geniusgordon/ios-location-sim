"""Pure route geometry. Must not import pymobiledevice3, requests, or asyncio."""

from __future__ import annotations

import bisect
import math
from collections.abc import Sequence

Coord = tuple[float, float]  # (latitude, longitude) in decimal degrees

EARTH_RADIUS_M = 6_371_008.8
_LOOP_TOLERANCE_M = 25.0


def haversine_m(a: Coord, b: Coord) -> float:
    """Great-circle distance between two (lat, lon) points, in metres."""
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


class Path:
    """A polyline with a cumulative-distance table for O(log n) interpolation."""

    def __init__(self, coords: Sequence[Coord]) -> None:
        if len(coords) < 2:
            raise ValueError("a path needs at least 2 coordinates")
        self.coords: list[Coord] = list(coords)
        self._cumulative: list[float] = [0.0]
        for prev, cur in zip(self.coords, self.coords[1:]):
            self._cumulative.append(self._cumulative[-1] + haversine_m(prev, cur))

    @property
    def length_m(self) -> float:
        return self._cumulative[-1]

    @property
    def is_closed_loop(self) -> bool:
        return haversine_m(self.coords[0], self.coords[-1]) <= _LOOP_TOLERANCE_M

    def position_at(self, metres: float) -> Coord:
        """Interpolate the position `metres` along the path. Clamps out-of-range input."""
        if metres <= 0:
            return self.coords[0]
        if metres >= self.length_m:
            return self.coords[-1]
        i = bisect.bisect_right(self._cumulative, metres) - 1
        seg_len = self._cumulative[i + 1] - self._cumulative[i]
        if seg_len == 0:
            return self.coords[i]
        t = (metres - self._cumulative[i]) / seg_len
        (lat1, lon1), (lat2, lon2) = self.coords[i], self.coords[i + 1]
        return (lat1 + (lat2 - lat1) * t, lon1 + (lon2 - lon1) * t)
