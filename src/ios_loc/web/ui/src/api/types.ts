import type { components } from "./schema"

type S = components["schemas"]

export type Fix = S["FixOut"]
export type Stats = S["StatsOut"]
export type Preset = S["PresetOut"]
export type Pace = S["PaceOut"]
export type PresetsList = S["PresetsListOut"]
export type PresetIn = S["PresetIn"]
export type RouteRequest = S["RouteRequest"]
export type RouteResponse = S["RouteResponse"]
export type RerouteRequest = S["RerouteRequest"]
export type StartRequest = S["StartRequest"]
export type WalkStatus = S["WalkStatus"]
export type WalkStateName = S["WalkState"]
export type PinRequest = S["PinRequest"]
export type Place = S["PlaceOut"]
export type PlaceIn = S["PlaceIn"]
export type PlacesList = S["PlacesListOut"]
export type DeviceStatus = S["DeviceStatus"]

/** `[latitude, longitude]` — the wire order everywhere in this API. */
export type LatLon = [number, number]

// --- WebSocket messages -----------------------------------------------------
// Not in OpenAPI (it cannot describe WebSockets). These mirror, byte for byte:
//   api.py:160          -> {"type": "snapshot", "status": WalkStatus}
//   service.py:197 etc. -> {"type": "state", "state": ..., "error": ..., "stats"?: ...}
//   service.py:385      -> {"type": "fix", "fix": ..., "stats": ..., "state": ...}
// Only the snapshot carries `route` and `trail`, and it is sent exactly once
// per connection.

export interface SnapshotMessage {
  type: "snapshot"
  status: WalkStatus
}

export interface StateMessage {
  type: "state"
  state: WalkStateName
  error: string | null
  /**
   * Only on a terminal state (`service.py`'s final broadcast), absent on every
   * other state message. These are the authoritative numbers and can be one
   * tick ahead of the last "fix" message: `run_walk` counts a tick before
   * `session.set()` is awaited, while `on_fix` only runs after a *successful*
   * set, so a run ending on a lost session never broadcasts its last tick.
   */
  stats?: Stats | null
}

export interface FixMessage {
  type: "fix"
  fix: Fix
  stats: Stats
  state: WalkStateName
}

/** A live reroute applied mid-walk (service.py:WalkService.reroute) — sent to
 *  every connected client, not just the one that clicked Apply. */
export interface RouteMessage {
  type: "route"
  route: LatLon[]
  length_m: number
}

export type ServerMessage = SnapshotMessage | StateMessage | FixMessage | RouteMessage
