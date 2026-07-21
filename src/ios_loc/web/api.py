"""FastAPI wiring. No behaviour — everything real lives in service.py."""

from __future__ import annotations

import asyncio
import logging
import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from ios_loc.presets import ConfigError, Preset, load_config, resolve_walk, save_preset
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

logger = logging.getLogger(__name__)


def create_app(
    *,
    service: WalkService,
    route_client,
    config_path: pathlib.Path | None = None,
    offline: bool = False,
    static_dir: pathlib.Path | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            yield
        finally:
            # Whatever ends the process -- Ctrl-C, a signal, the test client's
            # `with` block exiting -- must clear the device. `service.stop()`
            # is a no-op if nothing is running, so this is safe on every exit.
            try:
                await service.stop()
            except Exception:  # noqa: BLE001 — shutdown must not raise; log and move on
                logger.exception("failed to stop the walk and clear the device on shutdown")

    app = FastAPI(title="ios-loc", version="1", lifespan=lifespan)

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
        profiles, presets = _config()
        try:
            resolved = resolve_walk(
                preset=body.preset,
                waypoints=body.waypoints,
                profile=body.profile,
                speed=body.speed,
                costing=body.costing,
                loop=body.loop,
                profiles=profiles,
                presets=presets,
            )
        except ConfigError as exc:
            # An unknown preset name is a 404 (the named thing does not exist);
            # everything else resolve_walk rejects -- an unknown profile, a bad
            # request shape, an out-of-range coordinate, an over-ceiling speed
            # -- is the client's fault, a 400.
            detail = str(exc)
            status_code = 404 if detail.startswith("unknown preset") else 400
            raise HTTPException(status_code=status_code, detail=detail) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        spec = StartSpec(
            waypoints=resolved.waypoints,
            costing=resolved.costing,
            profile=resolved.profile,
            loop=resolved.loop,
            duration_s=body.duration_s,
            scatter_m=body.scatter_m,
            preset_name=resolved.preset_name,
        )
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

    @app.websocket("/ws")
    async def stream(socket: WebSocket) -> None:
        await socket.accept()
        with service.subscribe() as queue:
            # The snapshot is the only message carrying route and trail, so a tab
            # connecting mid-run gets the whole picture exactly once.
            await socket.send_json({"type": "snapshot", "status": service.status().model_dump()})
            try:
                while True:
                    message = await queue.get()
                    await socket.send_json(message)
            except WebSocketDisconnect:
                return

    if static_dir is not None and static_dir.exists():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="ui")

    return app
