"""Wire types for the GUI. Converters only — no behaviour lives here."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from ios_loc.path import Coord
from ios_loc.presets import DEFAULT_COSTING, Pace, Place, Preset
from ios_loc.runner import WalkStats
from ios_loc.walker import Fix


class WalkState(str, Enum):
    IDLE = "idle"
    STARTING = "starting"
    WALKING = "walking"
    RECONNECTING = "reconnecting"
    FINISHED = "finished"
    ERROR = "error"
    PINNED = "pinned"


class FixOut(BaseModel):
    elapsed_s: float
    lat: float
    lon: float
    distance_m: float
    speed_mps: float
    paused: bool

    @classmethod
    def from_fix(cls, fix: Fix) -> FixOut:
        return cls(
            elapsed_s=fix.elapsed_s,
            lat=fix.lat,
            lon=fix.lon,
            distance_m=fix.distance_m,
            speed_mps=fix.speed_mps,
            paused=fix.paused,
        )


class StatsOut(BaseModel):
    elapsed_s: float
    distance_m: float
    laps: int
    reconnects: int
    ticks: int

    @classmethod
    def from_stats(cls, stats: WalkStats) -> StatsOut:
        return cls(
            elapsed_s=stats.elapsed_s,
            distance_m=stats.distance_m,
            laps=stats.laps,
            reconnects=stats.reconnects,
            ticks=stats.ticks,
        )


class PresetOut(BaseModel):
    name: str
    waypoints: list[list[float]]
    pace: str
    loop: bool
    costing: str

    @classmethod
    def from_preset(cls, preset: Preset) -> PresetOut:
        return cls(
            name=preset.name,
            waypoints=[[lat, lon] for lat, lon in preset.waypoints],
            pace=preset.pace,
            loop=preset.loop,
            costing=preset.costing,
        )


class PaceOut(BaseModel):
    """A selectable pace. Carries `speed_mps` so the GUI can show what picking
    it actually means without a second request or a hardcoded copy of the
    built-in speeds."""

    name: str
    speed_mps: float

    @classmethod
    def from_pace(cls, pace: Pace) -> PaceOut:
        return cls(name=pace.name, speed_mps=pace.speed)


class PresetsListOut(BaseModel):
    presets: list[PresetOut]
    paces: list[PaceOut]
    offline: bool


class PresetIn(BaseModel):
    name: str = Field(min_length=1)
    waypoints: list[Coord] = Field(min_length=2)
    pace: str = "walk"
    loop: bool = False
    costing: str = DEFAULT_COSTING


class PlaceOut(BaseModel):
    name: str
    point: list[float]

    @classmethod
    def from_place(cls, place: Place) -> PlaceOut:
        return cls(name=place.name, point=[place.point[0], place.point[1]])


class PlacesListOut(BaseModel):
    places: list[PlaceOut]


class PlaceIn(BaseModel):
    name: str = Field(min_length=1)
    point: Coord


class RouteRequest(BaseModel):
    waypoints: list[Coord] = Field(min_length=2)
    costing: str = DEFAULT_COSTING


class RouteResponse(BaseModel):
    coords: list[list[float]]
    length_m: float
    is_closed_loop: bool


class StartRequest(BaseModel):
    """Either `preset` or `waypoints` — the API rejects both and neither."""

    preset: str | None = None
    waypoints: list[Coord] | None = None
    pace: str | None = None
    speed: float | None = None
    # Independent of `pace`. None means "use the preset's saved costing", or
    # DEFAULT_COSTING for an ad-hoc route -- never anything derived from the pace.
    costing: str | None = None
    # None means "inherit the preset's setting"; the ad-hoc branch coerces it.
    loop: bool | None = None
    # A run needs at least one tick to produce anything; a zero/negative value
    # would yield an instant "finished" run with nothing behind it.
    duration_s: float | None = Field(default=None, gt=0)
    # Anything much larger puts emitted positions kilometres off the route.
    scatter_m: float = Field(default=3.0, ge=0, le=100)


class PinRequest(BaseModel):
    """A single point to hold the device at — the GUI's `ios-loc set`."""

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class DeviceStatus(BaseModel):
    connected: bool
    reason: str  # "ok" | "no_device" | "tunneld_down" | "error"
    detail: str


class WalkStatus(BaseModel):
    state: WalkState
    error: str | None = None
    fix: FixOut | None = None
    stats: StatsOut | None = None
    route: list[list[float]] = Field(default_factory=list)
    trail: list[FixOut] = Field(default_factory=list)
    preset_name: str | None = None
    pace: str | None = None
    loop: bool = False
    length_m: float | None = None
