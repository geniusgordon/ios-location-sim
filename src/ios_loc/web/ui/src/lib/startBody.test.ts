import { describe, expect, it } from "vitest"
import { defaultSettings, type DraftRoute } from "./draft"
import { canStart, startBody } from "./startBody"

const TWO: DraftRoute = { waypoints: [[1, 1], [2, 2]], name: null, literal: false }
const NAMED: DraftRoute = { waypoints: [[1, 1], [2, 2]], name: "riverside", literal: false }
const LITERAL: DraftRoute = { waypoints: [[1, 1], [2, 2]], name: null, literal: true }

describe("startBody", () => {
  // The API rejects both and neither -- exactly one of preset/waypoints.
  it("sends waypoints and costing for an unnamed route", () => {
    const body = startBody(TWO, { ...defaultSettings, costing: "bicycle" })
    expect(body.preset).toBeNull()
    expect(body.waypoints).toEqual([[1, 1], [2, 2]])
    expect(body.path).toBeNull()
    expect(body.costing).toBe("bicycle")
  })

  it("sends the name instead of waypoints for a named route", () => {
    const body = startBody(NAMED, defaultSettings)
    expect(body.preset).toBe("riverside")
    expect(body.waypoints).toBeNull()
    expect(body.path).toBeNull()
  })

  // The API rejects any combination other than exactly one of preset/waypoints/path.
  it("sends path instead of waypoints for a literal route", () => {
    const body = startBody(LITERAL, defaultSettings)
    expect(body.preset).toBeNull()
    expect(body.waypoints).toBeNull()
    expect(body.path).toEqual([[1, 1], [2, 2]])
  })

  // Routing mode is the only thing that decides costing. It is sent for a named
  // route too -- `loadPreset` seeds the select from that preset's saved costing,
  // so this echoes it back unless the user deliberately changed it.
  it("always sends the chosen costing, named route or not", () => {
    expect(startBody(NAMED, { ...defaultSettings, costing: "auto" }).costing).toBe("auto")
    expect(startBody(TWO, { ...defaultSettings, costing: "auto" }).costing).toBe("auto")
  })

  // The pace must never leak into the route: picking `bike` for its speed and
  // leaving Routing mode alone has to keep planning a pedestrian route.
  it("does not let the pace change the costing", () => {
    const body = startBody(TWO, { ...defaultSettings, pace: "bike" })
    expect(body.pace).toBe("bike")
    expect(body.costing).toBe("pedestrian")
  })

  it("sends null, not zero, for an unset pace and a blank duration", () => {
    const body = startBody(TWO, defaultSettings)
    expect(body.pace).toBeNull()
    expect(body.duration_s).toBeNull()
    expect(body.speed).toBeNull()
  })

  it("converts minutes to seconds and ignores junk or non-positive input", () => {
    expect(startBody(TWO, { ...defaultSettings, durationMin: "90" }).duration_s).toBe(5400)
    expect(startBody(TWO, { ...defaultSettings, durationMin: "abc" }).duration_s).toBeNull()
    expect(startBody(TWO, { ...defaultSettings, durationMin: "0" }).duration_s).toBeNull()
    expect(startBody(TWO, { ...defaultSettings, durationMin: "-5" }).duration_s).toBeNull()
  })

  // Clamped here rather than eating a 422 round trip on a fat-fingered value.
  it("clamps scatter to 0..100 and falls back to 3", () => {
    expect(startBody(TWO, { ...defaultSettings, scatterM: "250" }).scatter_m).toBe(100)
    expect(startBody(TWO, { ...defaultSettings, scatterM: "-4" }).scatter_m).toBe(0)
    expect(startBody(TWO, { ...defaultSettings, scatterM: "" }).scatter_m).toBe(3)
  })

  // Always a boolean: sending null for an unchecked switch would let a preset
  // saved with loop = true loop forever while the UI showed it off.
  it("always sends loop as a boolean", () => {
    expect(startBody(TWO, defaultSettings).loop).toBe(false)
    expect(startBody(NAMED, { ...defaultSettings, loop: true }).loop).toBe(true)
  })
})

describe("canStart", () => {
  it("needs two waypoints", () => {
    expect(canStart({ waypoints: [], name: null, literal: false })).toBe(false)
    expect(canStart({ waypoints: [[1, 1]], name: null, literal: false })).toBe(false)
    expect(canStart(TWO)).toBe(true)
  })
})
