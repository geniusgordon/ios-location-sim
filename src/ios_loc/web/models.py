"""Wire types for the GUI. Converters only — no behaviour lives here."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from ios_loc.presets import Preset
from ios_loc.runner import WalkStats
from ios_loc.walker import Fix


class WalkState(str, Enum):
    IDLE = "idle"
    STARTING = "starting"
    WALKING = "walking"
    RECONNECTING = "reconnecting"
    FINISHED = "finished"
    ERROR = "error"


class FixOut(BaseModel):
    elapsed_s: float
    lat: float
    lon: float
    distance_m: float
    speed_mps: float
    paused: bool

    @classmethod
    def from_fix(cls, fix: Fix) -> "FixOut":
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
    def from_stats(cls, stats: WalkStats) -> "StatsOut":
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
    profile: str
    loop: bool

    @classmethod
    def from_preset(cls, preset: Preset) -> "PresetOut":
        return cls(
            name=preset.name,
            waypoints=[[lat, lon] for lat, lon in preset.waypoints],
            profile=preset.profile,
            loop=preset.loop,
        )


class PresetIn(BaseModel):
    name: str = Field(min_length=1)
    waypoints: list[list[float]] = Field(min_length=2)
    profile: str = "walk"
    loop: bool = False


class RouteRequest(BaseModel):
    waypoints: list[list[float]] = Field(min_length=2)
    costing: str = "pedestrian"


class RouteResponse(BaseModel):
    coords: list[list[float]]
    length_m: float
    is_closed_loop: bool


class StartRequest(BaseModel):
    """Either `preset` or `waypoints` — the API rejects both and neither."""

    preset: str | None = None
    waypoints: list[list[float]] | None = None
    profile: str | None = None
    speed: float | None = None
    costing: str | None = None
    # None means "inherit the preset's setting"; the ad-hoc branch coerces it.
    loop: bool | None = None
    duration_s: float | None = None
    scatter_m: float = 3.0


class WalkStatus(BaseModel):
    state: WalkState
    error: str | None = None
    fix: FixOut | None = None
    stats: StatsOut | None = None
    route: list[list[float]] = Field(default_factory=list)
    trail: list[FixOut] = Field(default_factory=list)
    preset_name: str | None = None
    profile: str | None = None
    loop: bool = False
    length_m: float | None = None
