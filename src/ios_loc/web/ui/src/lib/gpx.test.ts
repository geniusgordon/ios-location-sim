import { describe, expect, it } from "vitest"
import { gpxToRoute } from "./gpx"

function wrap(body: string): string {
  return `<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
${body}
</gpx>`
}

describe("gpxToRoute", () => {
  it("parses track points across multiple segments", () => {
    const gpx = wrap(`
      <trk>
        <trkseg>
          <trkpt lat="25.0" lon="121.0"></trkpt>
          <trkpt lat="25.1" lon="121.1"></trkpt>
        </trkseg>
        <trkseg>
          <trkpt lat="25.2" lon="121.2"></trkpt>
        </trkseg>
      </trk>
    `)
    expect(gpxToRoute(gpx, true)).toEqual({
      waypoints: [
        [25.0, 121.0],
        [25.1, 121.1],
        [25.2, 121.2],
      ],
      name: null,
      literal: true,
    })
  })

  it("falls back to route points, then waypoints", () => {
    const rte = wrap(`<rte><rtept lat="25.0" lon="121.0"></rtept><rtept lat="25.1" lon="121.1"></rtept></rte>`)
    expect(gpxToRoute(rte, false)).toEqual({
      waypoints: [
        [25.0, 121.0],
        [25.1, 121.1],
      ],
      name: null,
      literal: false,
    })

    const wpt = wrap(`<wpt lat="25.0" lon="121.0"></wpt><wpt lat="25.1" lon="121.1"></wpt>`)
    expect(gpxToRoute(wpt, false)).toEqual({
      waypoints: [
        [25.0, 121.0],
        [25.1, 121.1],
      ],
      name: null,
      literal: false,
    })
  })

  it("prefers track points over route points and waypoints", () => {
    const gpx = wrap(`
      <wpt lat="1.0" lon="1.0"></wpt>
      <rte><rtept lat="2.0" lon="2.0"></rtept><rtept lat="2.1" lon="2.1"></rtept></rte>
      <trk><trkseg>
        <trkpt lat="25.0" lon="121.0"></trkpt>
        <trkpt lat="25.1" lon="121.1"></trkpt>
      </trkseg></trk>
    `)
    const result = gpxToRoute(gpx, true)
    expect(result).toEqual({
      waypoints: [
        [25.0, 121.0],
        [25.1, 121.1],
      ],
      name: null,
      literal: true,
    })
  })

  it("rejects text with no <gpx> root", () => {
    expect(gpxToRoute("not xml at all", true)).toEqual({
      error: "not a GPX file (no <gpx> root element found)",
    })
  })

  it("rejects a point missing lat or lon", () => {
    const gpx = wrap(`<trk><trkseg><trkpt lon="121.0"></trkpt><trkpt lat="25.1" lon="121.1"></trkpt></trkseg></trk>`)
    const result = gpxToRoute(gpx, true)
    expect("error" in result && result.error).toMatch(/missing a lat or lon/)
  })

  it("rejects a non-numeric lat/lon", () => {
    const gpx = wrap(
      `<trk><trkseg><trkpt lat="north" lon="121.0"></trkpt><trkpt lat="25.1" lon="121.1"></trkpt></trkseg></trk>`,
    )
    const result = gpxToRoute(gpx, true)
    expect("error" in result && result.error).toMatch(/non-numeric/)
  })

  it("rejects a single point", () => {
    const gpx = wrap(`<trk><trkseg><trkpt lat="25.0" lon="121.0"></trkpt></trkseg></trk>`)
    const result = gpxToRoute(gpx, true)
    expect("error" in result && result.error).toMatch(/at least 2/)
  })

  it("rejects a file with no points at all", () => {
    const gpx = wrap(`<metadata></metadata>`)
    const result = gpxToRoute(gpx, true)
    expect("error" in result && result.error).toMatch(/no <trkpt>, <rtept>, or <wpt>/)
  })

  it("an explicit pointType reads only that element kind", () => {
    const gpx = wrap(`
      <wpt lat="1.0" lon="1.0"></wpt>
      <wpt lat="1.1" lon="1.1"></wpt>
      <trk><trkseg>
        <trkpt lat="25.0" lon="121.0"></trkpt>
        <trkpt lat="25.1" lon="121.1"></trkpt>
      </trkseg></trk>
    `)
    expect(gpxToRoute(gpx, true, "wpt")).toEqual({
      waypoints: [
        [1.0, 1.0],
        [1.1, 1.1],
      ],
      name: null,
      literal: true,
    })
  })

  it("an explicit pointType errors when that element kind is absent", () => {
    const gpx = wrap(`<trk><trkseg><trkpt lat="25.0" lon="121.0"></trkpt><trkpt lat="25.1" lon="121.1"></trkpt></trkseg></trk>`)
    expect(gpxToRoute(gpx, true, "rtept")).toEqual({ error: "GPX file has no <rtept> points" })
  })
})
