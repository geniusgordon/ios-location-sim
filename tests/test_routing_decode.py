import pytest
from ios_loc.routing import decode_polyline


def test_decodes_precision_5_reference_value():
    # The canonical Google-polyline example: (38.5,-120.2), (40.7,-120.95), (43.252,-126.453)
    pts = decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@", precision=5)
    assert pts == pytest.approx([(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)])


def test_precision_6_is_the_default():
    # Same encoded string decoded at precision 6 must be exactly 10x smaller.
    encoded = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
    p6 = decode_polyline(encoded)
    p5 = decode_polyline(encoded, precision=5)
    assert p6[0][0] == pytest.approx(p5[0][0] / 10)
    assert p6[0][1] == pytest.approx(p5[0][1] / 10)


def test_empty_string_yields_no_points():
    assert decode_polyline("") == []


def test_decodes_real_valhalla_shape():
    # Captured verbatim from valhalla1.openstreetmap.de for a Taipei pedestrian
    # route on 2026-07-21. Latitude comes first.
    pts = decode_polyline("{n{vn@qmwzfFDyFmFG")
    assert pts == pytest.approx(
        [
            (25.032958, 121.565417),
            (25.032955, 121.565542),
            (25.033074, 121.565546),
        ]
    )
