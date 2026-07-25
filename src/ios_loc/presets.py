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

# Location-based games stop crediting distance above roughly 20 km/h.
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
                f"(20 km/h) ceiling; movement above it is not credited"
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


@dataclass(frozen=True)
class Place:
    """A named single point — what the set-location pin holds the device at."""

    name: str
    point: Coord


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


def _check_coord_range(lat: float, lon: float, label: str) -> None:
    """Latitude/longitude range shared by every waypoint source (preset TOML,
    CLI `--via`, ad-hoc API waypoints)."""
    if not -90.0 <= lat <= 90.0 or not -180.0 <= lon <= 180.0:
        raise ValueError(f"{label} out of range: latitude {lat}, longitude {lon}")


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
        try:
            _check_coord_range(lat, lon, f"preset {preset_name!r}: waypoint {index}")
        except ValueError as exc:
            raise ConfigError(str(exc)) from exc
        coords.append((lat, lon))
    return coords


def _parse_point(raw: object, place_name: str) -> Coord:
    """Validate a place's single point, naming the place in every error."""
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise ConfigError(
            f"place {place_name!r}: 'point' must be a [latitude, longitude] pair, "
            f"got {raw!r}"
        )
    try:
        lat, lon = float(raw[0]), float(raw[1])
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"place {place_name!r}: point is not numeric: {raw!r}") from exc
    try:
        _check_coord_range(lat, lon, f"place {place_name!r}: point")
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc
    return (lat, lon)


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


def load_places(path: pathlib.Path | None = None) -> dict[str, Place]:
    """Load the named single locations from the config file.

    Deliberately separate from `load_config` rather than a third element of its
    return tuple: every existing caller unpacks two values, and widening that
    signature would be a breaking change bought for nothing. `load_config`
    ignores every top-level table it does not know, so [places.*] needs no
    change there and an older build reading a newer config still works.
    """
    path = pathlib.Path(path) if path else DEFAULT_CONFIG_PATH
    if not path.exists():
        return {}
    data = tomllib.loads(path.read_text())
    places: dict[str, Place] = {}
    for name, raw in data.get("places", {}).items():
        if "point" not in raw:
            raise ConfigError(f"place {name!r} in {path}: missing required 'point'")
        places[name] = Place(name=name, point=_parse_point(raw["point"], name))
    return places


# Shared verbatim by `cli.walk` and `POST /api/walk` so a rephrasing here never
# drifts out of sync between the two callers. The CLI appends its own
# `--via`-specific hint on top of these; the API leaves them as-is.
PRESET_AND_WAYPOINTS_CONFLICT = "pass either a preset name or waypoints, not both"
NEEDS_PRESET_OR_WAYPOINTS = "a walk needs a preset or at least 2 waypoints"
NEEDS_TWO_WAYPOINTS = "a route needs at least 2 waypoints"


@dataclass(frozen=True)
class ResolvedWalk:
    """The concrete, ready-to-run shape of a walk request."""

    waypoints: list[Coord]
    costing: str
    profile: Profile
    loop: bool
    preset_name: str | None = None


def resolve_walk(
    *,
    preset: str | None,
    waypoints: list[Coord] | None,
    profile: str | None,
    speed: float | None,
    costing: str | None,
    loop: bool | None,
    profiles: dict[str, Profile],
    presets: dict[str, Preset],
) -> ResolvedWalk:
    """Resolve a preset name or ad-hoc waypoints, plus overrides, into a
    concrete `ResolvedWalk`. This is the one rule shared by `ios-loc walk` and
    `POST /api/walk` — both parse their own inputs (the CLI's `--via 'lat,lon'`
    strings, the API's JSON body) and both present failures their own way, but
    the resolution rule itself — preset XOR waypoints, profile/speed/costing/
    loop overrides, the 20 km/h ceiling — lives only here.

    Raises `ConfigError` for an unknown preset or profile name, `ValueError`
    for anything else invalid: neither/both of preset and waypoints, too few
    waypoints, an out-of-range coordinate, or an over-ceiling speed.

    Deliberately does not know about routing: whether a `--loop`/`loop=True`
    route actually returns to its start is only knowable after the route is
    built, so that check stays with each caller, after it calls this.
    """
    if preset and waypoints:
        raise ValueError(PRESET_AND_WAYPOINTS_CONFLICT)
    if not preset and not waypoints:
        raise ValueError(NEEDS_PRESET_OR_WAYPOINTS)

    preset_name = None
    if preset:
        if preset not in presets:
            raise ConfigError(f"unknown preset {preset!r}")
        chosen = presets[preset]
        resolved_waypoints = list(chosen.waypoints)
        profile_name = profile or chosen.profile
        resolved_loop = chosen.loop if loop is None else loop
        preset_name = chosen.name
    else:
        assert waypoints is not None  # guaranteed by the guard above
        if len(waypoints) < 2:
            raise ValueError(NEEDS_TWO_WAYPOINTS)
        for index, (lat, lon) in enumerate(waypoints):
            _check_coord_range(lat, lon, f"waypoint {index}")
        resolved_waypoints = list(waypoints)
        profile_name = profile or "walk"
        resolved_loop = bool(loop)

    if profile_name not in profiles:
        raise ConfigError(f"unknown profile {profile_name!r}")
    resolved_profile = profiles[profile_name]

    if speed is not None:
        # Includes the 20 km/h ceiling — never bypass this validation.
        resolved_profile = replace(resolved_profile, speed=speed)

    return ResolvedWalk(
        waypoints=resolved_waypoints,
        costing=costing or resolved_profile.costing,
        profile=resolved_profile,
        loop=resolved_loop,
        preset_name=preset_name,
    )


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


def _strip_tables(text: str, kind: str) -> str:
    """Return `text` with every [<kind>.*] table removed, everything else verbatim.

    A table block runs from its header line to the next table header. Each writer
    regenerates only its own kind, so a hand-written [profiles.*] section and its
    comments -- and the other kind's tables -- survive untouched.
    """
    kept: list[str] = []
    dropping = False
    for line in text.splitlines(keepends=True):
        match = _TOP_LEVEL_TABLE_RE.match(line)
        if match is not None:
            name = match.group(1).strip()
            dropping = name == kind or name.startswith(f"{kind}.")
        if not dropping:
            kept.append(line)
    return "".join(kept)


def _write_atomic(path: pathlib.Path, body: str) -> None:
    """Write `body` to `path` atomically: mkstemp in the target directory (a
    collision-proof name), same-directory os.replace so the rename is atomic,
    and cleanup of the temp file if anything fails partway through, so a bad
    write never leaves a stray .tmp behind. newline="" keeps the caller's line
    endings byte for byte.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _write_tables(path: pathlib.Path, kind: str, tables: dict[str, dict]) -> None:
    """Rewrite the [<kind>.*] section of `path` as `tables`, preserving everything
    else. An empty `tables` leaves no header of that kind behind at all.
    """
    # Read with newline translation disabled so the preserved head keeps its
    # original line endings (a CRLF-authored file is not silently rewritten).
    existing_text = path.read_text(newline="") if path.exists() else ""
    head = _strip_tables(existing_text, kind).rstrip()
    if tables:
        rendered = tomli_w.dumps({kind: tables})
        body = f"{head}\n\n{rendered}" if head else rendered
    else:
        body = f"{head}\n" if head else ""
    _write_atomic(path, body)


def _preset_tables(presets: dict[str, Preset]) -> dict[str, dict]:
    """The TOML shape of a preset collection, name-sorted for a stable file."""
    return {
        name: {
            "waypoints": [[lat, lon] for lat, lon in item.waypoints],
            "profile": item.profile,
            "loop": item.loop,
        }
        for name, item in sorted(presets.items())
    }


def save_preset(path: pathlib.Path | None, preset: Preset) -> None:
    """Write `preset` into the config file, replacing any preset of the same name.

    Everything outside the [presets.*] tables is preserved byte for byte,
    including line endings (a CRLF-authored file stays CRLF); comments inside
    preset tables are not. `preset.profile` is validated against the built-in
    profiles plus any `[profiles.*]` the file already defines. The file is read
    first to load existing presets; if it is already invalid — for example an
    existing preset references a profile that no longer exists — `save_preset`
    raises `ConfigError` without writing, and the file must be repaired by hand.
    If the new preset's profile is unknown, the file is left untouched instead
    of writing something `load_config` would reject. The write is atomic
    (temp + rename) so an interrupted save cannot leave a truncated config
    behind, and a failed write cleans up its own temp file.
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

    merged = dict(existing)
    merged[preset.name] = preset
    _write_tables(path, "presets", _preset_tables(merged))


def delete_preset(path: pathlib.Path | None, name: str) -> None:
    """Remove `name` from the config file's presets.

    Raises `KeyError` if no such preset exists, without touching the file, and
    `ConfigError` if the file is already invalid — the same read-validate-write
    discipline `save_preset` uses. Deleting the last preset leaves no empty
    [presets] header behind.
    """
    path = pathlib.Path(path) if path else DEFAULT_CONFIG_PATH
    _, existing = load_config(path)
    if name not in existing:
        raise KeyError(name)
    remaining = {key: value for key, value in existing.items() if key != name}
    _write_tables(path, "presets", _preset_tables(remaining))


def _place_tables(places: dict[str, Place]) -> dict[str, dict]:
    """The TOML shape of a place collection, name-sorted for a stable file."""
    return {
        name: {"point": [item.point[0], item.point[1]]}
        for name, item in sorted(places.items())
    }


def save_place(path: pathlib.Path | None, place: Place) -> None:
    """Write `place` into the config file, replacing any place of the same name.

    Everything outside the [places.*] tables is preserved byte for byte,
    including line endings and the [presets.*] and [profiles.*] sections. An
    out-of-range point raises `ConfigError` before the file is touched.
    """
    path = pathlib.Path(path) if path else DEFAULT_CONFIG_PATH
    # Validate through the same path the loader uses, before touching the disk.
    _parse_point([place.point[0], place.point[1]], place.name)
    merged = dict(load_places(path))
    merged[place.name] = place
    _write_tables(path, "places", _place_tables(merged))


def delete_place(path: pathlib.Path | None, name: str) -> None:
    """Remove `name` from the config file's places.

    Raises `KeyError` if no such place exists, without touching the file.
    """
    path = pathlib.Path(path) if path else DEFAULT_CONFIG_PATH
    existing = load_places(path)
    if name not in existing:
        raise KeyError(name)
    remaining = {key: value for key, value in existing.items() if key != name}
    _write_tables(path, "places", _place_tables(remaining))
