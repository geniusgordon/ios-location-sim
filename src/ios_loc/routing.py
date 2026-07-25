"""Valhalla routing client and polyline decoding."""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import pathlib
import tempfile

import requests

from ios_loc.path import Coord, Path

DEFAULT_VALHALLA_URL = "https://valhalla1.openstreetmap.de"
DEFAULT_CACHE_DIR = pathlib.Path.home() / ".cache" / "ios-loc" / "routes"
_TIMEOUT_S = 30

logger = logging.getLogger(__name__)


def decode_polyline(encoded: str, precision: int = 6) -> list[Coord]:
    """
    Decode an encoded polyline into (lat, lon) pairs.

    Valhalla uses precision 6, unlike the more common precision 5. Decoding at the
    wrong precision silently yields coordinates off by a factor of ten.

    :raises ValueError: if the input is truncated or contains invalid characters.
        This data arrives from a remote routing server, so a malformed response
        must fail loudly rather than yield a plausible-looking wrong coordinate.
    """
    factor = float(10**precision)
    coords: list[Coord] = []
    index = lat = lon = 0
    length = len(encoded)

    while index < length:
        for is_latitude in (True, False):
            result = shift = 0
            terminated = False
            while index < length:
                byte = ord(encoded[index]) - 63
                if byte < 0:
                    raise ValueError(
                        f"invalid character {encoded[index]!r} at offset {index} "
                        f"of encoded polyline"
                    )
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    terminated = True
                    break
            if not terminated:
                raise ValueError(
                    f"truncated encoded polyline: varint ending at offset {index} "
                    f"has no terminating byte"
                )
            delta = ~(result >> 1) if result & 1 else (result >> 1)
            if is_latitude:
                lat += delta
            else:
                lon += delta
        coords.append((lat / factor, lon / factor))

    return coords


class RoutingError(Exception):
    """Routing failed."""


class RouteNotCached(RoutingError):
    """Offline mode was requested but this route is not in the cache."""


def _default_poster(url, json=None, timeout=None):
    return requests.post(url, json=json, timeout=timeout)


class ValhallaClient:
    """
    Fetches pedestrian/bicycle routes from a Valhalla server, caching every response.

    The public FOSSGIS server publishes no rate-limit headers, so caching is the only
    politeness control available. `base_url` can be repointed at a local
    `gis-ops/docker-valhalla` container, which speaks an identical API.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_VALHALLA_URL,
        cache_dir: pathlib.Path | None = None,
        offline: bool = False,
        poster=_default_poster,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.cache_dir = pathlib.Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
        self.offline = offline
        self._poster = poster

    def route(self, waypoints: list[Coord], costing: str) -> Path:
        if len(waypoints) < 2:
            raise ValueError("routing needs at least 2 waypoints")

        cache_file = self.cache_dir / f"{self._cache_key(waypoints, costing)}.json"
        cached = self._read_cache(cache_file)
        if cached is not None:
            return self._to_path(cached)

        if self.offline:
            raise RouteNotCached(
                f"no cached route for these waypoints with costing={costing!r}; "
                f"re-run without --offline once to populate the cache"
            )

        payload = self._fetch(waypoints, costing)
        self._write_cache(cache_file, payload)
        return self._to_path(payload)

    def _cache_key(self, waypoints: list[Coord], costing: str) -> str:
        blob = json.dumps(
            {
                "u": self.base_url,
                "w": [[round(lat, 6), round(lon, 6)] for lat, lon in waypoints],
                "c": costing,
            },
            sort_keys=True,
        )
        return hashlib.sha256(blob.encode()).hexdigest()[:32]

    def _read_cache(self, cache_file: pathlib.Path) -> dict | None:
        """Return the cached payload, or None if absent. Discards corrupt entries."""
        if not cache_file.exists():
            return None
        try:
            payload = json.loads(cache_file.read_text())
            if not isinstance(payload, dict):
                raise json.JSONDecodeError("cached payload is not a JSON object", "", 0)
            return payload
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("discarding unreadable cache entry %s: %s", cache_file, exc)
            if self.offline:
                raise RouteNotCached(
                    f"cached route {cache_file} is corrupt and --offline forbids refetching"
                ) from exc
            cache_file.unlink(missing_ok=True)
            return None

    def _write_cache(self, cache_file: pathlib.Path, payload: dict) -> None:
        """
        Write atomically, so a process killed mid-write leaves no partial entry.

        A failed cache write is logged and ignored: the route has already been
        fetched and decoded successfully, so losing it because the cache is
        unwritable would trade a working result for a crash.
        """
        tmp: str | None = None
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.cache_dir, suffix=".tmp")
            with os.fdopen(fd, "w") as handle:
                json.dump(payload, handle)
            os.replace(tmp, cache_file)
        except OSError as exc:
            logger.warning("could not cache route to %s: %s", cache_file, exc)
            if tmp is not None:
                with contextlib.suppress(OSError):
                    pathlib.Path(tmp).unlink(missing_ok=True)
        except BaseException:
            if tmp is not None:
                pathlib.Path(tmp).unlink(missing_ok=True)
            raise

    def _fetch(self, waypoints: list[Coord], costing: str) -> dict:
        body = {
            "locations": [{"lat": lat, "lon": lon} for lat, lon in waypoints],
            "costing": costing,
            "directions_options": {"units": "km"},
        }
        try:
            resp = self._poster(f"{self.base_url}/route", json=body, timeout=_TIMEOUT_S)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise RoutingError(f"Valhalla request failed: {exc}") from exc

    def _to_path(self, payload: dict) -> Path:
        legs = payload.get("trip", {}).get("legs", [])
        if not legs:
            raise RoutingError("Valhalla returned no route legs for these waypoints")

        coords: list[Coord] = []
        for leg in legs:
            try:
                shape = leg["shape"]
                leg_coords = decode_polyline(shape, precision=6)
            except (KeyError, ValueError) as exc:
                raise RoutingError(f"malformed route geometry from Valhalla: {exc}") from exc
            # Strip every leading point repeating the junction, not just the first.
            while coords and leg_coords and coords[-1] == leg_coords[0]:
                leg_coords = leg_coords[1:]
            coords.extend(leg_coords)

        if len(coords) < 2:
            raise RoutingError("decoded route had fewer than 2 points")
        return Path(coords)
