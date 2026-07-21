"""FastAPI wiring. No behaviour — everything real lives in service.py."""

from __future__ import annotations

import asyncio
import dataclasses
import pathlib

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from ios_loc.presets import ConfigError, Preset, load_config, save_preset
from ios_loc.routing import RoutingError
from ios_loc.session import _PROGRAMMING_ERRORS
from ios_loc.web.models import (
    PresetIn,
    PresetOut,
    PresetsListOut,
    RouteRequest,
    RouteResponse,
    StartRequest,
    WalkStatus,
)
from ios_loc.web.service import StartSpec, WalkAlreadyRunning, WalkService


def create_app(
    *,
    service: WalkService,
    route_client,
    config_path: pathlib.Path | None = None,
    offline: bool = False,
    static_dir: pathlib.Path | None = None,
) -> FastAPI:
    app = FastAPI(title="ios-loc", version="1")

    def _config():
        try:
            return load_config(config_path)
        except ConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/presets", response_model=PresetsListOut)
    def list_presets() -> PresetsListOut:
        profiles, presets = _config()
        return PresetsListOut(
            presets=[PresetOut.from_preset(p) for p in sorted(presets.values(), key=lambda p: p.name)],
            profiles=sorted(profiles),
            offline=offline,
        )

    @app.post("/api/presets", response_model=PresetOut)
    def create_preset(body: PresetIn) -> PresetOut:
        preset = Preset(
            name=body.name,
            waypoints=[(lat, lon) for lat, lon in body.waypoints],
            profile=body.profile,
            loop=body.loop,
        )
        try:
            save_preset(config_path, preset)
        except ConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"could not write config: {exc}") from exc
        return PresetOut.from_preset(preset)

    @app.post("/api/route", response_model=RouteResponse)
    async def build_route(body: RouteRequest) -> RouteResponse:
        waypoints = [(lat, lon) for lat, lon in body.waypoints]
        try:
            path = await asyncio.to_thread(route_client.route, waypoints, body.costing)
        except (RoutingError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return RouteResponse(
            coords=[[lat, lon] for lat, lon in path.coords],
            length_m=path.length_m,
            is_closed_loop=path.is_closed_loop,
        )

    @app.get("/api/walk", response_model=WalkStatus)
    def walk_status() -> WalkStatus:
        return service.status()

    @app.post("/api/walk", response_model=WalkStatus)
    async def start_walk(body: StartRequest) -> WalkStatus:
        spec = _build_spec(body, config_path)
        try:
            return await service.start(spec)
        except WalkAlreadyRunning as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (RoutingError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except _PROGRAMMING_ERRORS:
            # A bug, not a device dropout: let it propagate to a 500 instead of
            # telling the client (wrongly) that retrying is reasonable.
            raise
        except Exception as exc:  # device or tunnel failure at start
            raise HTTPException(status_code=503, detail=f"{type(exc).__name__}: {exc}") from exc

    @app.delete("/api/walk", response_model=WalkStatus)
    async def stop_walk() -> WalkStatus:
        await service.stop()
        return service.status()

    if static_dir is not None and static_dir.exists():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="ui")

    return app


def _build_spec(body: StartRequest, config_path: pathlib.Path | None) -> StartSpec:
    """Turn a request into a validated StartSpec, or raise HTTPException(400)."""
    if body.preset and body.waypoints:
        raise HTTPException(status_code=400, detail="pass either preset or waypoints, not both")
    if not body.preset and not body.waypoints:
        raise HTTPException(status_code=400, detail="a walk needs a preset or at least 2 waypoints")

    try:
        profiles, presets = load_config(config_path)
    except ConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    preset_name = None
    if body.preset:
        if body.preset not in presets:
            raise HTTPException(status_code=404, detail=f"unknown preset {body.preset!r}")
        chosen = presets[body.preset]
        waypoints = list(chosen.waypoints)
        profile_name = body.profile or chosen.profile
        loop = chosen.loop if body.loop is None else body.loop
        preset_name = chosen.name
    else:
        if len(body.waypoints) < 2:
            raise HTTPException(status_code=400, detail="a route needs at least 2 waypoints")
        waypoints = [(lat, lon) for lat, lon in body.waypoints]
        profile_name = body.profile or "walk"
        loop = bool(body.loop)

    if profile_name not in profiles:
        raise HTTPException(status_code=400, detail=f"unknown profile {profile_name!r}")
    profile = profiles[profile_name]

    if body.speed is not None:
        try:
            profile = dataclasses.replace(profile, speed=body.speed)
        except ValueError as exc:
            # Includes the 20 km/h ceiling — never bypass this validation.
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return StartSpec(
        waypoints=waypoints,
        costing=body.costing or profile.costing,
        profile=profile,
        loop=loop,
        duration_s=body.duration_s,
        scatter_m=body.scatter_m,
        preset_name=preset_name,
    )
