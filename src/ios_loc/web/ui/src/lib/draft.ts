import { haversineM } from "@/lib/geo"
import type { LatLon, Preset } from "@/api/types"

/**
 * The one route on the map. `name` is set by loading a saved route or saving
 * this one, and cleared by the first edit afterwards: the moment the waypoints
 * stop being the preset, starting BY NAME would run the old route on the phone
 * while the map shows the new one.
 *
 * `literal` marks a pasted route: its waypoints are the exact path to walk,
 * with no Valhalla routing call. It survives ordinary edits (drag, add,
 * remove) -- those still describe the same literal path -- but never survives
 * loading a preset, which is always Valhalla-planned geometry.
 */
export interface DraftRoute {
  waypoints: LatLon[]
  name: string | null
  literal: boolean
}

/**
 * Every knob a start needs, held once and sticky across draws. `pace: null`
 * and a blank `durationMin` both mean "inherit the default", which the backend
 * models as null -- they must never be sent as 0.
 *
 * `pace` and `costing` are independent by design: pace is how fast, costing
 * ("Routing mode") is which way. Nothing here may derive one from the other.
 */
export interface DraftSettings {
  pace: string | null
  costing: string
  loop: boolean
  durationMin: string
  scatterM: string
}

export const emptyRoute: DraftRoute = { waypoints: [], name: null, literal: false }

export const defaultSettings: DraftSettings = {
  pace: "bike",
  costing: "pedestrian",
  loop: false,
  durationMin: "",
  scatterM: "3",
}

/**
 * Any edit produces an unnamed route -- see `DraftRoute.name` -- but keeps
 * whatever `literal` the route already had: editing a pasted path's points
 * still describes a literal path, not a re-interpretation as routed waypoints.
 */
function edited(waypoints: LatLon[], literal: boolean): DraftRoute {
  return { waypoints, name: null, literal }
}

export function addWaypoint(route: DraftRoute, point: LatLon): DraftRoute {
  return edited([...route.waypoints, point], route.literal)
}

export function moveWaypoint(route: DraftRoute, index: number, point: LatLon): DraftRoute {
  return edited(
    route.waypoints.map((p, i) => (i === index ? point : p)),
    route.literal,
  )
}

export function removeWaypoint(route: DraftRoute, index: number): DraftRoute {
  return edited(
    route.waypoints.filter((_, i) => i !== index),
    route.literal,
  )
}

export function removeLast(route: DraftRoute): DraftRoute {
  return edited(route.waypoints.slice(0, -1), route.literal)
}

export function clearRoute(): DraftRoute {
  return { waypoints: [], name: null, literal: false }
}

/**
 * Parse a pasted list of "lat, lon" lines into a `DraftRoute`. `literal` picks
 * whether the points are walked exactly as given (no Valhalla call) or sent as
 * waypoints for Valhalla to route between. Blank lines are ignored; anything
 * else that doesn't parse into an in-range coordinate pair fails the whole
 * paste with a message naming the offending line, rather than silently
 * dropping it.
 */
export function pasteRoute(text: string, literal: boolean): DraftRoute | { error: string } {
  const waypoints: LatLon[] = []
  const lines = text.split(/\r?\n/)
  for (const [index, rawLine] of lines.entries()) {
    const line = rawLine.trim()
    if (line.length === 0) continue
    const parts = line.split(",")
    if (parts.length !== 2) {
      return { error: `line ${index + 1}: expected "latitude, longitude", got ${JSON.stringify(rawLine)}` }
    }
    const lat = Number.parseFloat(parts[0])
    const lon = Number.parseFloat(parts[1])
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
      return { error: `line ${index + 1}: not two numbers: ${JSON.stringify(rawLine)}` }
    }
    if (lat < -90 || lat > 90 || lon < -180 || lon > 180) {
      return { error: `line ${index + 1}: out of range: latitude ${lat}, longitude ${lon}` }
    }
    waypoints.push([lat, lon])
  }
  if (waypoints.length < 2) {
    return { error: "a route needs at least 2 points" }
  }
  return { waypoints, name: null, literal }
}

/** Total length of a literal route, in metres -- no `/api/route` call to ask Valhalla instead. */
export function routeLengthM(waypoints: LatLon[]): number {
  let total = 0
  for (let i = 1; i < waypoints.length; i++) {
    total += haversineM(waypoints[i - 1], waypoints[i])
  }
  return total
}

/**
 * A saved route owns its pace, loop and costing -- costing included because it
 * describes the geometry that was saved, so loading a route must show the
 * Routing mode it was planned with rather than whatever the last draw used.
 * Duration and scatter stay as the user's current session preference.
 */
export function loadPreset(
  preset: Preset,
  settings: DraftSettings,
): { route: DraftRoute; settings: DraftSettings } {
  return {
    route: { waypoints: preset.waypoints as LatLon[], name: preset.name, literal: false },
    settings: {
      ...settings,
      pace: preset.pace,
      loop: preset.loop,
      costing: preset.costing,
    },
  }
}
