import math
import pytest
from ios_loc.path import Path, haversine_m


def test_haversine_known_distance():
    # One degree of latitude is ~111.19 km anywhere on the globe.
    d = haversine_m((0.0, 0.0), (1.0, 0.0))
    assert 111_000 < d < 111_400


def test_haversine_is_symmetric():
    a, b = (25.0330, 121.5654), (25.0380, 121.5680)
    assert haversine_m(a, b) == pytest.approx(haversine_m(b, a))


def test_length_is_sum_of_segments():
    p = Path([(0.0, 0.0), (0.0, 0.001), (0.0, 0.002)])
    seg = haversine_m((0.0, 0.0), (0.0, 0.001))
    assert p.length_m == pytest.approx(2 * seg)


def test_position_at_endpoints():
    coords = [(0.0, 0.0), (0.0, 0.001)]
    p = Path(coords)
    assert p.position_at(0.0) == pytest.approx(coords[0])
    assert p.position_at(p.length_m) == pytest.approx(coords[1])


def test_position_at_midpoint_interpolates():
    p = Path([(0.0, 0.0), (0.0, 0.001)])
    lat, lon = p.position_at(p.length_m / 2)
    assert lat == pytest.approx(0.0, abs=1e-9)
    assert lon == pytest.approx(0.0005, rel=1e-6)


def test_position_at_clamps_out_of_range():
    p = Path([(0.0, 0.0), (0.0, 0.001)])
    assert p.position_at(-5.0) == pytest.approx((0.0, 0.0))
    assert p.position_at(p.length_m + 5.0) == pytest.approx((0.0, 0.001))


def test_is_closed_loop():
    assert Path([(0.0, 0.0), (0.0, 0.001), (0.0, 0.0)]).is_closed_loop
    assert not Path([(0.0, 0.0), (0.0, 0.001)]).is_closed_loop


def test_rejects_short_path():
    with pytest.raises(ValueError):
        Path([(0.0, 0.0)])
