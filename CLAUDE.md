# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

**README.md is the source of truth for everything a user does** — install, CLI and
GUI usage, every `make` target, the config file format, and what is unverified on
hardware. Read it first, and when it already says something, link to it instead of
restating it here. This file is only what the README has no reason to explain: the
layering, the invariants, and where the traps are.

## What this is

`ios-loc` — a CLI plus local web GUI that simulates GPS location on iOS 17+ devices
via `pymobiledevice3`: hold a fixed point, or walk/cycle a routed path at a realistic
pace for hours. Python 3.13, `uv`-managed, package at `src/ios_loc/`, React frontend
at `src/ios_loc/web/ui/`.

**The repo is public — keep the name of any specific game out of code, docs, and
commits.**

## Working here

- **`make check` is the full gate** — ruff, pytest, vitest, oxlint, and a real
  frontend build. Run it before reporting anything as done. `make help` lists every
  target; README's Development section says what each is for. A single test is
  `uv run pytest tests/test_walker.py::test_name -q`.
- **Only source is committed.** `web/static/` is generated, so a change under
  `web/ui/` stays invisible to `ios-loc gui` until it is rebuilt — `make gui` does
  that for you. See the `web/static/` invariant below.
- **ruff's config explains itself in `pyproject.toml` comments** — why the line
  length is 100, why `BLE001` is on with two exemptions, and why three rules are
  off. Read those comments before touching that block: re-enabling `B905` or
  `UP042` changes runtime behaviour.
- **A hanging suite is a bug, not a slow test.** Every test runs under a 60s
  `pytest-timeout` cap so a regression in the broadcast path fails loudly. On the
  frontend, oxlint carries two expected `only-export-components` warnings in
  vendored shadcn files; anything else is real.
- **Hardware** needs `sudo pymobiledevice3 remote tunneld -d` once per boot, then
  `uv run ios-loc doctor` to verify tunneld → device → DVT channel.

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
- **A terminal state needs an exit, not a disabled Stop.** `finished`/`error`
  keep `LiveWalkPanel` on screen (`showSummary` in `App.tsx`) but the session is
  already torn down, so `canStop()` is false. The panel therefore swaps its
  footer — **Stop** while `canStop`, **Done** / **Walk again** once the run is
  over — rather than disabling the one button it has. Done calls `DELETE
  /api/walk` as well as clearing `showSummary`: `_drive` leaves `self._run` set,
  so the service reports `finished` with that run's route and trail until
  something clears it and a reload would resurrect an old summary
  (`test_stop_after_natural_finish_clears_the_finished_run`).
- **The terminal `state` broadcast carries `stats`; the reducer must keep them.**
  `service.py`'s final broadcast attaches the authoritative counts, which can be
  one tick ahead of the last `fix` message (a tick is counted before `set()` is
  awaited; `on_fix` only runs after a *successful* one). `applyMessage`'s `state`
  case reads `msg.stats ?? model.stats`, so a terminal message adopts them and
  every other state message leaves the on-screen numbers alone.
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
- **`web/static/` is generated, gitignored, and required by `gui`.** `ios-loc gui`
  reads the built bundle, never the source, and nothing verifies that a *present*
  bundle is current — so an un-rebuilt `web/ui/` change is silently invisible.
  `make gui` rebuilds before serving; use it. Two other guards:
  `cli._require_ui_assets()` refuses to serve when `static/index.html` is absent
  (otherwise the app mounts nothing and serves a bare 404), and `hatch_build.py`
  builds the bundle for the wheel target. That hook keys off
  `version == "editable"`, NOT `self.target_name` — hatchling builds an editable
  install as the *wheel* target, so a `target_name` check would never match and
  every `uv sync` would demand pnpm. The wheel ships `web/static/` and excludes
  `web/ui/` (`[tool.hatch.build.targets.wheel] exclude`).

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
  `make test-ui` as proof about reducers, the store, and the API client, not
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
- **A natural finish sticks; only an error clears.** `_drive`'s `finally`
  calls `_teardown(run, clear=self._state is WalkState.ERROR)` — a walk that
  reaches the end of its route leaves the device holding that last simulated
  fix, with no session left open, until a new walk or pin overwrites it.
  There is deliberately no "revert to real GPS" affordance for an idle device
  after a natural finish. An errored walk (lost device, exception) still
  clears, since a stuck fake position on top of an unclean state isn't a
  guarantee worth making. `stop()`'s own `_teardown(run)` call (Done, or an
  explicit Stop mid-walk) keeps the `clear=True` default throughout.
- **A live reroute is synchronous, so it can never race the tick loop.**
  `Walker.reroute(new_path)` and `run_walk`'s `advance()` never `await`
  anything, so calling `WalkService.reroute()` — itself lock-guarded like
  `start()`/`stop()` — from the same event loop can only run wholly before or
  wholly after a given tick, never interleaved with one. `reroute()` rebases
  path-relative position via `_reroute_offset_m` (set to the current
  `distance_m` at reroute time) rather than resetting `distance_m` itself,
  so the cumulative counter — the number reported to the user — never jumps.
  Reroute always plans `[current_fix, *appended_waypoints]` only, discarding
  whatever remained of the original route (append-only, no waypoint
  projection), and refuses a looping walk (`loop=True`) outright, since a
  route computed from an arbitrary live position is never a closed course.

## Config

`~/.config/ios-loc/config.toml`, overridable with `--config`. The file format, a
worked example of all three table kinds, and the layering rules are in README's
Config section. Routes cache to `~/.cache/ios-loc/routes` with atomic writes;
corrupt entries are discarded rather than trusted.

## Hardware verification

The test suite needs no device and no network, and covers everything except the
device layer. README's Notes section lists exactly what a real iPhone has and has
not confirmed — keep that list honest whenever device-facing behaviour changes, and
never let a green suite stand in for hardware proof on the paths it names.
