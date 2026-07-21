import json
import pathlib
import subprocess
import sys

SCHEMA = pathlib.Path("src/ios_loc/web/ui/api-schema.json")


def test_the_committed_schema_matches_the_current_api(tmp_path):
    """Fails when a route or model changed without re-running the exporter."""
    out = tmp_path / "api-schema.json"
    subprocess.run(
        [sys.executable, "scripts/export_openapi.py", "--out", str(out)],
        check=True,
        capture_output=True,
    )
    assert json.loads(out.read_text()) == json.loads(SCHEMA.read_text()), (
        "API schema is stale — run: uv run python scripts/export_openapi.py"
    )


def test_the_schema_describes_the_walk_routes():
    schema = json.loads(SCHEMA.read_text())
    assert "/api/walk" in schema["paths"]
    assert "WalkStatus" in schema["components"]["schemas"]
    assert "FixOut" in schema["components"]["schemas"]
