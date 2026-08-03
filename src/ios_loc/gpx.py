"""Parse GPX files into a plain list of coordinates.

Pure parsing, no I/O: like `routing.decode_polyline`, this module never
touches the filesystem or network -- callers read the file and pass the text
in.
"""

from __future__ import annotations

from xml.etree import ElementTree

from ios_loc.path import Coord


def _local_name(tag: str) -> str:
    """Strip a GPX namespace off an element tag, e.g. '{...}trkpt' -> 'trkpt'."""
    return tag.rsplit("}", 1)[-1]


def _points(root: ElementTree.Element, tag: str) -> list[Coord]:
    points: list[Coord] = []
    for elem in root.iter():
        if _local_name(elem.tag) != tag:
            continue
        lat_raw, lon_raw = elem.get("lat"), elem.get("lon")
        if lat_raw is None or lon_raw is None:
            raise ValueError(f"<{tag}> is missing a lat or lon attribute")
        try:
            points.append((float(lat_raw), float(lon_raw)))
        except ValueError as exc:
            raise ValueError(
                f"<{tag}> has a non-numeric lat/lon: {lat_raw!r}, {lon_raw!r}"
            ) from exc
    return points


def parse_gpx(text: str) -> list[Coord]:
    """Extract a route's coordinates from GPX XML.

    Prefers track points (`<trkpt>`, concatenated across every `<trkseg>` in
    document order -- a multi-segment track is one continuous path here).
    Falls back to route points (`<rtept>`) if there is no track, then to
    waypoints (`<wpt>`) if there is neither: a recorded track is the most
    literal description of a path a GPX file can hold, so it wins whenever
    it's present.

    Raises `ValueError` for anything that isn't parseable GPX: invalid XML, a
    point missing `lat`/`lon`, or fewer than 2 points found in total.
    """
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        raise ValueError(f"not valid XML: {exc}") from exc

    for tag in ("trkpt", "rtept", "wpt"):
        points = _points(root, tag)
        if points:
            if len(points) < 2:
                raise ValueError(
                    f"GPX file has only {len(points)} <{tag}> point(s); a route needs at least 2"
                )
            return points

    raise ValueError("GPX file has no <trkpt>, <rtept>, or <wpt> points")
