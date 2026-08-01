import type { LatLon } from "@/api/types"

const EARTH_RADIUS_M = 6_371_008.8

/** Great-circle distance between two [lat, lon] points, in metres. Mirrors `path.py`'s `haversine_m`. */
export function haversineM(a: LatLon, b: LatLon): number {
  const lat1 = (a[0] * Math.PI) / 180
  const lat2 = (b[0] * Math.PI) / 180
  const dLat = ((b[0] - a[0]) * Math.PI) / 180
  const dLon = ((b[1] - a[1]) * Math.PI) / 180
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2
  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(h))
}
