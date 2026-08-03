import type { LatLon } from "@/api/types"
import type { DraftRoute } from "@/lib/draft"

// A regex scanner rather than DOMParser: vitest's frontend suite is
// pure-logic-only (node environment, no jsdom -- see vitest.config.ts), so
// anything reachable from a test can't depend on a browser DOM API.

/** Which GPX element to read points from. `"auto"` is `parse_gpx`'s priority
 *  order (track, then route, then waypoints); the rest force one kind, for a
 *  file that holds more than one and needs the other one picked instead. */
export type GpxPointType = "auto" | "trkpt" | "rtept" | "wpt"

const GPX_TAGS_IN_PRIORITY = ["trkpt", "rtept", "wpt"] as const

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

function tooFew(tag: string, count: number): { error: string } {
  return { error: `GPX file has only ${count} <${tag}> point(s); a route needs at least 2` }
}

/**
 * Parse GPX XML into a `DraftRoute`. `pointType: "auto"` mirrors
 * `ios_loc.gpx.parse_gpx`'s priority: track points (`<trkpt>`, every
 * `<trkseg>` concatenated in document order) win over route points
 * (`<rtept>`), which win over waypoints (`<wpt>`) -- a recorded track is the
 * most literal description of a path a GPX file can hold, so it wins whenever
 * present. Any other `pointType` reads only that one element kind, for a file
 * that holds more than one and needs a specific one instead.
 */
export function gpxToRoute(
  text: string,
  literal: boolean,
  pointType: GpxPointType = "auto",
): DraftRoute | { error: string } {
  if (!/<gpx[\s>]/i.test(text)) {
    return { error: "not a GPX file (no <gpx> root element found)" }
  }
  try {
    if (pointType !== "auto") {
      const points = pointsFor(text, pointType)
      if (points.length === 0) return { error: `GPX file has no <${pointType}> points` }
      if (points.length < 2) return tooFew(pointType, points.length)
      return { waypoints: points, name: null, literal }
    }
    for (const tag of GPX_TAGS_IN_PRIORITY) {
      const points = pointsFor(text, tag)
      if (points.length === 0) continue
      if (points.length < 2) return tooFew(tag, points.length)
      return { waypoints: points, name: null, literal }
    }
  } catch (error) {
    return { error: error instanceof Error ? error.message : String(error) }
  }
  return { error: "GPX file has no <trkpt>, <rtept>, or <wpt> points" }
}
