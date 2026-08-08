import pathlib
import time

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient
from starlette.websockets import WebSocket as StarletteWebSocket

from ios_loc.presets import Preset, load_config, load_places, save_preset
from ios_loc.routing import RoutingError
from ios_loc.web.api import create_app
from ios_loc.web.models import DeviceStatus
from ios_loc.web.service import WalkService
from tests.conftest import SQUARE, FakeRouteClient, FakeSession, VirtualClock


def _make_app(tmp_path, session=None, static_dir=None, device_probe=None):
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
        device_probe=device_probe,
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


def test_presets_start_empty_and_list_built_in_paces(context):
    client, *_ = context
    body = client.get("/api/presets").json()
    assert body["presets"] == []
    # Each pace carries its speed so the GUI can show what picking it means
    # without hardcoding a second copy of the built-in numbers.
    assert {p["name"] for p in body["paces"]} >= {"walk", "bike"}
    by_name = {p["name"]: p["speed_mps"] for p in body["paces"]}
    assert by_name["bike"] > by_name["walk"] > 0
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


def test_saving_a_preset_with_an_unknown_pace_is_a_400(context):
    client, *_ = context
    response = client.post(
        "/api/presets",
        json={"name": "x", "waypoints": [[25.0, 121.0], [25.1, 121.1]], "pace": "nope"},
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
    client, _, _, _ = context
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


def test_rerouting_a_running_walk_updates_the_route(context):
    client, *_ = context
    with client.websocket_connect("/ws") as socket:
        assert socket.receive_json()["type"] == "snapshot"
        client.post("/api/walk", json={"waypoints": [[25.0, 121.0], [25.1, 121.1]]})
        msg = socket.receive_json()
        while msg["type"] != "fix":
            msg = socket.receive_json()

    response = client.patch("/api/walk/route", json={"waypoints": [[25.05, 121.05]]})
    assert response.status_code == 200
    assert response.json()["route"] == [[lat, lon] for lat, lon in SQUARE]
    client.delete("/api/walk")


def test_rerouting_an_idle_walk_is_a_409(context):
    client, *_ = context
    response = client.patch("/api/walk/route", json={"waypoints": [[25.05, 121.05]]})
    assert response.status_code == 409


def test_rerouting_a_looping_walk_is_a_409(context):
    client, *_ = context
    with client.websocket_connect("/ws") as socket:
        assert socket.receive_json()["type"] == "snapshot"
        client.post("/api/walk", json={"waypoints": [[25.0, 121.0], [25.1, 121.1]], "loop": True})
        msg = socket.receive_json()
        while msg["type"] != "fix":
            msg = socket.receive_json()

    response = client.patch("/api/walk/route", json={"waypoints": [[25.05, 121.05]]})
    assert response.status_code == 409
    client.delete("/api/walk")


def test_rerouting_with_a_routing_failure_is_a_502(context):
    client, _, route_client, _ = context
    with client.websocket_connect("/ws") as socket:
        assert socket.receive_json()["type"] == "snapshot"
        client.post("/api/walk", json={"waypoints": [[25.0, 121.0], [25.1, 121.1]]})
        msg = socket.receive_json()
        while msg["type"] != "fix":
            msg = socket.receive_json()

    route_client.error = RoutingError("valhalla said no")
    response = client.patch("/api/walk/route", json={"waypoints": [[25.05, 121.05]]})
    assert response.status_code == 502
    assert "valhalla said no" in response.json()["detail"]
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


def test_app_shutdown_clears_the_device_if_a_walk_is_running(tmp_path):
    """Ctrl-C (or any process exit) must not leave the phone frozen at a fake
    position with the tunnel open. `TestClient` used as a context manager runs
    the app's lifespan startup on enter and shutdown on exit, which is the
    same event uvicorn fires on a real Ctrl-C -- so exiting the `with` block
    below without ever calling DELETE /api/walk stands in for that."""
    route_client = FakeRouteClient()
    session = FakeSession()
    clock = VirtualClock()
    service = WalkService(
        route_client=route_client,
        session_factory=lambda: session,
        clock=clock,
        sleep=clock.sleep,
    )
    app = create_app(
        service=service, route_client=route_client, config_path=tmp_path / "config.toml"
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/walk",
            json={"waypoints": [[25.0, 121.0], [25.1, 121.1]], "duration_s": 100},
        )
        assert response.status_code == 200
        assert response.json()["state"] == "walking"
        # No DELETE /api/walk here -- the process is "killed" by the `with`
        # block exiting instead, exactly like a Ctrl-C during a walk.

    assert session.cleared is True, "shutdown must clear the device even mid-walk"
    assert session.stopped is True


def test_app_shutdown_with_no_walk_running_does_not_raise(tmp_path):
    route_client = FakeRouteClient()
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
        assert client.get("/api/walk").json()["state"] == "idle"
    # Reaching here without an exception is the assertion.


def test_an_out_of_range_latitude_is_a_400_not_a_started_walk(context):
    """The API's ad-hoc waypoint path must enforce the same latitude/longitude
    range as presets and the CLI (Finding 3) -- routed through the shared
    `resolve_walk`, not a fourth copy of the check."""
    client, *_ = context
    response = client.post(
        "/api/walk",
        json={"waypoints": [[999.0, 121.0], [25.1, 121.1]]},
    )
    assert response.status_code == 400
    assert client.get("/api/walk").json()["state"] == "idle"


def test_a_malformed_waypoint_pair_is_a_422_not_a_500(context):
    """A 3-element (or 1-element) coordinate pair must fail Pydantic validation
    before any handler runs, not raise a bare ValueError (Finding 4)."""
    client, *_ = context
    for path in ("/api/walk", "/api/route", "/api/presets"):
        body = {"waypoints": [[1.0, 2.0, 3.0], [4.0, 5.0]]}
        if path == "/api/presets":
            body["name"] = "bad"
        response = client.post(path, json=body)
        assert response.status_code == 422, f"{path}: {response.status_code}"


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


def test_the_socket_opens_with_a_snapshot(context):
    client, *_ = context
    with client.websocket_connect("/ws") as socket:
        message = socket.receive_json()
    assert message["type"] == "snapshot"
    assert message["status"]["state"] == "idle"


def test_the_socket_streams_fixes_then_a_finished_state(context):
    client, *_ = context
    with client.websocket_connect("/ws") as socket:
        assert socket.receive_json()["type"] == "snapshot"
        client.post(
            "/api/walk",
            json={"waypoints": [[25.0, 121.0], [25.1, 121.1]], "duration_s": 2},
        )
        seen = [socket.receive_json() for _ in range(4)]

    kinds = [m["type"] for m in seen]
    assert kinds.count("fix") == 2
    # The terminal broadcast carries the authoritative final stats alongside
    # the state, so a WebSocket-only consumer never has to re-GET /api/walk
    # to learn the final numbers (Finding 3).
    assert seen[-1] == {
        "type": "state",
        "state": "finished",
        "error": None,
        "stats": {
            "elapsed_s": 2.0,
            "distance_m": seen[-1]["stats"]["distance_m"],
            "laps": 0,
            "reconnects": 0,
            "ticks": 2,
        },
    }


def test_two_viewers_each_get_their_own_snapshot_and_full_stream(context):
    client, *_ = context
    with client.websocket_connect("/ws") as first, client.websocket_connect("/ws") as second:
        assert first.receive_json()["type"] == "snapshot"
        assert second.receive_json()["type"] == "snapshot"

        client.post(
            "/api/walk",
            json={"waypoints": [[25.0, 121.0], [25.1, 121.1]], "duration_s": 2},
        )
        # "walking" (start), two fixes, then "finished" -- both viewers see the
        # identical sequence, each from its own independent queue.
        first_seen = [first.receive_json() for _ in range(4)]
        second_seen = [second.receive_json() for _ in range(4)]

    expected = ["state", "fix", "fix", "state"]
    assert [m["type"] for m in first_seen] == expected
    assert [m["type"] for m in second_seen] == expected


def test_a_disconnected_socket_does_not_stop_the_walk(tmp_path):
    """A departed mid-walk viewer must neither stop the walk nor linger as a
    subscriber. Built inline (rather than off the shared `context` fixture)
    so the test can reach `service._subscribers` directly and check the
    cleanup, not just that a fresh connection still works (Finding 5)."""
    route_client = FakeRouteClient()
    clock = VirtualClock()
    session = FakeSession()
    service = WalkService(
        route_client=route_client,
        session_factory=lambda: session,
        clock=clock,
        sleep=clock.sleep,
    )
    app = create_app(
        service=service, route_client=route_client, config_path=tmp_path / "config.toml"
    )

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as socket:
            assert socket.receive_json()["type"] == "snapshot"
            client.post(
                "/api/walk",
                json={"waypoints": [[25.0, 121.0], [25.1, 121.1]], "duration_s": 2},
            )
            # Close immediately, mid-walk, without draining any fixes.

        # Whether the departed viewer's subscription is actually released is
        # covered by test_an_idle_departed_socket_is_cleaned_up_even_with_no_walk_running
        # (this test's own teardown is driven by Starlette's test-session
        # cancellation, not the handler's own disconnect-detection path, so
        # asserting `service._subscribers == set()` here would pass even
        # against an unfixed handler).

        # The walk is still running/finishing on the service side, unaffected by
        # the departed viewer; a fresh connection can still see it end cleanly.
        with client.websocket_connect("/ws") as socket:
            message = socket.receive_json()
            assert message["type"] == "snapshot"
            assert message["status"]["state"] in ("walking", "finished")
        client.delete("/api/walk")


def test_an_idle_departed_socket_is_cleaned_up_even_with_no_walk_running(tmp_path):
    """A closed tab must not leave its subscription (and connection) parked
    forever when the service is idle and nothing is ever broadcast to notice
    the disconnect through (Finding 2). Before the fix, the handler only ever
    awaits `queue.get()` and `send_json`, so with no walk running there is no
    traffic at all to fail against, and a departed client's handler blocks on
    `queue.get()` forever.

    Exiting `client.websocket_connect(...)`'s own `with` block is not a fair
    test of this: Starlette's `WebSocketTestSession.__exit__` forcibly cancels
    the server-side task after sending the disconnect (see the comment on
    `test_a_real_websocketdisconnect_during_send_is_handled_and_cleans_up`
    above), which would clean up the subscription regardless of whether the
    handler ever reads the socket. So this test calls `.close()` directly --
    sending a genuine ASGI `websocket.disconnect` message with no cancellation
    -- and polls for cleanup from *outside* that `with` block, the same way a
    real client's TCP drop would look to a long-lived uvicorn process.
    """
    route_client = FakeRouteClient()
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

    with TestClient(app) as client, client.websocket_connect("/ws") as socket:
        assert socket.receive_json()["type"] == "snapshot"
        # No walk started -- idle, no broadcast traffic whatsoever. Just
        # send a real disconnect, without tearing down the whole session.
        socket.close()

        deadline = time.monotonic() + 2.0
        while service._subscribers and time.monotonic() < deadline:
            time.sleep(0.01)

        assert service._subscribers == set(), (
            "the handler must notice a departed idle client on its own"
        )


def test_a_real_websocketdisconnect_during_send_is_handled_and_cleans_up(tmp_path, monkeypatch):
    """Drive the `except WebSocketDisconnect` branch directly, rather than relying
    on TestClient teardown (which ends the handler via CancelledError instead,
    never actually raising WebSocketDisconnect from send_json)."""
    route_client = FakeRouteClient()
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

    original_send_json = StarletteWebSocket.send_json
    calls = {"n": 0}

    async def flaky_send_json(self, data):
        calls["n"] += 1
        # Call 1 is the connect snapshot -- let it through so the test client
        # observes a normal connection. Call 2 is the first broadcast (the
        # "walking" state message) -- fail it like a dropped real socket would.
        if calls["n"] == 2:
            raise WebSocketDisconnect(code=1006)
        return await original_send_json(self, data)

    monkeypatch.setattr(StarletteWebSocket, "send_json", flaky_send_json)

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as socket:
            assert socket.receive_json()["type"] == "snapshot"
            # This triggers the broadcast that the patched send_json turns into
            # a WebSocketDisconnect on the server side.
            response = client.post(
                "/api/walk",
                json={"waypoints": [[25.0, 121.0], [25.1, 121.1]], "duration_s": 2},
            )
            assert response.status_code == 200

        # (a) the handler must have exited cleanly -- no exception escaped the
        # `with client.websocket_connect(...)` block above, which is itself
        # part of the proof.
        # (b) its subscription must be released.
        assert service._subscribers == set()
        # (c) the walk itself is unaffected by the departed viewer.
        status_response = client.get("/api/walk")
        assert status_response.status_code == 200
        assert status_response.json()["state"] in ("walking", "finished")
        client.delete("/api/walk")


def test_the_socket_still_resolves_when_a_static_dir_is_mounted(tmp_path):
    """Route registration order matters: a `/` StaticFiles mount registered
    before the websocket route would swallow every request, `/ws` included."""
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html>ui</html>")

    app = _make_app(tmp_path, static_dir=static_dir)
    with TestClient(app) as client, client.websocket_connect("/ws") as socket:
        message = socket.receive_json()

    assert message["type"] == "snapshot"
    assert message["status"]["state"] == "idle"


def test_only_the_snapshot_carries_route_and_trail(context):
    """The whole point of splitting snapshot/fix/state messages is that route
    and trail ride along once, at connect, instead of every tick."""
    client, *_ = context
    with client.websocket_connect("/ws") as socket:
        snapshot = socket.receive_json()
        assert snapshot["type"] == "snapshot"
        assert "route" in snapshot["status"]
        assert "trail" in snapshot["status"]

        client.post(
            "/api/walk",
            json={"waypoints": [[25.0, 121.0], [25.1, 121.1]], "duration_s": 2},
        )
        seen = [socket.receive_json() for _ in range(4)]

    for message in seen:
        assert message["type"] in ("fix", "state")
        assert "route" not in message
        assert "trail" not in message


def test_a_present_bundle_is_a_real_build(tmp_path):
    """If a bundle exists, it must be a real build, not a stale scaffold.

    `web/static/` is generated by `pnpm build` and is not committed, so this
    skips on a fresh checkout and only guards developers (and CI jobs) that
    have actually built the frontend.
    """
    import ios_loc.web.api as web_api

    static = pathlib.Path(web_api.__file__).parent / "static"
    if not (static / "index.html").exists():
        pytest.skip("frontend not built (run `pnpm build` in web/ui)")
    index = (static / "index.html").read_text(encoding="utf-8")
    assert '<div id="root">' in index, "static/index.html is not the built React app"
    assert "/assets/" in index, "built index.html does not reference a hashed bundle"

    client = TestClient(_make_app(tmp_path, static_dir=static))
    assert client.get("/").headers["content-type"].startswith("text/html")
    assert client.get("/api/walk").json()["state"] == "idle"


def _probe_returning(status: DeviceStatus):
    async def _probe():
        return status

    return _probe


def test_device_status_reports_ok(tmp_path):
    app = _make_app(
        tmp_path,
        device_probe=_probe_returning(DeviceStatus(connected=True, reason="ok", detail="iOS 17.5")),
    )
    with TestClient(app) as client:
        resp = client.get("/api/device")
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"connected": True, "reason": "ok", "detail": "iOS 17.5"}


def test_device_status_reports_tunneld_down(tmp_path):
    app = _make_app(
        tmp_path,
        device_probe=_probe_returning(
            DeviceStatus(connected=False, reason="tunneld_down", detail="not running")
        ),
    )
    with TestClient(app) as client:
        resp = client.get("/api/device")
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is False
        assert body["reason"] == "tunneld_down"


def test_device_status_reports_no_device(tmp_path):
    app = _make_app(
        tmp_path,
        device_probe=_probe_returning(
            DeviceStatus(connected=False, reason="no_device", detail="no tunnels")
        ),
    )
    with TestClient(app) as client:
        resp = client.get("/api/device")
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is False
        assert body["reason"] == "no_device"


def test_device_status_reports_error(tmp_path):
    app = _make_app(
        tmp_path,
        device_probe=_probe_returning(
            DeviceStatus(connected=False, reason="error", detail="RuntimeError: boom")
        ),
    )
    with TestClient(app) as client:
        resp = client.get("/api/device")
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is False
        assert body["reason"] == "error"


def test_device_status_probe_exception_is_a_200_error_status(tmp_path):
    async def boom():
        raise RuntimeError("device_probe itself blew up")

    app = _make_app(tmp_path, device_probe=boom)
    with TestClient(app) as client:
        resp = client.get("/api/device")
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is False
        assert body["reason"] == "error"


def test_pin_sets_the_device_and_reports_pinned(tmp_path):
    session = FakeSession()
    app = _make_app(tmp_path, session=session)
    with TestClient(app) as client:
        resp = client.post("/api/pin", json={"lat": 48.858666, "lon": 2.293991})
        assert resp.status_code == 200
        body = resp.json()
        assert body["state"] == "pinned"
        assert body["fix"]["lat"] == 48.858666
        assert body["fix"]["lon"] == 2.293991
    # Leaving the TestClient context runs lifespan shutdown -> service.stop(),
    # which clears the pinned device.
    assert session.cleared is True


def test_pin_rejects_out_of_range_coordinates(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        resp = client.post("/api/pin", json={"lat": 200.0, "lon": 2.0})
        assert resp.status_code == 422


def test_pin_while_walking_is_409(tmp_path):
    # A never-completing set() keeps the walk alive across the pin attempt.
    session = FakeSession()
    app = _make_app(tmp_path, session=session)
    with TestClient(app) as client:
        started = client.post("/api/walk", json={"waypoints": SQUARE, "duration_s": 3600})
        assert started.status_code == 200
        resp = client.post("/api/pin", json={"lat": 48.858666, "lon": 2.293991})
        assert resp.status_code == 409
        client.delete("/api/walk")


def test_pin_session_lost_is_503_and_does_not_hang(tmp_path):
    from ios_loc.session import SessionLost

    class LostSession(FakeSession):
        async def set(self, lat, lon, deadline=None):
            await super().set(lat, lon, deadline=deadline)
            raise SessionLost("device unreachable at deadline")

    session = LostSession()
    app = _make_app(tmp_path, session=session)
    with TestClient(app) as client:
        resp = client.post("/api/pin", json={"lat": 48.858666, "lon": 2.293991})
        assert resp.status_code == 503


def test_pin_device_failure_is_503(tmp_path):
    session = FakeSession(fail_with=RuntimeError("tunnel gone"), fail_on=1)
    app = _make_app(tmp_path, session=session)
    with TestClient(app) as client:
        resp = client.post("/api/pin", json={"lat": 48.858666, "lon": 2.293991})
        assert resp.status_code == 503


def test_pin_programming_error_is_500_not_503(tmp_path):
    session = FakeSession(fail_with=TypeError("bug in set"), fail_on=1)
    app = _make_app(tmp_path, session=session)
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post("/api/pin", json={"lat": 48.858666, "lon": 2.293991})
        assert resp.status_code == 500


def test_deleting_a_preset_removes_it(context):
    client, config, *_ = context
    client.post(
        "/api/presets",
        json={"name": "home", "waypoints": [[25.0, 121.0], [25.1, 121.1]]},
    )

    response = client.delete("/api/presets/home")

    assert response.status_code == 204
    _, presets = load_config(config)
    assert presets == {}


def test_deleting_an_unknown_preset_is_a_404(context):
    client, *_ = context
    response = client.delete("/api/presets/nope")
    assert response.status_code == 404
    assert "nope" in response.json()["detail"]


def test_deleting_a_preset_whose_name_needs_escaping(context):
    client, config, *_ = context
    client.post(
        "/api/presets",
        json={"name": "my route", "waypoints": [[25.0, 121.0], [25.1, 121.1]]},
    )

    assert client.delete("/api/presets/my%20route").status_code == 204
    _, presets = load_config(config)
    assert presets == {}


def test_places_start_empty(context):
    client, *_ = context
    assert client.get("/api/places").json() == {"places": []}


def test_saving_a_place_persists_it_and_lists_it(context):
    client, config, *_ = context
    response = client.post("/api/places", json={"name": "home", "point": [25.0, 121.0]})

    assert response.status_code == 200
    assert response.json() == {"name": "home", "point": [25.0, 121.0]}
    assert load_places(config)["home"].point == (25.0, 121.0)
    assert client.get("/api/places").json()["places"] == [{"name": "home", "point": [25.0, 121.0]}]


def test_places_are_listed_name_sorted(context):
    client, *_ = context
    client.post("/api/places", json={"name": "zoo", "point": [1.0, 2.0]})
    client.post("/api/places", json={"name": "attic", "point": [3.0, 4.0]})

    names = [place["name"] for place in client.get("/api/places").json()["places"]]
    assert names == ["attic", "zoo"]


def test_saving_an_out_of_range_place_is_a_400(context):
    client, *_ = context
    response = client.post("/api/places", json={"name": "bad", "point": [125.0, 0.0]})
    assert response.status_code == 400
    assert "out of range" in response.json()["detail"]


def test_saving_a_place_with_an_empty_name_is_a_422(context):
    client, *_ = context
    assert client.post("/api/places", json={"name": "", "point": [1.0, 2.0]}).status_code == 422


def test_deleting_a_place_removes_it(context):
    client, config, *_ = context
    client.post("/api/places", json={"name": "home", "point": [25.0, 121.0]})

    assert client.delete("/api/places/home").status_code == 204
    assert load_places(config) == {}


def test_deleting_an_unknown_place_is_a_404(context):
    client, *_ = context
    response = client.delete("/api/places/nope")
    assert response.status_code == 404
    assert "nope" in response.json()["detail"]
