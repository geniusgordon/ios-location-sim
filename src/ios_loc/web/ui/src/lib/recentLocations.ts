import type { LatLon } from "@/api/types"

export interface RecentLocation {
  point: LatLon
  ts: number
}

const STORAGE_KEY = "ios-loc:recent-locations"
const MAX_RECENTS = 8

interface Store {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
}

function defaultStore(): Store | null {
  return typeof localStorage === "undefined" ? null : localStorage
}

function samePoint(a: LatLon, b: LatLon): boolean {
  return a[0].toFixed(6) === b[0].toFixed(6) && a[1].toFixed(6) === b[1].toFixed(6)
}

function isRecentLocation(value: unknown): value is RecentLocation {
  if (!value || typeof value !== "object") return false
  const entry = value as { point?: unknown; ts?: unknown }
  return (
    Array.isArray(entry.point) &&
    entry.point.length === 2 &&
    typeof entry.point[0] === "number" &&
    typeof entry.point[1] === "number" &&
    typeof entry.ts === "number"
  )
}

/**
 * Reads the set-location history, most-recent first. Browser-local (never
 * sent to the server) -- unlike saved places, this is a recency aid, not
 * something to sync across devices. Never throws: a missing or corrupt entry
 * just means an empty history rather than a broken panel.
 */
export function loadRecents(store: Store | null = defaultStore()): RecentLocation[] {
  if (!store) return []
  try {
    const raw = store.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter(isRecentLocation) : []
  } catch {
    return []
  }
}

/**
 * Records a newly set point at the front of the history, deduping against any
 * existing entry for the same point (a re-pin moves it to the top rather than
 * appearing twice) and capping the list at MAX_RECENTS. Persists and returns
 * the new list.
 */
export function addRecent(
  point: LatLon,
  ts: number = Date.now(),
  store: Store | null = defaultStore(),
): RecentLocation[] {
  const next = [{ point, ts }, ...loadRecents(store).filter((entry) => !samePoint(entry.point, point))].slice(
    0,
    MAX_RECENTS,
  )
  store?.setItem(STORAGE_KEY, JSON.stringify(next))
  return next
}

/** Drops one entry from the history (the row's own remove button). */
export function removeRecent(point: LatLon, store: Store | null = defaultStore()): RecentLocation[] {
  const next = loadRecents(store).filter((entry) => !samePoint(entry.point, point))
  store?.setItem(STORAGE_KEY, JSON.stringify(next))
  return next
}
