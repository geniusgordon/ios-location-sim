import type { components } from "./schema"

type S = components["schemas"]

export type Fix = S["FixOut"]
export type Stats = S["StatsOut"]
export type Preset = S["PresetOut"]
export type PresetsList = S["PresetsListOut"]
export type PresetIn = S["PresetIn"]
export type RouteRequest = S["RouteRequest"]
export type RouteResponse = S["RouteResponse"]
export type StartRequest = S["StartRequest"]
export type WalkStatus = S["WalkStatus"]
export type WalkStateName = S["WalkState"]
export type PinRequest = S["PinRequest"]

/** `[latitude, longitude]` — the wire order everywhere in this API. */
export type LatLon = [number, number]

// --- WebSocket messages -----------------------------------------------------
// Not in OpenAPI (it cannot describe WebSockets). These mirror, byte for byte:
//   api.py:160          -> {"type": "snapshot", "status": WalkStatus}
//   service.py:197 etc. -> {"type": "state", "state": ..., "error": ...}
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
}

export interface FixMessage {
  type: "fix"
  fix: Fix
  stats: Stats
  state: WalkStateName
}

export type ServerMessage = SnapshotMessage | StateMessage | FixMessage
