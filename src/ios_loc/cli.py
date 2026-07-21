"""Command-line interface. Wiring only — behaviour lives in the other modules."""

from __future__ import annotations

import asyncio
import logging
import pathlib
import random
import re
import sys
import webbrowser

import typer
import uvicorn

from ios_loc.discovery import DiscoveryError, find_device, open_simulation
from ios_loc.path import Coord
from ios_loc.presets import ConfigError, load_config, resolve_walk
from ios_loc.routing import RoutingError, ValhallaClient
from ios_loc.runner import run_walk
from ios_loc.session import LocationSession, SessionLost
from ios_loc.walker import Walker

app = typer.Typer(no_args_is_help=True, help="Simulate GPS location on iOS 17+ devices.")
presets_app = typer.Typer(no_args_is_help=True, help="Inspect configured presets.")
app.add_typer(presets_app, name="presets")

logger = logging.getLogger("ios_loc.progress")

_DURATION_RE = re.compile(r"^(\d+(?:\.\d+)?)([smh]?)$")
_UNITS = {"s": 1.0, "m": 60.0, "h": 3600.0, "": 1.0}


def parse_waypoint(text: str) -> Coord:
    """Parse a 'lat,lon' string into a coordinate."""
    parts = text.split(",")
    if len(parts) != 2:
        raise ValueError(f"waypoint must be 'lat,lon', got {text!r}")
    try:
        lat, lon = float(parts[0].strip()), float(parts[1].strip())
    except ValueError as exc:
        raise ValueError(f"waypoint must be 'lat,lon', got {text!r}") from exc
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError(f"waypoint out of range: {text!r}")
    return lat, lon


def parse_duration(text: str) -> float:
    """Parse '30s', '15m', '3h' or a bare number of seconds."""
    match = _DURATION_RE.match(text.strip())
    if not match:
        raise ValueError(f"duration must look like 30s, 15m or 3h, got {text!r}")
    return float(match.group(1)) * _UNITS[match.group(2)]


def _fail(message: str) -> None:
    typer.echo(message)
    raise typer.Exit(code=1)


@app.command()
def doctor(udid: str = typer.Option(None, help="Target a specific device UDID.")) -> None:
    """Check that tunneld, the device, and the DVT channel are all reachable."""

    async def _run() -> None:
        try:
            rsd = await find_device(udid)
            typer.echo(f"tunneld:  OK\ndevice:   OK (iOS {rsd.product_version})")
            await rsd.close()
        except DiscoveryError as exc:
            _fail(f"FAILED: {exc}")

        try:
            async with open_simulation(udid):
                typer.echo("DVT:      OK — ready to simulate")
        except Exception as exc:
            _fail(
                f"DVT channel failed to open: {exc}\n"
                "Check Developer Mode is enabled and the device is unlocked."
            )

    asyncio.run(_run())


@app.command("set")
def set_location(
    latitude: float,
    longitude: float,
    udid: str = typer.Option(None, help="Target a specific device UDID."),
) -> None:
    """Hold a fixed location until interrupted with Ctrl-C."""

    async def _run() -> None:
        async with open_simulation(udid) as sim:
            await sim.set(latitude, longitude)
            typer.echo(f"location set to {latitude}, {longitude} — Ctrl-C to clear")
            try:
                while True:
                    await asyncio.sleep(3600)
            except (KeyboardInterrupt, asyncio.CancelledError):
                await sim.clear()
                typer.echo("cleared")

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
    except typer.Exit:
        raise
    except DiscoveryError as exc:
        _fail(f"FAILED: {exc}")
    except Exception as exc:
        _fail(f"FAILED: {exc}")


@app.command()
def clear(udid: str = typer.Option(None, help="Target a specific device UDID.")) -> None:
    """Stop simulating and restore the device's real GPS."""

    async def _run() -> None:
        async with open_simulation(udid) as sim:
            await sim.clear()
            typer.echo("cleared")

    try:
        asyncio.run(_run())
    except typer.Exit:
        raise
    except DiscoveryError as exc:
        _fail(f"FAILED: {exc}")
    except Exception as exc:
        _fail(f"FAILED: {exc}")


@presets_app.command("list")
def presets_list(
    config: pathlib.Path = typer.Option(None, help="Path to config.toml."),
) -> None:
    """List configured speed profiles and named routes."""
    try:
        profiles, presets = load_config(config)
    except ConfigError as exc:
        _fail(f"config error: {exc}")
    typer.echo("profiles:")
    for name, profile in sorted(profiles.items()):
        typer.echo(
            f"  {name:<10} {profile.speed:>5.2f} m/s "
            f"({profile.speed * 3.6:>4.1f} km/h)  costing={profile.costing}"
        )
    typer.echo("presets:")
    if not presets:
        typer.echo("  (none)")
    for name, preset in sorted(presets.items()):
        loop = " loop" if preset.loop else ""
        typer.echo(f"  {name:<10} {len(preset.waypoints)} waypoints  profile={preset.profile}{loop}")


@app.command()
def walk(
    preset: str = typer.Argument(None, help="Name of a preset from config.toml."),
    via: list[str] = typer.Option(None, "--via", help="Waypoint as 'lat,lon'. Repeatable."),
    profile: str = typer.Option(None, help="Speed profile name, e.g. walk or bike."),
    speed: float = typer.Option(None, help="Override the profile's base speed, m/s."),
    costing: str = typer.Option(None, help="Override the Valhalla costing model."),
    loop: bool = typer.Option(
        None, "--loop/--no-loop", help="Repeat the route (overrides a preset's setting)."
    ),
    duration: str = typer.Option(None, help="Stop after this long, e.g. 3h."),
    scatter: float = typer.Option(3.0, help="GPS scatter in metres."),
    offline: bool = typer.Option(False, "--offline", help="Fail if the route is not cached."),
    udid: str = typer.Option(None, help="Target a specific device UDID."),
    config: pathlib.Path = typer.Option(None, help="Path to config.toml."),
    log: pathlib.Path = typer.Option(None, help="Also write progress to this file."),
    no_clear: bool = typer.Option(
        False, "--no-clear", help="Leave the simulated location in place on exit."
    ),
) -> None:
    """Walk or cycle a route, holding the simulated location for the whole run."""
    try:
        profiles, presets = load_config(config)
    except ConfigError as exc:
        _fail(f"config error: {exc}")

    try:
        parsed_via = [parse_waypoint(v) for v in via] if via else None
    except ValueError as exc:
        _fail(str(exc))

    try:
        resolved = resolve_walk(
            preset=preset,
            waypoints=parsed_via,
            profile=profile,
            speed=speed,
            costing=costing,
            loop=loop,
            profiles=profiles,
            presets=presets,
        )
    except ConfigError as exc:
        _fail(f"{exc}; try: ios-loc presets list")
    except ValueError as exc:
        _fail(str(exc))

    waypoints = resolved.waypoints
    selected = resolved.profile
    loop = resolved.loop

    duration_s = None
    if duration:
        try:
            duration_s = parse_duration(duration)
        except ValueError as exc:
            _fail(str(exc))

    handlers = [logging.StreamHandler(sys.stderr)]
    if log:
        try:
            log.parent.mkdir(parents=True, exist_ok=True)
            handlers.append(logging.FileHandler(log))
        except OSError as exc:
            _fail(f"could not open log file {log}: {exc}")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", handlers=handlers)

    try:
        client = ValhallaClient(offline=offline)
        path = client.route(waypoints, costing=resolved.costing)
    except (RoutingError, ValueError) as exc:
        _fail(f"routing failed: {exc}")

    if loop and not path.is_closed_loop:
        typer.echo(
            "note: this route does not return to its start, so --loop will "
            "retrace it in both directions rather than jumping back"
        )

    walker = Walker(path, selected, loop=loop, rng=random.Random(), scatter_m=scatter)
    typer.echo(
        f"route: {path.length_m / 1000:.2f} km, profile={selected.name} "
        f"({selected.speed * 3.6:.1f} km/h), loop={loop}"
    )

    async def _run() -> None:
        session = LocationSession(lambda: open_simulation(udid))

        def report(fix) -> None:
            if int(fix.elapsed_s) % 30 == 0:
                logger.info(
                    "  %6.1f min  %6.2f km  laps=%s  %4.1f km/h%s  reconnects=%s",
                    fix.elapsed_s / 60,
                    walker.distance_m / 1000,
                    walker.laps,
                    fix.speed_mps * 3.6,
                    "  (paused)" if fix.paused else "",
                    session.reconnects,
                )

        await session.start()
        try:
            stats = await run_walk(walker, session, duration_s=duration_s, on_fix=report)
        finally:
            await session.stop(clear=not no_clear)
        typer.echo(
            f"done: {stats.distance_m / 1000:.2f} km in {stats.elapsed_s / 60:.1f} min, "
            f"{stats.laps} laps, {stats.reconnects} reconnects"
        )

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        typer.echo("\ninterrupted")
    except typer.Exit:
        raise
    except DiscoveryError as exc:
        _fail(f"FAILED: {exc}")
    except SessionLost as exc:
        _fail(f"FAILED: {exc}")
    except Exception as exc:
        _fail(
            f"FAILED: {exc}\n"
            "Check the device is unlocked, trusted, and has Developer Mode enabled."
        )


DEFAULT_STATIC_DIR = pathlib.Path(__file__).parent / "web" / "static"


def build_gui_app(
    *,
    config: pathlib.Path | None,
    offline: bool,
    udid: str | None,
    static_dir: pathlib.Path | None = DEFAULT_STATIC_DIR,
):
    """Assemble the GUI app. Separated from `gui` so tests need no server."""
    from ios_loc.web.api import create_app
    from ios_loc.web.service import WalkService

    route_client = ValhallaClient(offline=offline)
    service = WalkService(
        route_client=route_client,
        session_factory=lambda: LocationSession(lambda: open_simulation(udid)),
    )
    return create_app(
        service=service,
        route_client=route_client,
        config_path=config,
        offline=offline,
        static_dir=static_dir,
    )


@app.command()
def gui(
    host: str = typer.Option("127.0.0.1", help="Bind address. Leave as loopback unless you mean it."),
    port: int = typer.Option(8765, help="Port to serve on."),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Open a browser on start."),
    offline: bool = typer.Option(False, "--offline", help="Fail routing that is not cached."),
    udid: str = typer.Option(None, help="Target a specific device UDID."),
    config: pathlib.Path = typer.Option(None, help="Path to config.toml."),
) -> None:
    """Serve the map GUI on localhost."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    application = build_gui_app(config=config, offline=offline, udid=udid)
    url = f"http://{host}:{port}"
    typer.echo(f"serving {url}")
    if open_browser:
        webbrowser.open(url)
    uvicorn.run(application, host=host, port=port, log_level="info")
