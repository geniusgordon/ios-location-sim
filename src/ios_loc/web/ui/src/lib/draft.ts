import type { LatLon, Preset } from "@/api/types"

/**
 * The one route on the map. `name` is set by loading a saved route or saving
 * this one, and cleared by the first edit afterwards: the moment the waypoints
 * stop being the preset, starting BY NAME would run the old route on the phone
 * while the map shows the new one.
 */
export interface DraftRoute {
  waypoints: LatLon[]
  name: string | null
}

/**
 * Every knob a start needs, held once and sticky across draws. `profile: null`
 * and a blank `durationMin` both mean "inherit the default", which the backend
 * models as null -- they must never be sent as 0.
 */
export interface DraftSettings {
  profile: string | null
  costing: string
  loop: boolean
  durationMin: string
  scatterM: string
}

export const emptyRoute: DraftRoute = { waypoints: [], name: null }

export const defaultSettings: DraftSettings = {
  profile: null,
  costing: "pedestrian",
  loop: false,
  durationMin: "",
  scatterM: "3",
}

/** Any edit produces an unnamed route -- see `DraftRoute.name`. */
function edited(waypoints: LatLon[]): DraftRoute {
  return { waypoints, name: null }
}

export function addWaypoint(route: DraftRoute, point: LatLon): DraftRoute {
  return edited([...route.waypoints, point])
}

export function moveWaypoint(route: DraftRoute, index: number, point: LatLon): DraftRoute {
  return edited(route.waypoints.map((p, i) => (i === index ? point : p)))
}

export function removeWaypoint(route: DraftRoute, index: number): DraftRoute {
  return edited(route.waypoints.filter((_, i) => i !== index))
}

export function removeLast(route: DraftRoute): DraftRoute {
  return edited(route.waypoints.slice(0, -1))
}

export function clearRoute(): DraftRoute {
  return { waypoints: [], name: null }
}

/**
 * A saved route owns its profile and loop; everything else (costing, duration,
 * scatter) is the user's current session preference and is left alone.
 */
export function loadPreset(
  preset: Preset,
  settings: DraftSettings,
): { route: DraftRoute; settings: DraftSettings } {
  return {
    route: { waypoints: preset.waypoints as LatLon[], name: preset.name },
    settings: { ...settings, profile: preset.profile, loop: preset.loop },
  }
}
