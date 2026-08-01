import type { StartRequest } from "@/api/types"
import type { DraftRoute, DraftSettings } from "@/lib/draft"

/**
 * THE place a StartRequest is built. Two inline copies of this in the quick bar
 * and the start form is exactly how the two paths drifted apart; keep it one
 * function so they cannot again.
 */
export function startBody(route: DraftRoute, settings: DraftSettings): StartRequest {
  const named = route.name !== null
  const minutes = Number.parseFloat(settings.durationMin)
  const scatter = Number.parseFloat(settings.scatterM)
  return {
    // Exactly one of these three -- the API rejects any other combination.
    preset: route.name,
    waypoints: !named && !route.literal ? route.waypoints : null,
    path: !named && route.literal ? route.waypoints : null,
    pace: settings.pace,
    speed: null,
    // Always sent, named route or not: "Routing mode" is the one thing that
    // decides costing, and it is never inferred from the pace. Loading a preset
    // seeds this select from that preset's saved costing (`loadPreset`), so
    // sending it back is a no-op unless the user deliberately changed it --
    // and then re-planning under the new mode is exactly what they asked for.
    costing: settings.costing,
    loop: settings.loop,
    duration_s: Number.isFinite(minutes) && minutes > 0 ? minutes * 60 : null,
    scatter_m: Number.isFinite(scatter) ? Math.min(100, Math.max(0, scatter)) : 3,
  }
}

/** One point is not a route. */
export function canStart(route: DraftRoute): boolean {
  return route.waypoints.length >= 2
}
