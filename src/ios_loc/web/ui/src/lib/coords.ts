import type { LatLon } from "@/api/types"

/**
 * THE conversion point. The API speaks [lat, lon]; MapLibre and GeoJSON speak
 * [lng, lat]. Every coordinate entering MapLibre goes through `toLngLat`, and
 * everything coming back out goes through `fromLngLat`. These two functions
 * are the ONLY places in the app that flip a pair — never open-code a swap.
 *
 * They live here rather than in MapView.tsx so that file exports only its
 * component (a mixed export breaks React fast refresh) and so the invariant
 * has one obvious home.
 */
export function toLngLat(point: LatLon): [number, number] {
  return [point[1], point[0]]
}

/** The inverse of `toLngLat`: MapLibre's {lng, lat} back to wire order. */
export function fromLngLat(lngLat: { lng: number; lat: number }): LatLon {
  return [lngLat.lat, lngLat.lng]
}

/**
 * Parse a pasted "lat,lon" pair like `48.858666,2.293991` into wire order.
 * Tolerates surrounding whitespace and a space after the comma. Returns an
 * error message rather than a silently clamped or zeroed coordinate — a wrong
 * pin is worse than a rejected one.
 */
export function parseLatLon(text: string): { point: LatLon } | { error: string } {
  const parts = text.trim().split(",")
  if (parts.length !== 2) {
    return { error: "Enter two numbers separated by a comma, e.g. 48.858666,2.293991" }
  }
  const lat = Number(parts[0].trim())
  const lon = Number(parts[1].trim())
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
    return { error: "Both values must be numbers, e.g. 48.858666,2.293991" }
  }
  if (lat < -90 || lat > 90) return { error: "Latitude must be between -90 and 90" }
  if (lon < -180 || lon > 180) return { error: "Longitude must be between -180 and 180" }
  return { point: [lat, lon] }
}

/** Render a point as "lat, lon" at 5 decimals -- the inverse of parseLatLon's
 *  accepted form, used to show the currently-set coordinate in the UI. */
export function formatLatLon(point: LatLon): string {
  return `${point[0].toFixed(5)}, ${point[1].toFixed(5)}`
}
