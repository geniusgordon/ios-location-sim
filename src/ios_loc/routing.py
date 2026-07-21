"""Valhalla routing client and polyline decoding."""

from __future__ import annotations

import hashlib
import json
import pathlib

import requests

from ios_loc.path import Coord, Path

DEFAULT_VALHALLA_URL = "https://valhalla1.openstreetmap.de"
DEFAULT_CACHE_DIR = pathlib.Path.home() / ".cache" / "ios-loc" / "routes"
_TIMEOUT_S = 30


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
        if cache_file.exists():
            return self._to_path(json.loads(cache_file.read_text()))

        if self.offline:
            raise RouteNotCached(
                f"no cached route for these waypoints with costing={costing!r}; "
                f"re-run without --offline once to populate the cache"
            )

        payload = self._fetch(waypoints, costing)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(payload))
        return self._to_path(payload)

    def _cache_key(self, waypoints: list[Coord], costing: str) -> str:
        blob = json.dumps(
            {"w": [[round(lat, 6), round(lon, 6)] for lat, lon in waypoints], "c": costing},
            sort_keys=True,
        )
        return hashlib.sha256(blob.encode()).hexdigest()[:32]

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
        except Exception as exc:  # network, HTTP, or JSON failure
            raise RoutingError(f"Valhalla request failed: {exc}") from exc

    def _to_path(self, payload: dict) -> Path:
        legs = payload.get("trip", {}).get("legs", [])
        if not legs:
            raise RoutingError("Valhalla returned no route legs for these waypoints")

        coords: list[Coord] = []
        for leg in legs:
            leg_coords = decode_polyline(leg["shape"], precision=6)
            if coords and leg_coords and coords[-1] == leg_coords[0]:
                leg_coords = leg_coords[1:]  # drop duplicated junction point
            coords.extend(leg_coords)

        if len(coords) < 2:
            raise RoutingError("decoded route had fewer than 2 points")
        return Path(coords)
