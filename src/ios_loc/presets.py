"""Speed profiles and named route presets, loaded from TOML."""

from __future__ import annotations

import pathlib
import tomllib
from dataclasses import dataclass, replace

from ios_loc.path import Coord

# Pikmin Bloom stops crediting distance above roughly 20 km/h.
MAX_SPEED_MPS = 5.56

DEFAULT_CONFIG_PATH = pathlib.Path.home() / ".config" / "ios-loc" / "config.toml"


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
        base = profiles.get(name, DEFAULT_PROFILES["walk"])
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

    for name, raw in data.get("presets", {}).items():
        presets[name] = Preset(
            name=name,
            waypoints=[(float(lat), float(lon)) for lat, lon in raw["waypoints"]],
            profile=str(raw.get("profile", "walk")),
            loop=bool(raw.get("loop", False)),
        )

    return profiles, presets
