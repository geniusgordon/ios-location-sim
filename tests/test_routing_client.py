import pytest
from ios_loc.routing import RouteNotCached, RoutingError, ValhallaClient

WAYPOINTS = [(25.0330, 121.5654), (25.0380, 121.5680)]

# Real precision-6 shapes captured from valhalla1.openstreetmap.de on 2026-07-21,
# split across two legs to exercise leg concatenation.
FAKE_RESPONSE = {
    "trip": {
        "status": 0,
        "legs": [
            {"shape": "{n{vn@qmwzfFDyFmFG"},   # (25.032958,121.565417) ... (25.033074,121.565546)
            {"shape": "{n{vn@qmwzfFDyFmFG"},
        ],
    }
}


class FakePoster:
    """Stands in for requests.post; records calls and returns a canned payload."""

    def __init__(self, payload=FAKE_RESPONSE):
        self.payload = payload
        self.calls = []

    def __call__(self, url, json=None, timeout=None):
        self.calls.append((url, json))

        class Resp:
            status_code = 200

            def raise_for_status(self_inner):
                return None

            def json(self_inner):
                return self.payload

        return Resp()


def test_route_returns_path_with_points(tmp_path):
    poster = FakePoster()
    client = ValhallaClient(cache_dir=tmp_path, poster=poster)
    path = client.route(WAYPOINTS, costing="pedestrian")
    assert len(path.coords) >= 2
    assert path.length_m > 0


def test_costing_is_sent_in_request(tmp_path):
    poster = FakePoster()
    ValhallaClient(cache_dir=tmp_path, poster=poster).route(WAYPOINTS, costing="bicycle")
    _url, body = poster.calls[0]
    assert body["costing"] == "bicycle"
    assert body["locations"] == [
        {"lat": 25.0330, "lon": 121.5654},
        {"lat": 25.0380, "lon": 121.5680},
    ]


def test_second_identical_call_hits_cache_not_network(tmp_path):
    poster = FakePoster()
    client = ValhallaClient(cache_dir=tmp_path, poster=poster)
    client.route(WAYPOINTS, costing="pedestrian")
    client.route(WAYPOINTS, costing="pedestrian")
    assert len(poster.calls) == 1


def test_different_costing_is_a_different_cache_entry(tmp_path):
    poster = FakePoster()
    client = ValhallaClient(cache_dir=tmp_path, poster=poster)
    client.route(WAYPOINTS, costing="pedestrian")
    client.route(WAYPOINTS, costing="bicycle")
    assert len(poster.calls) == 2


def test_offline_uses_cache_written_by_earlier_run(tmp_path):
    poster = FakePoster()
    ValhallaClient(cache_dir=tmp_path, poster=poster).route(WAYPOINTS, costing="pedestrian")

    def explode(*a, **k):
        raise AssertionError("offline client must not touch the network")

    offline = ValhallaClient(cache_dir=tmp_path, offline=True, poster=explode)
    path = offline.route(WAYPOINTS, costing="pedestrian")
    assert path.length_m > 0


def test_offline_raises_when_not_cached(tmp_path):
    offline = ValhallaClient(cache_dir=tmp_path, offline=True)
    with pytest.raises(RouteNotCached):
        offline.route(WAYPOINTS, costing="pedestrian")


def test_needs_at_least_two_waypoints(tmp_path):
    client = ValhallaClient(cache_dir=tmp_path, poster=FakePoster())
    with pytest.raises(ValueError):
        client.route([(25.0, 121.0)], costing="pedestrian")


def test_route_without_legs_raises(tmp_path):
    poster = FakePoster(payload={"trip": {"legs": []}})
    client = ValhallaClient(cache_dir=tmp_path, poster=poster)
    with pytest.raises(RoutingError):
        client.route(WAYPOINTS, costing="pedestrian")
