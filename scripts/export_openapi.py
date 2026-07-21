"""Dump the GUI's OpenAPI schema. The frontend generates its types from this."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from ios_loc.cli import build_gui_app  # noqa: E402

DEFAULT_OUT = pathlib.Path(__file__).resolve().parent.parent / "src/ios_loc/web/ui/api-schema.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    app = build_gui_app(config=None, offline=False, udid=None, static_dir=None)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
