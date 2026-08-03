import pytest

from ios_loc.gpx import parse_gpx


def _wrap(body: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
{body}
</gpx>
"""


def test_parses_a_single_track_segment():
    gpx = _wrap(
        """
        <trk><trkseg>
          <trkpt lat="25.0330" lon="121.5654"></trkpt>
          <trkpt lat="25.0335" lon="121.5660"></trkpt>
        </trkseg></trk>
        """
    )
    assert parse_gpx(gpx) == pytest.approx([(25.0330, 121.5654), (25.0335, 121.5660)])


def test_concatenates_multiple_segments_in_document_order():
    gpx = _wrap(
        """
        <trk>
          <trkseg>
            <trkpt lat="25.0" lon="121.0"></trkpt>
            <trkpt lat="25.1" lon="121.1"></trkpt>
          </trkseg>
          <trkseg>
            <trkpt lat="25.2" lon="121.2"></trkpt>
          </trkseg>
        </trk>
        """
    )
    assert parse_gpx(gpx) == pytest.approx([(25.0, 121.0), (25.1, 121.1), (25.2, 121.2)])


def test_falls_back_to_route_points_when_no_track():
    gpx = _wrap(
        """
        <rte>
          <rtept lat="25.0" lon="121.0"></rtept>
          <rtept lat="25.1" lon="121.1"></rtept>
        </rte>
        """
    )
    assert parse_gpx(gpx) == pytest.approx([(25.0, 121.0), (25.1, 121.1)])


def test_falls_back_to_waypoints_when_no_track_or_route():
    gpx = _wrap(
        """
        <wpt lat="25.0" lon="121.0"></wpt>
        <wpt lat="25.1" lon="121.1"></wpt>
        """
    )
    assert parse_gpx(gpx) == pytest.approx([(25.0, 121.0), (25.1, 121.1)])


def test_track_points_win_over_route_points_and_waypoints():
    gpx = _wrap(
        """
        <wpt lat="1.0" lon="1.0"></wpt>
        <rte><rtept lat="2.0" lon="2.0"></rtept><rtept lat="2.1" lon="2.1"></rtept></rte>
        <trk><trkseg>
          <trkpt lat="25.0" lon="121.0"></trkpt>
          <trkpt lat="25.1" lon="121.1"></trkpt>
        </trkseg></trk>
        """
    )
    assert parse_gpx(gpx) == pytest.approx([(25.0, 121.0), (25.1, 121.1)])


def test_invalid_xml_raises():
    with pytest.raises(ValueError, match="not valid XML"):
        parse_gpx("<gpx><trk>")


def test_missing_lat_raises():
    gpx = _wrap(
        '<trk><trkseg><trkpt lon="121.0"></trkpt>'
        '<trkpt lat="25.1" lon="121.1"></trkpt></trkseg></trk>'
    )
    with pytest.raises(ValueError, match="missing a lat or lon"):
        parse_gpx(gpx)


def test_non_numeric_lat_raises():
    gpx = _wrap(
        '<trk><trkseg><trkpt lat="north" lon="121.0"></trkpt>'
        '<trkpt lat="25.1" lon="121.1"></trkpt></trkseg></trk>'
    )
    with pytest.raises(ValueError, match="non-numeric"):
        parse_gpx(gpx)


def test_single_point_raises():
    gpx = _wrap('<trk><trkseg><trkpt lat="25.0" lon="121.0"></trkpt></trkseg></trk>')
    with pytest.raises(ValueError, match="at least 2"):
        parse_gpx(gpx)


def test_no_points_at_all_raises():
    gpx = _wrap("<metadata></metadata>")
    with pytest.raises(ValueError, match="no <trkpt>, <rtept>, or <wpt>"):
        parse_gpx(gpx)
