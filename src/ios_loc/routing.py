"""Valhalla routing client and polyline decoding."""

from __future__ import annotations

from ios_loc.path import Coord


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
