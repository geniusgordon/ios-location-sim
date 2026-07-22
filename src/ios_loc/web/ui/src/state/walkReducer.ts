import type { Fix, LatLon, ServerMessage, Stats, WalkStateName, WalkStatus } from "@/api/types"

/**
 * How many recent fixes the map draws as a fading trail. Matches the server's
 * own ring buffer (service.py keeps ~120), so a mid-run connect and a long
 * live run show the same length of tail.
 */
export const TRAIL_LIMIT = 120

export interface WalkModel {
  state: WalkStateName
  error: string | null
  fix: Fix | null
  stats: Stats | null
  route: LatLon[]
  trail: Fix[]
  preset_name: string | null
  profile: string | null
  loop: boolean
  length_m: number | null
}

export const initialModel: WalkModel = {
  state: "idle",
  error: null,
  fix: null,
  stats: null,
  route: [],
  trail: [],
  preset_name: null,
  profile: null,
  loop: false,
  length_m: null,
}

function tail<T>(items: T[]): T[] {
  return items.length > TRAIL_LIMIT ? items.slice(items.length - TRAIL_LIMIT) : items
}

export function fromStatus(status: WalkStatus): WalkModel {
  return {
    state: status.state,
    error: status.error ?? null,
    fix: status.fix ?? null,
    stats: status.stats ?? null,
    route: (status.route ?? []) as LatLon[],
    trail: status.state === "pinned" ? [] : tail(status.trail ?? []),
    preset_name: status.preset_name ?? null,
    profile: status.profile ?? null,
    loop: status.loop ?? false,
    length_m: status.length_m ?? null,
  }
}

export function applyMessage(model: WalkModel, msg: ServerMessage): WalkModel {
  switch (msg.type) {
    case "snapshot":
      // A full replace, not a merge: the snapshot only ever arrives on a fresh
      // connection, and merging would keep a trail from the previous run.
      return fromStatus(msg.status)
    case "state":
      return { ...model, state: msg.state, error: msg.error }
    case "fix":
      return {
        ...model,
        state: msg.state,
        fix: msg.fix,
        stats: msg.stats,
        // A pinned "fix" is a set location, not a walk step: keep it out of the
        // trail so the map draws only the live dot, never an orange path line.
        trail: msg.state === "pinned" ? [] : tail([...model.trail, msg.fix]),
      }
  }
}

/**
 * The slice the map and sidebar care about — everything except the per-tick
 * telemetry. Task 4's store only notifies those components when this changes,
 * which is what keeps a 1 Hz fix from re-rendering the map.
 */
export interface WalkMeta {
  state: WalkStateName
  error: string | null
  route: LatLon[]
  preset_name: string | null
  profile: string | null
  loop: boolean
  length_m: number | null
}

export function metaOf(model: WalkModel): WalkMeta {
  return {
    state: model.state,
    error: model.error,
    route: model.route,
    preset_name: model.preset_name,
    profile: model.profile,
    loop: model.loop,
    length_m: model.length_m,
  }
}

export function metaEquals(a: WalkMeta, b: WalkMeta): boolean {
  if (
    a.state !== b.state ||
    a.error !== b.error ||
    a.preset_name !== b.preset_name ||
    a.profile !== b.profile ||
    a.loop !== b.loop ||
    a.length_m !== b.length_m
  ) {
    return false
  }
  if (a.route === b.route) return true
  if (a.route.length !== b.route.length) return false
  // Compared by value, not identity: a re-fetch of the same route must not
  // count as a change and force the map to redraw its line.
  for (let i = 0; i < a.route.length; i++) {
    if (a.route[i][0] !== b.route[i][0] || a.route[i][1] !== b.route[i][1]) return false
  }
  return true
}

/** True while the service holds the device — the states in which a start is refused. */
export function isRunning(state: WalkStateName): boolean {
  return state === "starting" || state === "walking" || state === "reconnecting"
}

/** True while the device is held — a walk OR a pin — the states with a live Stop. */
export function canStop(state: WalkStateName): boolean {
  return isRunning(state) || state === "pinned"
}

/**
 * Whether the dock shows the live telemetry view instead of the editor. A walk
 * (or a finished/lost run whose summary is still up) does; a bare pinned
 * location does NOT -- it is set-and-kept in place from the editor dock, so a
 * dock takeover would block setting the next location.
 */
export function showsLiveDock(state: WalkStateName, showSummary: boolean): boolean {
  return isRunning(state) || showSummary
}
