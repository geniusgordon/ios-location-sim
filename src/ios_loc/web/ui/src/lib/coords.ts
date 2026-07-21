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
