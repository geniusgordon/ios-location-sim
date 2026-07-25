# ios-loc

Simulate GPS location on iOS 17+ devices from your Mac, built on
[`pymobiledevice3`](https://github.com/doronz88/pymobiledevice3).

Two ways to use it:

- **CLI** — hold a fixed point, or walk/cycle a routed path at a realistic pace
  for hours, with speed jitter, occasional pauses, and automatic reconnect if
  the tunnel drops.
- **Local map GUI** — a browser map for drawing routes, saving them, starting a
  walk, and watching the live position, served from `127.0.0.1`.

Nothing leaves your machine except routing requests and map tiles, and it only
ever talks to a device you have physically connected and trusted.

## System requirements

| | |
| --- | --- |
| Host | macOS (Linux may work via `pymobiledevice3`, untested here) |
| Python | 3.13 or newer |
| Package manager | [`uv`](https://docs.astral.sh/uv/) |
| Device | iPhone/iPad on **iOS 17+**, connected by USB and trusted |
| Privileges | `sudo`, once per boot, to start the tunnel daemon |
| Network | Internet for routing and map tiles — both avoidable, see `--offline` |
| Optional | Node 20+ and `pnpm`, only to modify the GUI frontend |

iOS 17 moved developer services behind a RemoteXPC tunnel that a privileged
process has to create — that is what `tunneld` below is, and why it needs
`sudo`. There is no Developer Disk Image to mount on modern iOS: the DVT
channel opens once the tunnel is up and the device is unlocked.

## Installation

```bash
git clone https://github.com/geniusgordon/ios-location-sim.git
cd ios-location-sim
uv sync                  # creates .venv and installs everything
uv run ios-loc --help
```

The GUI's built assets are committed, so `uv sync` is the whole install — no
frontend build needed to use the tool.

Start tunneld once per boot (needs sudo — it creates the Mac↔iPhone tunnel):

```bash
sudo pymobiledevice3 remote tunneld -d
```

Unlock the device, plug it in, and accept "Trust This Computer" if prompted.
Then check everything is reachable:

```bash
uv run ios-loc doctor
```

```
tunneld:  OK
device:   OK (iOS 26.6)
DVT:      OK — ready to simulate
```

If tunneld is not running, `doctor` says so and prints the command that fixes
it, rather than a traceback.

To install the CLI globally instead of running it from the checkout:

```bash
uv tool install .
ios-loc doctor
```

## Usage

```bash
# Walk a route, looping, for three hours
uv run ios-loc walk --via 25.033,121.565 --via 25.038,121.568 --loop --duration 3h

# Cycle instead (also switches routing to bicycle paths)
uv run ios-loc walk --via 25.033,121.565 --via 25.038,121.568 --profile bike --loop

# Use a named preset
uv run ios-loc walk home-loop
uv run ios-loc presets list

# Hold a fixed point
uv run ios-loc set 25.0330 121.5654

# Restore real GPS
uv run ios-loc clear
```

Other `walk` options worth knowing: `--speed` (m/s, overrides the profile),
`--scatter` (GPS noise in metres, default 3), `--duration` (`90s`, `20m`, `3h`),
`--offline`, `--log FILE`, `--no-clear` to leave the last position in place on
exit, and `--udid` to pick between multiple connected devices.

## Map GUI

```bash
uv run ios-loc gui               # serves 127.0.0.1:8765 and opens a browser
uv run ios-loc gui --no-open --port 9000
uv run ios-loc gui --offline     # disables routing; saved presets still work
uv run ios-loc gui --config ./my.toml   # alternate config file
uv run ios-loc gui --udid <UDID>        # pick a specific device
```

`--host` defaults to `127.0.0.1`; leave it there unless you really want control
of your phone's location reachable from the rest of your network.

![The map GUI: a drawn route on the Walk tab](docs/screenshot.png)

The page is a full-screen map beside a sidebar (open by default, collapsible;
it overlays the map on narrow screens). A chip at the top of the sidebar shows
whether a device is currently reachable. The sidebar has two tabs, and the tab
you are on decides what a map tap does:

- **Set location** — a coordinate box (paste `lat,lon`, e.g.
  `48.858666,2.293991`), a save-place form, and your saved places. On this tab,
  tapping the map holds the device at that point — the GUI form of `ios-loc
  set`. Naming a coordinate saves it as a place; picking one sets the device
  there. Stop releases it, same as it ends a walk. With no device connected the
  coordinate is still saved as a place, just not pushed to a phone.
- **Walk** — the route editor and everything a walk needs. On this tab, tapping
  the map adds a waypoint; drag to move one, click it to remove it. Each edit
  re-routes through Valhalla (debounced ~300 ms) and draws the returned
  polyline. Set profile, routing mode, loop, duration, and GPS scatter, then
  Start. Saving writes a `[presets.<name>]` table back to the config, so
  `ios-loc walk <name>` works on anything you draw, and your saved routes are
  listed below the editor. While a walk runs, this tab becomes the live view —
  elapsed, distance, speed, laps, reconnects, and a Stop button.

While a walk runs, the map follows the live dot with a fading trail of the last
120 fixes; panning detaches following and the crosshair button reattaches it.

Two things worth knowing:

- **The run lives in the server process.** Quitting `ios-loc gui` ends the walk.
  A walk started from a terminal is invisible to the GUI, and starting a second
  one from the browser fails at the device layer with the error shown in the UI.
  Relatedly: the GUI server owns the run, and a single Ctrl-C (or a plain
  `kill`/SIGTERM) clears the device and ends the walk before the process exits.
  A second Ctrl-C, or anything that force-kills the process (`kill -9`, a
  crash), skips that cleanup and leaves the device frozen at its last simulated
  location — if that happens, run `ios-loc clear` to recover it.
- **Saving a preset rewrites the `[presets.*]` tables.** Comments and hand
  formatting inside those tables are lost. `[profiles.*]` and every other section
  are preserved byte for byte, CRLF included.

The map needs network access for OpenStreetMap tiles even under `--offline`,
which disables routing only.

## Development

```bash
uv run pytest -q                          # full Python suite, ~2s, no device or network
uv run python scripts/export_openapi.py   # regenerate the OpenAPI schema the frontend types from
```

#### Developing the UI

```bash
cd src/ios_loc/web/ui
pnpm install
pnpm dev          # vite on 5173, proxying /api and /ws to uvicorn on 8765
pnpm test run     # pure-logic tests (reducer, store, follow mode, API client)
pnpm build        # writes the committed bundle to ../static
pnpm lint         # oxlint
pnpm gen:api      # regenerates src/api/schema.d.ts from api-schema.json
```

`src/ios_loc/web/static/` is committed, so `uv sync` alone is enough to run the
tool — but it means **a UI change is not shipped until you re-run `pnpm build`
and commit the result.**

## Config

`~/.config/ios-loc/config.toml` (override with `--config`):

```toml
[profiles.jog]
speed = 2.6            # m/s — must stay under 5.56 (20 km/h)
jitter = 0.10
pause_per_min = 0.05
pause_min_s = 5
pause_max_s = 20
costing = "pedestrian"

[presets.home-loop]
waypoints = [[25.033, 121.5654], [25.038, 121.568], [25.033, 121.5654]]
profile = "walk"
loop = true

[places.landmark]
point = [25.033, 121.565]
```

**Profiles** layer over the built-in `walk` and `bike`; a new profile name
inherits `walk`'s defaults for the fields it omits. **Presets** are routes with
waypoints, profile, and loop settings, loaded via the GUI or `ios-loc walk
<name>`. **Places** are single coordinates saved from the GUI's Set location
tab; picking one sets the device there. Deleting a route or place from the GUI
rewrites this file, preserving comments and hand formatting outside the
`[presets.*]` and `[places.*]` tables — `[profiles.*]` and every other section
are untouched.

## Notes

- **Speeds above 20 km/h are rejected.** Location-based games stop crediting
  distance above roughly that speed, so an over-speed run would silently
  produce nothing.
- **An outage costs distance, it never causes a jump.** If the device
  connection stalls mid-run, the walk picks up where it left off instead of
  firing a catch-up burst that would teleport the position.
- **Routes are cached** to `~/.cache/ios-loc/routes`. `--offline` fails fast rather
  than hitting the network, which is what you want for unattended overnight runs.
- **Routing uses the public FOSSGIS Valhalla server.** To run it locally instead,
  start `ghcr.io/gis-ops/docker-valhalla/valhalla` and point `ValhallaClient`'s
  `base_url` at `http://localhost:8002` — it speaks an identical API.
- **Hardware coverage is recorded honestly** in `docs/manual-verification.md`,
  including what has *not* been confirmed on a real device.

## Legal

Intended for testing your own apps and devices. Simulating location may violate
the terms of service of apps you use it with — that is your call to make. No
warranty; use at your own risk.
