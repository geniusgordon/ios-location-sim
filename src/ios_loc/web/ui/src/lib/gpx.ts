import type { LatLon } from "@/api/types"
import type { DraftRoute } from "@/lib/draft"

// A regex scanner rather than DOMParser: vitest's frontend suite is
// pure-logic-only (node environment, no jsdom -- see vitest.config.ts), so
// anything reachable from a test can't depend on a browser DOM API.

function attr(tagAttrs: string, name: string): string | null {
  const match = tagAttrs.match(new RegExp(`\\b${name}\\s*=\\s*(?:"([^"]*)"|'([^']*)')`))
  if (!match) return null
  return match[1] ?? match[2] ?? null
}

function pointsFor(text: string, tag: string): LatLon[] {
  const points: LatLon[] = []
  const tagRe = new RegExp(`<${tag}\\b([^>]*?)/?>`, "g")
  for (const match of text.matchAll(tagRe)) {
    const tagAttrs = match[1]
    const latRaw = attr(tagAttrs, "lat")
    const lonRaw = attr(tagAttrs, "lon")
    if (latRaw === null || lonRaw === null) {
      throw new Error(`<${tag}> is missing a lat or lon attribute`)
    }
    const lat = Number.parseFloat(latRaw)
    const lon = Number.parseFloat(lonRaw)
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
      throw new Error(
        `<${tag}> has a non-numeric lat/lon: ${JSON.stringify(latRaw)}, ${JSON.stringify(lonRaw)}`,
      )
    }
    if (lat < -90 || lat > 90 || lon < -180 || lon > 180) {
      throw new Error(`<${tag}> out of range: latitude ${lat}, longitude ${lon}`)
    }
    points.push([lat, lon])
  }
  return points
}

/**
 * Parse GPX XML into a `DraftRoute`. Mirrors `ios_loc.gpx.parse_gpx`'s
 * priority: track points (`<trkpt>`, every `<trkseg>` concatenated in
 * document order) win over route points (`<rtept>`), which win over waypoints
 * (`<wpt>`) -- a recorded track is the most literal description of a path a
 * GPX file can hold, so it wins whenever present.
 */
export function gpxToRoute(text: string, literal: boolean): DraftRoute | { error: string } {
  if (!/<gpx[\s>]/i.test(text)) {
    return { error: "not a GPX file (no <gpx> root element found)" }
  }
  try {
    for (const tag of ["trkpt", "rtept", "wpt"]) {
      const points = pointsFor(text, tag)
      if (points.length === 0) continue
      if (points.length < 2) {
        return {
          error: `GPX file has only ${points.length} <${tag}> point(s); a route needs at least 2`,
        }
      }
      return { waypoints: points, name: null, literal }
    }
  } catch (error) {
    return { error: error instanceof Error ? error.message : String(error) }
  }
  return { error: "GPX file has no <trkpt>, <rtept>, or <wpt> points" }
}
