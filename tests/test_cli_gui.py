import pathlib

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from ios_loc import cli

runner = CliRunner()


@pytest.fixture
def built_assets(monkeypatch, tmp_path):
    """A stand-in for `pnpm build` output.

    `web/static/` is generated and gitignored, so these tests must not depend
    on whether the developer running them has built the frontend.
    """
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html>ui</html>")
    monkeypatch.setattr(cli, "DEFAULT_STATIC_DIR", static)
    return static


def test_build_gui_app_serves_the_api(tmp_path):
    app = cli.build_gui_app(
        config=tmp_path / "config.toml", offline=False, udid=None, static_dir=None
    )
    with TestClient(app) as client:
        assert client.get("/api/walk").json()["state"] == "idle"


def test_offline_is_reported_to_the_ui(tmp_path):
    app = cli.build_gui_app(
        config=tmp_path / "config.toml", offline=True, udid=None, static_dir=None
    )
    with TestClient(app) as client:
        assert client.get("/api/presets").json()["offline"] is True


def test_gui_command_serves_on_the_requested_port(monkeypatch, tmp_path, built_assets):
    calls = {}

    def fake_run(app, host, port, log_level="info"):
        calls["host"] = host
        calls["port"] = port

    monkeypatch.setattr(cli.uvicorn, "run", fake_run)
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: calls.setdefault("opened", url))

    result = runner.invoke(
        cli.app, ["gui", "--port", "9999", "--no-open", "--config", str(tmp_path / "c.toml")]
    )
    assert result.exit_code == 0, result.output
    assert calls["port"] == 9999
    assert calls["host"] == "127.0.0.1"
    assert "opened" not in calls


def test_gui_refuses_to_serve_when_the_bundle_is_missing(monkeypatch, tmp_path):
    """An unbuilt frontend must fail loudly, not serve a 404 page.

    The API mounts happily with no static dir, so without this check `ios-loc
    gui` would start, print a URL, and hand back a blank page.
    """
    monkeypatch.setattr(cli, "DEFAULT_STATIC_DIR", tmp_path / "never-built")
    monkeypatch.setattr(cli.uvicorn, "run", lambda *a, **k: pytest.fail("served anyway"))

    result = runner.invoke(cli.app, ["gui", "--no-open", "--config", str(tmp_path / "c.toml")])

    assert result.exit_code != 0
    assert "pnpm build" in result.output
    assert "index.html" in result.output


def test_the_default_static_dir_points_inside_the_package():
    assert cli.DEFAULT_STATIC_DIR == pathlib.Path(cli.__file__).parent / "web" / "static"


def test_gui_command_opens_browser_by_default(monkeypatch, tmp_path, built_assets):
    """Verify that `gui` without --no-open calls webbrowser.open with correct URL."""
    calls = {}

    def fake_run(app, host, port, log_level="info"):
        calls["host"] = host
        calls["port"] = port

    monkeypatch.setattr(cli.uvicorn, "run", fake_run)
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: calls.setdefault("opened", url))

    result = runner.invoke(
        cli.app, ["gui", "--port", "8765", "--config", str(tmp_path / "c.toml")]
    )
    assert result.exit_code == 0, result.output
    assert calls["opened"] == "http://127.0.0.1:8765"


def test_build_gui_app_handles_missing_static_dir(tmp_path):
    """Verify that non-existent static_dir doesn't raise and API still works."""
    non_existent_dir = tmp_path / "does" / "not" / "exist"

    app = cli.build_gui_app(
        config=tmp_path / "config.toml",
        offline=False,
        udid=None,
        static_dir=non_existent_dir,
    )
    with TestClient(app) as client:
        assert client.get("/api/walk").json()["state"] == "idle"
