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


def test_different_base_url_is_a_different_cache_entry(tmp_path):
    # A local Valhalla container and the public server may return different routes;
    # they must not share a cache entry.
    p1, p2 = FakePoster(), FakePoster()
    ValhallaClient(base_url="https://valhalla1.openstreetmap.de", cache_dir=tmp_path, poster=p1).route(
        WAYPOINTS, costing="pedestrian"
    )
    ValhallaClient(base_url="http://localhost:8002", cache_dir=tmp_path, poster=p2).route(
        WAYPOINTS, costing="pedestrian"
    )
    assert len(p1.calls) == 1
    assert len(p2.calls) == 1, "local server was served the public server's cached route"


def test_corrupt_cache_entry_is_discarded_and_refetched(tmp_path):
    poster = FakePoster()
    client = ValhallaClient(cache_dir=tmp_path, poster=poster)
    client.route(WAYPOINTS, costing="pedestrian")
    # Simulate a process killed mid-write.
    cache_file = next(tmp_path.glob("*.json"))
    cache_file.write_text(cache_file.read_text()[:20])
    path = client.route(WAYPOINTS, costing="pedestrian")
    assert path.length_m >= 0
    assert len(poster.calls) == 2, "corrupt entry should have forced a refetch"


def test_corrupt_cache_offline_raises_route_not_cached(tmp_path):
    ValhallaClient(cache_dir=tmp_path, poster=FakePoster()).route(WAYPOINTS, costing="pedestrian")
    cache_file = next(tmp_path.glob("*.json"))
    cache_file.write_text("{not json")
    offline = ValhallaClient(cache_dir=tmp_path, offline=True)
    with pytest.raises(RouteNotCached):
        offline.route(WAYPOINTS, costing="pedestrian")


def test_cache_write_leaves_no_temp_files(tmp_path):
    ValhallaClient(cache_dir=tmp_path, poster=FakePoster()).route(WAYPOINTS, costing="pedestrian")
    assert list(tmp_path.glob("*.tmp")) == []


def test_malformed_geometry_raises_routing_error(tmp_path):
    poster = FakePoster(payload={"trip": {"legs": [{"shape": "!"}]}})
    client = ValhallaClient(cache_dir=tmp_path, poster=poster)
    with pytest.raises(RoutingError):
        client.route(WAYPOINTS, costing="pedestrian")


def test_all_repeated_junction_points_are_stripped(tmp_path):
    # Leg 2 opens with the junction point twice over.
    poster = FakePoster(
        payload={
            "trip": {
                "legs": [
                    {"shape": "{n{vn@qmwzfF"},
                    {"shape": "{n{vn@qmwzfF??DyF"},
                ]
            }
        }
    )
    path = ValhallaClient(cache_dir=tmp_path, poster=poster).route(WAYPOINTS, costing="pedestrian")
    assert path.coords == pytest.approx([(25.032958, 121.565417), (25.032955, 121.565542)])
    consecutive_dupes = [a for a, b in zip(path.coords, path.coords[1:]) if a == b]
    assert consecutive_dupes == []


def test_unwritable_cache_dir_does_not_lose_the_route(tmp_path):
    # Caching is an optimisation; failing to cache must not discard a good route.
    import os
    import stat

    ro_dir = tmp_path / "readonly"
    ro_dir.mkdir()
    os.chmod(ro_dir, stat.S_IREAD | stat.S_IEXEC)
    try:
        client = ValhallaClient(cache_dir=ro_dir, poster=FakePoster())
        path = client.route(WAYPOINTS, costing="pedestrian")
        assert path.length_m >= 0
        assert len(path.coords) >= 2
    finally:
        os.chmod(ro_dir, stat.S_IRWXU)


def test_wrong_typed_cache_payload_is_discarded_and_refetched(tmp_path):
    poster = FakePoster()
    client = ValhallaClient(cache_dir=tmp_path, poster=poster)
    client.route(WAYPOINTS, costing="pedestrian")
    # Valid JSON, wrong shape — must be treated as corrupt, not crash on .get()
    next(tmp_path.glob("*.json")).write_text("[1, 2, 3]")
    path = client.route(WAYPOINTS, costing="pedestrian")
    assert len(path.coords) >= 2
    assert len(poster.calls) == 2, "wrong-typed cache entry should force a refetch"


def test_wrong_typed_cache_payload_offline_raises_route_not_cached(tmp_path):
    ValhallaClient(cache_dir=tmp_path, poster=FakePoster()).route(WAYPOINTS, costing="pedestrian")
    next(tmp_path.glob("*.json")).write_text('"just a string"')
    offline = ValhallaClient(cache_dir=tmp_path, offline=True)
    with pytest.raises(RouteNotCached):
        offline.route(WAYPOINTS, costing="pedestrian")
