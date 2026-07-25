# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`ios-loc` — a CLI plus local web GUI that simulates GPS location on iOS 17+ devices
via `pymobiledevice3`: hold a fixed point, or walk/cycle a routed path at a realistic
pace for hours. Python 3.13, `uv`-managed, package at `src/ios_loc/`. The repo is
public — keep the name of any specific game out of code, docs, and commits.

Only source is committed: the GUI bundle under `src/ios_loc/web/static/` is gitignored
build output, so `make install` installs the CLI and the GUI needs `make build`
(Node 20+) once.

## Commands

The `Makefile` at the repo root is the entry point — it owns the `cd` into the
five-deep frontend directory, so this list stays short and cannot drift from it.
`make help` lists every target.

```bash
make install      # uv sync (CLI only; the GUI also needs `make build`)
make check        # THE FULL GATE: ruff + pytest + vitest + oxlint + pnpm build
make test         # both suites          make test-py / make test-ui for one
make lint         # both linters         make fmt to apply ruff's fixes
make build        # (re)build the bundle in web/static/ — required by `gui`
make gui          # build, then serve    make dev for vite + API together
make schema       # regenerate src/ios_loc/web/ui/api-schema.json
uv run pytest tests/test_walker.py::test_name -q   # single test
```

Python is linted and formatted by `ruff` (config in `pyproject.toml`), at
`line-length = 100` rather than the default 88 — this codebase predates the
formatter and its own p99 line is 91. `BLE001` is deliberately on, since the code
already annotates every intentional broad `except` with a reason; `session.py` and
`cli.py` are exempt because absorbing anything is their contract. Three rules are
off with reasons stated inline in `pyproject.toml` — don't re-enable `B905` or
`UP042` without reading them, as both change runtime behaviour.

Every test runs under a 60s `pytest-timeout` cap, so a regression in the broadcast
path fails loudly instead of hanging the suite. On the frontend, `pnpm build` runs
`tsc -b` first, so it is also the typecheck; oxlint carries two expected
`only-export-components` warnings in vendored shadcn files.

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
| `presets.py` | `Pace` / `Preset` / `Place` dataclasses, TOML config layered over built-in defaults | — |
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

- **20 km/h ceiling (`MAX_SPEED_MPS = 5.56`).** Location-based games stop crediting
  distance above it, so an over-speed run produces nothing. Enforced in `Pace.__post_init__`
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
- **A 1 Hz fix must not re-render the map.** The frontend store
  (`web/ui/src/state/walkStore.ts`) has three channels: telemetry (every
  message), meta (only when state/route/preset actually change), and fix
  (imperative, the map's dot-mover). `WalkPanel.tsx` is the ONLY component
  that calls `useWalkTelemetry` — a second caller higher up (`App`, `Sidebar`)
  re-renders that whole subtree, map included, once a second.
- **`[lat, lon]` on the wire, `[lng, lat]` in MapLibre.**
  `src/ios_loc/web/ui/src/lib/coords.ts` exports `toLngLat` / `fromLngLat`, and
  those two functions are the only places in the app that flip a pair. A third
  flip anywhere else produces plausible-looking coordinates in the wrong
  hemisphere, with no error.
- **`web/static/` is generated, gitignored, and required by `gui`.** A change
  under `web/ui/` that is not followed by a build is invisible to `ios-loc gui`,
  which reads the built bundle, never the source. Nothing verifies that a
  *present* bundle matches current source, so three things guard it:
  `make gui` rebuilds before serving (the cheapest guard — use it),
  `cli._require_ui_assets()` refuses to serve when `static/index.html` is
  absent (a missing bundle would otherwise mount nothing and serve a bare 404),
  and `hatch_build.py` runs `pnpm build` for the wheel target so a released
  wheel always carries a bundle matching its source. That hook keys off
  `version == "editable"`, NOT `self.target_name` — hatchling builds an
  editable install as the *wheel* target, so a `target_name` check would never
  match and every `uv sync` would demand pnpm. The wheel ships `web/static/` but
  excludes `web/ui/` (`[tool.hatch.build.targets.wheel] exclude`) — the built
  bundle is what an installed copy needs; its TSX source is not.

- **Python tests must pass on a checkout with no bundle.** The frontend is not
  committed, so any test that touches `web/static/` either skips when it is
  absent (`test_a_present_bundle_is_a_real_build`) or fakes it
  (`built_assets` in `tests/test_cli_gui.py`). A test asserting the real bundle
  exists turns "I have not run pnpm build" into a red suite for everyone.
- **The sidebar must never cover or swallow the map on desktop.**
  `Sidebar.tsx` renders as an inline flex column (`w-[360px]`, no scrim) when
  `overlay` is false, and takes the fixed-drawer + `bg-black/30` scrim branch
  only on mobile (`useIsMobile`). Drawing a route with the sidebar open is the
  primary flow, so any modal wrapper — Sheet, Dialog, AlertDialog —
  reintroduces a backdrop that eats every map click. That failure passes every
  test in the suite. Row deletion therefore confirms inline (local row state in
  `LibraryRow.tsx`), not via an AlertDialog.
- **The active sidebar tab decides what a map tap does.** `location` → set the
  device at the tapped point; `walk` → append a waypoint. One tap handler
  branching on tab; a second map-click path is how the two modes start fighting
  over the same gesture.
- **A pace is speed; a costing is the route. They never feed each other.**
  `Pace` carries no costing at all, and `resolve_walk` resolves the two
  independently: an explicit `costing` wins, else the preset's saved `costing`,
  else `DEFAULT_COSTING`. Let a pace supply a costing again and selecting
  `bike` for its speed silently re-plans a footpath onto cycleways — a wrong
  route, with no error anywhere. `tests/test_resolve_walk.py` pins
  this; `test_a_pace_carries_no_costing` fails the moment the field comes back.
- **A preset owns its costing, because the costing describes its geometry.**
  Re-planning a saved route under a different costing yields a different
  polyline than the one that was drawn and saved, so `Preset.costing` round
  trips through the config file and `loadPreset` seeds the GUI's Routing mode
  select from it.
- **One `StartRequest` builder.** `web/ui/src/lib/startBody.ts` is the only
  place a start body is constructed. Two inline copies (the quick bar and the
  start form) is how the two paths silently drifted apart — a named route sends
  `preset` with `waypoints` null, an edited one sends the reverse, and BOTH
  always send `costing` (Routing mode is the only thing that decides it).
  `DraftRoute.name` is cleared by every edit for the same reason: starting by
  name after an edit runs the OLD route on the phone.
- **Frontend tests are pure-logic only** (`vitest.config.ts` pins `environment:
  "node"`, `include: ["src/**/*.test.ts"]`). No jsdom, no component rendering —
  so the suite cannot catch a re-modalled sidebar, a re-rendering map, or any
  layout regression. Those are only ever caught in a real browser. Treat a green
  `pnpm test run` as proof about reducers, the store, and the API client, not
  about anything the DOM does.
- **A set-location pin is a walk-parity device state.** `WalkService.pin()`
  holds one open session under the same lock as `start()`/`stop()`, so the
  device never gets two owners. Pinning while a walk runs is refused (409);
  starting a walk while pinned silently replaces the pin (a pin holds no
  accumulated state). `stop()` clears a pin exactly as it ends a walk — one
  Stop button for both. The pin reaches the browser as a `"fix"` broadcast so
  the map's live dot moves; it produces no per-second traffic.
- **Each config writer regenerates only its own table kind.** `_write_tables(path,
  "presets" | "places", …)` strips and re-renders one kind and preserves the rest
  byte for byte — a place save must never disturb `[presets.*]`, and neither may
  touch a hand-written `[paces.*]` or its comments. `load_config` reads only
  `paces` and `presets` and ignores unknown top-level tables, which is what
  lets `[places.*]` coexist without a loader change.

## Config

`~/.config/ios-loc/config.toml` (override with `--config`). `[paces.<name>]` layers
over built-in `walk` / `bike`; a brand-new pace name inherits `walk`'s defaults for
omitted fields. A pace has no `costing` — that lives on the route. `[presets.<name>]`
needs `waypoints`, and may set `pace`, `costing` and `loop`. See README.md for examples.

Routes are cached to `~/.cache/ios-loc/routes` (atomic writes, corrupt entries
discarded). `--offline` fails fast rather than hitting the network — that is the mode
for unattended overnight runs.

## Hardware verification

Everything except the device layer is covered by the test suite, which needs no device
and no network. What a real iPhone has actually confirmed: `doctor`, `walk`, `set`,
`clear`, and one short supervised GUI run. What it has not: reconnect after a genuine
cable pull, a multi-hour unattended run, and `SessionLost` surfacing in the browser
mid-walk. The README's Notes section states this to users — keep that honest when
device-facing behaviour changes, and never let a green suite stand in for hardware
proof on those paths.
