# ios-loc

Simulate GPS location on iOS 17+ devices, built on `pymobiledevice3`.

## Setup

```bash
uv sync
```

Start tunneld once per boot (needs sudo — it creates the Mac↔iPhone tunnel):

```bash
sudo pymobiledevice3 remote tunneld -d
```

Then check everything is reachable:

```bash
uv run ios-loc doctor
```

## Usage

```bash
# Walk a route, looping, for three hours
uv run ios-loc walk --via 25.033,121.565 --via 25.038,121.568 --loop --duration 3h

# Cycle instead (also switches routing to bicycle paths)
uv run ios-loc walk --via 25.033,121.565 --via 25.038,121.568 --profile bike --loop

# Use a named preset
uv run ios-loc walk home-loop

# Hold a fixed point
uv run ios-loc set 25.0330 121.5654

# Restore real GPS
uv run ios-loc clear
```

## Config

`~/.config/ios-loc/config.toml`:

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
```

## Notes

- **Speeds above 20 km/h are rejected.** Pikmin Bloom stops crediting distance
  above roughly that speed, so an over-speed run would silently produce nothing.
- **Routes are cached** to `~/.cache/ios-loc/routes`. `--offline` fails fast rather
  than hitting the network, which is what you want for unattended overnight runs.
- **Routing uses the public FOSSGIS Valhalla server.** To run it locally instead,
  start `ghcr.io/gis-ops/docker-valhalla/valhalla` and point `ValhallaClient`'s
  `base_url` at `http://localhost:8002` — it speaks an identical API.
