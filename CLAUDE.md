# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`ios-loc` — a CLI that simulates GPS location on iOS 17+ devices via `pymobiledevice3`,
used to walk/cycle routes for Pikmin Bloom. Python 3.13, `uv`-managed, package at
`src/ios_loc/`.

## Commands

```bash
uv sync                              # install
uv run pytest -q                     # full suite (193 tests, ~2s, no device/network needed)
uv run pytest tests/test_walker.py::test_name -q   # single test
uv run ios-loc --help
uv run python scripts/export_openapi.py            # regenerate src/ios_loc/web/ui/api-schema.json
cd src/ios_loc/web/ui && pnpm test run   # frontend pure-logic tests
cd src/ios_loc/web/ui && pnpm build      # rebuild the committed bundle in web/static/
```

There is no linter or formatter configured. Every test runs under a 60s `pytest-timeout`
cap, so a regression in the broadcast path fails loudly instead of hanging the suite.

Running against hardware needs tunneld up first (once per boot, needs sudo):

```bash
sudo pymobiledevice3 remote tunneld -d
uv run ios-loc doctor                # verifies tunneld → device → DVT channel
```

## Architecture

A strict layering by what can fail. Keep it that way — it is why a three-hour
run can be tested in milliseconds.

| Module | Role | May not import |
| --- | --- | --- |
| `path.py` | Pure polyline geometry, cumulative-distance interpolation | pymobiledevice3, requests, asyncio |
| `walker.py` | Movement model: `advance(dt)` → `Fix`. Pure, synchronous, never sleeps, no I/O | anything doing I/O |
| `presets.py` | `Profile` / `Preset` dataclasses, TOML config layered over built-in defaults | — |
| `routing.py` | Valhalla HTTP client + polyline decode + disk cache | — |
| `session.py` | **The only module that can fail because of hardware.** All reconnect/backoff logic | — |
| `discovery.py` | tunneld lookup → `LocationSimulation` async context manager | — |
| `runner.py` | The async tick loop joining Walker → LocationSession | — |
| `cli.py` | Typer wiring only; no behaviour | — |
| `web/` | Local GUI: `WalkService` (run lifecycle + broadcast), FastAPI wiring, built UI assets in `web/static/`, React source in `web/ui/` | — (imports everything; nothing imports it) |

`runner.run_walk`, `session.LocationSession` and `walker.Walker` all take injectable
`clock` / `sleep` / `rng` / `poster` / `opener`, so tests drive virtual time and fake
devices. Preserve those seams when editing.

`src/ios_loc/web/ui/api-schema.json` is the OpenAPI schema exported from the FastAPI
app; a drift test fails if it goes stale. The frontend generates its
TypeScript types from this file rather than hand-copying the API shape.

## Invariants that are load-bearing

These were each fixed deliberately; re-breaking them is silent, not loud.

- **20 km/h ceiling (`MAX_SPEED_MPS = 5.56`).** Pikmin Bloom stops crediting distance
  above it, so an over-speed run produces nothing. Enforced in `Profile.__post_init__`
  and again per-tick in `Walker._tick_speed` against the *jittered* speed, not the base.
- **An outage costs distance; it never causes a jump.** If `session.set()` blocks on a
  reconnect, `run_walk` resets its deadline to now instead of firing a catch-up burst
  of ticks (`runner.py`). `walker.advance()` is called exactly once per tick.
- **`Walker.distance_m` is cumulative and never wrapped**, even across laps — that is
  the number reported to the user. Only `_position_distance()` folds it onto the path.
- **Looping an *open* path bounces back and forth**, it does not teleport to the start;
  a closed path (`Path.is_closed_loop`, 25 m tolerance) wraps by modulo.
- **Scatter perturbs only the emitted position**, never `distance_m`.
- **Valhalla polylines are precision 6**, not the common 5. Wrong precision silently
  yields coordinates off by 10×. Malformed polylines raise rather than return
  plausible-looking garbage.
- **`session.set()` re-raises programming errors** (`TypeError`, `AttributeError`,
  `NameError`, `ImportError`) instead of retrying — a bug never succeeds on retry and
  would otherwise consume an overnight run. Backoff lives on the instance, not the call,
  so a tunnel flapping once per tick still escalates.
- **`discovery.find_device()` closes the tunnels it does not use** —
  `get_tunneld_devices()` connects every tunnel it finds, so skipping the close leaks
  a live connection per call.
- **GUI broadcast queues are bounded and drop oldest.** A stalled browser tab must
  never apply backpressure to the tick loop — that would convert a UI problem into
  lost walking distance. `WalkService._broadcast` never awaits.
- **`run_walk` swallows `SessionLost`,** so `_WatchedSession` records it and the GUI
  reports a lost device as an error rather than a clean finish.
- **`WalkService.start()` / `stop()` are serialized under an `asyncio.Lock`.**
  Concurrent HTTP callers could otherwise open two device sessions and orphan a
  drive task with nothing left tracking it.
- **The API re-raises programming errors** (`TypeError`, `AttributeError`,
  `NameError`, `ImportError`) rather than mapping them to a retryable 503 — same
  reasoning as `session.set()`: a bug should fail loudly, not look like a transient
  hardware hiccup a client should retry.
- **A 1 Hz fix must not re-render the map or the sidebar.** The frontend store
  (`web/ui/src/state/walkStore.ts`) has three channels: telemetry (every
  message, status bar only), meta (only when state/route/preset actually
  change), and fix (imperative, the map's dot-mover). Reading telemetry from a
  component above the status bar re-renders the MapLibre subtree once a second.
- **`[lat, lon]` on the wire, `[lng, lat]` in MapLibre.**
  `src/ios_loc/web/ui/src/lib/coords.ts` exports `toLngLat` / `fromLngLat`, and
  those two functions are the only places in the app that flip a pair. A third
  flip anywhere else produces plausible-looking coordinates in the wrong
  hemisphere, with no error.
- **`web/static/` is committed build output.** A change under `web/ui/` that is
  not followed by `pnpm build` ships nothing.

## Config

`~/.config/ios-loc/config.toml` (override with `--config`). `[profiles.<name>]` layers
over built-in `walk` / `bike`; a brand-new profile name inherits `walk`'s defaults for
omitted fields. `[presets.<name>]` needs `waypoints`. See README.md for examples.

Routes are cached to `~/.cache/ios-loc/routes` (atomic writes, corrupt entries
discarded). `--offline` fails fast rather than hitting the network — that is the mode
for unattended overnight runs.

## Hardware verification

`docs/manual-verification.md` records what has and has *not* been confirmed on a real
device. Keep it honest and up to date when device-facing behaviour changes; notably a
real mid-run cable pull and a multi-hour run are still unverified.
