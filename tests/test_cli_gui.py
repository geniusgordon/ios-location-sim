import pathlib

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from ios_loc import cli

runner = CliRunner()


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


def test_gui_command_serves_on_the_requested_port(monkeypatch, tmp_path):
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


def test_the_placeholder_page_is_shipped():
    static = pathlib.Path(cli.__file__).parent / "web" / "static" / "index.html"
    assert static.exists()
