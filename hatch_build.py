"""Build the GUI's frontend bundle into `web/static/` when packaging a wheel.

`web/static/` is generated, not committed, so a wheel built from a clean
checkout would otherwise ship an API with no UI behind it. This hook runs
`pnpm build` at package-build time and marks the result as an artifact so
hatchling includes it despite `.gitignore`.

Editable installs (`uv sync`) deliberately skip the build: the CLI half of this
tool needs no bundle, and requiring Node to install a Python package would be a
tax on people who never open the GUI. They get the bundle by running `pnpm
build` themselves — `ios-loc gui` says so if it is missing.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

UI_DIR = pathlib.Path("src") / "ios_loc" / "web" / "ui"
STATIC_DIR = pathlib.Path("src") / "ios_loc" / "web" / "static"


class FrontendBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        # An editable install is the *wheel* target built with version
        # "editable" -- checking `self.target_name` here would never match and
        # every `uv sync` would demand pnpm.
        if version == "editable":
            return

        root = pathlib.Path(self.root)
        ui = root / UI_DIR
        if not (ui / "package.json").exists():
            return  # not a source checkout (e.g. building from an sdist)

        pnpm = shutil.which("pnpm")
        if pnpm is None:
            raise RuntimeError(
                "pnpm is required to build the GUI assets into a wheel. Install "
                "Node 20+ and pnpm (https://pnpm.io/installation), or install "
                "this project in editable mode with `uv sync` instead."
            )

        subprocess.run([pnpm, "install", "--frozen-lockfile"], cwd=ui, check=True)
        subprocess.run([pnpm, "build"], cwd=ui, check=True)

        if not (root / STATIC_DIR / "index.html").exists():
            raise RuntimeError(f"`pnpm build` finished but {STATIC_DIR}/index.html is missing.")

        # `web/static/` is gitignored; without this hatchling excludes it.
        build_data.setdefault("artifacts", []).append(f"/{STATIC_DIR.as_posix()}/**")
