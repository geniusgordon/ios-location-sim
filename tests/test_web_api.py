import pytest
from fastapi.testclient import TestClient

from ios_loc.presets import Preset, load_config, save_preset
from ios_loc.routing import RoutingError
from ios_loc.web.api import create_app
from ios_loc.web.service import WalkService
from tests.test_web_service import SQUARE, FakeRouteClient, FakeSession, VirtualClock


def _make_app(tmp_path, session=None, static_dir=None):
    route_client = FakeRouteClient()
    clock = VirtualClock()
    service = WalkService(
        route_client=route_client,
        session_factory=(lambda: session) if session is not None else FakeSession,
        clock=clock,
        sleep=clock.sleep,
    )
    app = create_app(
        service=service,
        route_client=route_client,
        config_path=tmp_path / "config.toml",
        static_dir=static_dir,
    )
    return app


@pytest.fixture
def context(tmp_path):
    config = tmp_path / "config.toml"
    route_client = FakeRouteClient()
    session = FakeSession()
    clock = VirtualClock()
    service = WalkService(
        route_client=route_client,
        session_factory=lambda: session,
        clock=clock,
        sleep=clock.sleep,
    )
    app = create_app(service=service, route_client=route_client, config_path=config)
    with TestClient(app) as client:
        yield client, config, route_client, session


def test_presets_start_empty_and_list_built_in_profiles(context):
    client, *_ = context
    body = client.get("/api/presets").json()
    assert body["presets"] == []
    assert "walk" in body["profiles"] and "bike" in body["profiles"]
    assert body["offline"] is False


def test_saving_a_preset_persists_it_to_the_config_file(context):
    client, config, *_ = context
    response = client.post(
        "/api/presets",
        json={"name": "home", "waypoints": [[25.0, 121.0], [25.1, 121.1]], "loop": True},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "home"

    _, presets = load_config(config)
    assert presets["home"].loop is True


def test_saving_a_preset_with_an_unknown_profile_is_a_400(context):
    client, *_ = context
    response = client.post(
        "/api/presets",
        json={"name": "x", "waypoints": [[25.0, 121.0], [25.1, 121.1]], "profile": "nope"},
    )
    assert response.status_code == 400
    assert "nope" in response.json()["detail"]


def test_route_returns_the_polyline_for_the_editor(context):
    client, _, route_client, _ = context
    response = client.post(
        "/api/route",
        json={"waypoints": [[25.0, 121.0], [25.1, 121.1]], "costing": "bicycle"},
    )
    body = response.json()
    assert body["coords"] == [[lat, lon] for lat, lon in SQUARE]
    assert body["length_m"] > 0
    assert route_client.calls[-1][1] == "bicycle"


def test_a_routing_failure_is_a_502_with_the_real_message(tmp_path):
    route_client = FakeRouteClient(error=RoutingError("valhalla said no"))
    clock = VirtualClock()
    service = WalkService(
        route_client=route_client,
        session_factory=FakeSession,
        clock=clock,
        sleep=clock.sleep,
    )
    app = create_app(
        service=service, route_client=route_client, config_path=tmp_path / "config.toml"
    )
    with TestClient(app) as client:
        response = client.post("/api/route", json={"waypoints": [[1.0, 2.0], [3.0, 4.0]]})
    assert response.status_code == 502
    assert "valhalla said no" in response.json()["detail"]


def test_walk_is_idle_before_it_starts(context):
    client, *_ = context
    assert client.get("/api/walk").json()["state"] == "idle"


def test_starting_a_walk_from_waypoints(context):
    client, _, _, session = context
    response = client.post(
        "/api/walk",
        json={"waypoints": [[25.0, 121.0], [25.1, 121.1]], "duration_s": 3},
    )
    assert response.status_code == 200
    assert response.json()["state"] == "walking"
    client.delete("/api/walk")


def test_starting_a_second_walk_is_a_409(context):
    client, *_ = context
    client.post("/api/walk", json={"waypoints": [[25.0, 121.0], [25.1, 121.1]]})
    response = client.post("/api/walk", json={"waypoints": [[25.0, 121.0], [25.1, 121.1]]})
    assert response.status_code == 409
    client.delete("/api/walk")


def test_starting_with_both_preset_and_waypoints_is_a_400(context):
    client, *_ = context
    response = client.post(
        "/api/walk",
        json={"preset": "home", "waypoints": [[25.0, 121.0], [25.1, 121.1]]},
    )
    assert response.status_code == 400


def test_starting_from_a_saved_preset(context):
    client, config, *_ = context
    save_preset(config, Preset(name="home", waypoints=[(25.0, 121.0), (25.1, 121.1)]))
    response = client.post("/api/walk", json={"preset": "home"})
    assert response.status_code == 200
    assert response.json()["preset_name"] == "home"
    client.delete("/api/walk")


def test_an_over_ceiling_speed_is_a_400(context):
    client, *_ = context
    response = client.post(
        "/api/walk",
        json={"waypoints": [[25.0, 121.0], [25.1, 121.1]], "speed": 12.0},
    )
    assert response.status_code == 400
    assert "ceiling" in response.json()["detail"]


def test_deleting_the_walk_stops_it(context):
    client, _, _, session = context
    client.post("/api/walk", json={"waypoints": [[25.0, 121.0], [25.1, 121.1]]})
    response = client.delete("/api/walk")
    assert response.json()["state"] == "idle"
    assert session.cleared is True


def test_a_device_failure_at_start_is_a_503_with_the_real_cause(tmp_path):
    class FailingSession(FakeSession):
        async def start(self, attempts=3):
            raise ConnectionError("no device found")

    app = _make_app(tmp_path, session=FailingSession())
    with TestClient(app) as client:
        response = client.post(
            "/api/walk",
            json={"waypoints": [[25.0, 121.0], [25.1, 121.1]]},
        )
    assert response.status_code == 503
    assert "no device found" in response.json()["detail"]


def test_a_programming_error_at_start_is_not_a_503(tmp_path):
    class BuggySession(FakeSession):
        async def start(self, attempts=3):
            raise TypeError("bad argument")

    app = _make_app(tmp_path, session=BuggySession())
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/walk",
            json={"waypoints": [[25.0, 121.0], [25.1, 121.1]]},
        )
    assert response.status_code == 500
    assert response.status_code != 503


def test_api_routes_still_resolve_when_a_static_dir_is_mounted(tmp_path):
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html>ui</html>")

    app = _make_app(tmp_path, static_dir=static_dir)
    with TestClient(app) as client:
        response = client.get("/api/walk")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["state"] == "idle"
