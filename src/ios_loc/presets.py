"""Speed profiles and named route presets, loaded from TOML."""

from __future__ import annotations

import os
import pathlib
import re
import tempfile
import tomllib
from dataclasses import dataclass, replace

import tomli_w

from ios_loc.path import Coord

# Pikmin Bloom stops crediting distance above roughly 20 km/h.
MAX_SPEED_MPS = 5.56

DEFAULT_CONFIG_PATH = pathlib.Path.home() / ".config" / "ios-loc" / "config.toml"


class ConfigError(ValueError):
    """The configuration file is invalid. Subclasses ValueError so callers
    catching ValueError at the config boundary still work."""


@dataclass(frozen=True)
class Profile:
    """How a mode of travel moves — and how its route should be planned."""

    name: str
    speed: float           # base speed, m/s
    jitter: float          # relative sigma applied per tick
    pause_per_min: float   # probability of starting a pause, per minute
    pause_min_s: float
    pause_max_s: float
    costing: str           # Valhalla costing model

    def __post_init__(self) -> None:
        if self.speed <= 0:
            raise ValueError(f"profile {self.name!r}: speed must be positive")
        if self.speed > MAX_SPEED_MPS:
            raise ValueError(
                f"profile {self.name!r}: speed {self.speed} m/s "
                f"({self.speed * 3.6:.1f} km/h) exceeds the {MAX_SPEED_MPS} m/s "
                f"(20 km/h) ceiling; Pikmin Bloom would not credit the distance"
            )
        if self.jitter < 0:
            raise ValueError(f"profile {self.name!r}: jitter must not be negative")
        if self.pause_per_min < 0:
            raise ValueError(f"profile {self.name!r}: pause_per_min must not be negative")
        if self.pause_min_s < 0:
            raise ValueError(f"profile {self.name!r}: pause_min_s must not be negative")
        if self.pause_min_s > self.pause_max_s:
            raise ValueError(
                f"profile {self.name!r}: pause_min_s ({self.pause_min_s}) exceeds "
                f"pause_max_s ({self.pause_max_s})"
            )


@dataclass(frozen=True)
class Preset:
    """A named route."""

    name: str
    waypoints: list[Coord]
    profile: str = "walk"
    loop: bool = False


DEFAULT_PROFILES: dict[str, Profile] = {
    "walk": Profile(
        name="walk",
        speed=1.3,
        jitter=0.08,
        pause_per_min=0.15,
        pause_min_s=5,
        pause_max_s=30,
        costing="pedestrian",
    ),
    "bike": Profile(
        name="bike",
        speed=4.2,
        jitter=0.12,
        pause_per_min=0.02,
        pause_min_s=10,
        pause_max_s=40,
        costing="bicycle",
    ),
}


def _parse_waypoints(raw: object, preset_name: str) -> list[Coord]:
    """Validate a preset's waypoint list, naming the preset in every error."""
    if not isinstance(raw, list) or len(raw) < 2:
        raise ConfigError(
            f"preset {preset_name!r}: 'waypoints' must be a list of at least "
            f"2 [latitude, longitude] pairs"
        )
    coords: list[Coord] = []
    for index, item in enumerate(raw):
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ConfigError(
                f"preset {preset_name!r}: waypoint {index} must be a "
                f"[latitude, longitude] pair, got {item!r}"
            )
        try:
            lat, lon = float(item[0]), float(item[1])
        except (TypeError, ValueError) as exc:
            raise ConfigError(
                f"preset {preset_name!r}: waypoint {index} is not numeric: {item!r}"
            ) from exc
        if not -90.0 <= lat <= 90.0 or not -180.0 <= lon <= 180.0:
            raise ConfigError(
                f"preset {preset_name!r}: waypoint {index} out of range: "
                f"latitude {lat}, longitude {lon}"
            )
        coords.append((lat, lon))
    return coords


def load_config(
    path: pathlib.Path | None = None,
) -> tuple[dict[str, Profile], dict[str, Preset]]:
    """Load profiles and presets, layering the TOML file over the built-in defaults."""
    path = pathlib.Path(path) if path else DEFAULT_CONFIG_PATH
    profiles = dict(DEFAULT_PROFILES)
    presets: dict[str, Preset] = {}

    if not path.exists():
        return profiles, presets

    data = tomllib.loads(path.read_text())

    for name, raw in data.get("profiles", {}).items():
        # A brand-new profile name inherits `walk`'s defaults for any field the
        # TOML omits; an existing name layers over its own current values.
        base = profiles.get(name, DEFAULT_PROFILES["walk"])
        try:
            profiles[name] = replace(
                base,
                name=name,
                speed=float(raw.get("speed", base.speed)),
                jitter=float(raw.get("jitter", base.jitter)),
                pause_per_min=float(raw.get("pause_per_min", base.pause_per_min)),
                pause_min_s=float(raw.get("pause_min_s", base.pause_min_s)),
                pause_max_s=float(raw.get("pause_max_s", base.pause_max_s)),
                costing=str(raw.get("costing", base.costing)),
            )
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"profile {name!r} in {path}: {exc}") from exc

    for name, raw in data.get("presets", {}).items():
        if "waypoints" not in raw:
            raise ConfigError(f"preset {name!r} in {path}: missing required 'waypoints'")
        profile_name = str(raw.get("profile", "walk"))
        if profile_name not in profiles:
            raise ConfigError(
                f"preset {name!r} in {path}: unknown profile {profile_name!r}; "
                f"available: {', '.join(sorted(profiles))}"
            )
        presets[name] = Preset(
            name=name,
            waypoints=_parse_waypoints(raw["waypoints"], name),
            profile=profile_name,
            loop=bool(raw.get("loop", False)),
        )

    return profiles, presets


# A TOML table header's bracketed content is a dotted sequence of bare keys
# ([A-Za-z0-9_-]+) or quoted keys ("..."/'...'); nothing else is legal there.
# Requiring that shape (rather than "anything but ']'") matters: a line inside
# a multi-line array such as the last, comma-less element of
#     waypoints = [
#         [25.0, 121.0],
#         [25.1, 121.1]
#     ]
# also looks like "[<content>]" but its content ("25.1, 121.1") contains a
# comma and a space, which cannot appear in a dotted key — so it correctly
# fails to match here, whereas a naive "[^\]]+" body would treat it as a table
# header and prematurely stop dropping a [presets.*] block mid-array. The same
# tightened grammar also lets a quoted key legitimately contain "]"
# (`["my]key"]`) without truncating the match early.
_KEY_SEGMENT = r'(?:[A-Za-z0-9_-]+|"(?:[^"\\]|\\.)*"|\'[^\']*\')'
_TOP_LEVEL_TABLE_RE = re.compile(
    rf"^\s*\[\[?\s*({_KEY_SEGMENT}(?:\s*\.\s*{_KEY_SEGMENT})*)\s*\]\]?\s*(?:#.*)?$"
)


def _strip_preset_tables(text: str) -> str:
    """Return `text` with every [presets.*] table removed, everything else verbatim.

    A table block runs from its header line to the next table header. Only the
    preset tables are regenerated on save, so a hand-written [profiles.*] section
    and its comments survive untouched.
    """
    kept: list[str] = []
    dropping = False
    for line in text.splitlines(keepends=True):
        match = _TOP_LEVEL_TABLE_RE.match(line)
        if match is not None:
            name = match.group(1).strip()
            dropping = name == "presets" or name.startswith("presets.")
        if not dropping:
            kept.append(line)
    return "".join(kept)


def save_preset(path: pathlib.Path | None, preset: Preset) -> None:
    """Write `preset` into the config file, replacing any preset of the same name.

    Everything outside the [presets.*] tables is preserved byte for byte,
    including line endings (a CRLF-authored file stays CRLF); comments inside
    preset tables are not. `preset.profile` is validated against the built-in
    profiles plus any `[profiles.*]` the file already defines, before any read-
    modify-write of the target file, so a preset naming an unknown profile
    leaves the file untouched instead of writing something `load_config` will
    then reject. The write is atomic (temp + rename) so an interrupted save
    cannot leave a truncated config behind, and a failed write cleans up its
    own temp file.
    """
    path = pathlib.Path(path) if path else DEFAULT_CONFIG_PATH
    # Validate through the same path the loader uses, before touching the disk.
    _parse_waypoints([[lat, lon] for lat, lon in preset.waypoints], preset.name)

    # `load_config` already handles a missing file (defaults, no presets), so
    # this is also where we learn the profiles a not-yet-written file would
    # accept. Validating here -- before any read-modify-write of the target
    # file -- means a preset naming an unknown profile never touches disk, and
    # never jams `load_config` for every save that follows.
    profiles, existing = load_config(path)
    if preset.profile not in profiles:
        raise ConfigError(
            f"preset {preset.name!r}: unknown profile {preset.profile!r}; "
            f"available: {', '.join(sorted(profiles))}"
        )

    # Read with newline translation disabled so the preserved head keeps its
    # original line endings byte for byte (e.g. a CRLF-authored file is not
    # silently rewritten to LF).
    existing_text = path.read_text(newline="") if path.exists() else ""
    merged = dict(existing)
    merged[preset.name] = preset

    tables = {
        name: {
            "waypoints": [[lat, lon] for lat, lon in item.waypoints],
            "profile": item.profile,
            "loop": item.loop,
        }
        for name, item in sorted(merged.items())
    }
    rendered = tomli_w.dumps({"presets": tables})

    head = _strip_preset_tables(existing_text).rstrip()
    body = f"{head}\n\n{rendered}" if head else rendered

    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic temp + rename, mirroring routing.py's _write_cache: a
    # collision-proof temp name via mkstemp, same-directory os.replace so the
    # rename stays atomic, and cleanup of the temp file if anything fails
    # partway through so a bad write never leaves a stray .tmp behind.
    tmp: str | None = None
    try:
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
        with os.fdopen(fd, "w", newline="") as handle:
            handle.write(body)
        os.replace(tmp, path)
    except BaseException:
        if tmp is not None:
            pathlib.Path(tmp).unlink(missing_ok=True)
        raise
