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
    // Exactly one of these -- the API rejects both and neither.
    preset: route.name,
    waypoints: named ? null : route.waypoints,
    profile: settings.profile,
    speed: null,
    // A named route carries its own costing server-side; sending one would
    // silently re-route it.
    costing: named ? null : settings.costing,
    loop: settings.loop,
    duration_s: Number.isFinite(minutes) && minutes > 0 ? minutes * 60 : null,
    scatter_m: Number.isFinite(scatter) ? Math.min(100, Math.max(0, scatter)) : 3,
  }
}

/** One point is not a route. */
export function canStart(route: DraftRoute): boolean {
  return route.waypoints.length >= 2
}
