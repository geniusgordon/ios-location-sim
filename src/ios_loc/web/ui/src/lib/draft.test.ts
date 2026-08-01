import { describe, expect, it } from "vitest"
import type { Preset } from "@/api/types"
import {
  addWaypoint,
  clearRoute,
  defaultSettings,
  emptyRoute,
  loadPreset,
  moveWaypoint,
  pasteRoute,
  removeLast,
  removeWaypoint,
  routeLengthM,
} from "./draft"

const LOADED = {
  waypoints: [[1, 1], [2, 2]] as [number, number][],
  name: "riverside",
  literal: false,
}

describe("waypoint edits", () => {
  it("appends, moves and removes by index", () => {
    let route = addWaypoint(emptyRoute, [1, 1])
    route = addWaypoint(route, [2, 2])
    expect(route.waypoints).toEqual([[1, 1], [2, 2]])

    route = moveWaypoint(route, 0, [3, 3])
    expect(route.waypoints).toEqual([[3, 3], [2, 2]])

    route = removeWaypoint(route, 0)
    expect(route.waypoints).toEqual([[2, 2]])
  })

  it("removeLast drops the tail and tolerates an empty route", () => {
    expect(removeLast(addWaypoint(emptyRoute, [1, 1])).waypoints).toEqual([])
    expect(removeLast(emptyRoute).waypoints).toEqual([])
  })

  it("never mutates its input", () => {
    const before = addWaypoint(emptyRoute, [1, 1])
    addWaypoint(before, [2, 2])
    expect(before.waypoints).toEqual([[1, 1]])
  })

  it("preserves a literal route through edits", () => {
    const literal = { waypoints: [[1, 1], [2, 2]] as [number, number][], name: null, literal: true }
    expect(addWaypoint(literal, [3, 3]).literal).toBe(true)
    expect(moveWaypoint(literal, 0, [3, 3]).literal).toBe(true)
    expect(removeWaypoint(literal, 0).literal).toBe(true)
    expect(removeLast(literal).literal).toBe(true)
  })
})

describe("the name", () => {
  // The rule the whole model exists for: a named route that no longer matches
  // the preset must not start BY NAME -- that runs the old route on the phone.
  it("is cleared by every edit", () => {
    expect(addWaypoint(LOADED, [3, 3]).name).toBeNull()
    expect(moveWaypoint(LOADED, 0, [3, 3]).name).toBeNull()
    expect(removeWaypoint(LOADED, 0).name).toBeNull()
    expect(removeLast(LOADED).name).toBeNull()
  })

  it("survives a load", () => {
    const preset = {
      name: "riverside",
      waypoints: [[1, 1], [2, 2]],
      pace: "bike",
      loop: true,
      costing: "bicycle",
    } as unknown as Preset
    const result = loadPreset(preset, defaultSettings)
    expect(result.route).toEqual({
      waypoints: [[1, 1], [2, 2]],
      name: "riverside",
      literal: false,
    })
    expect(result.settings.pace).toBe("bike")
    expect(result.settings.loop).toBe(true)
  })

  // The saved costing describes the saved geometry, so it must win over
  // whatever the previous draw happened to leave in the select.
  it("adopts the preset's costing", () => {
    const preset = {
      name: "riverside",
      waypoints: [[1, 1], [2, 2]],
      pace: "walk",
      loop: false,
      costing: "auto",
    } as unknown as Preset
    const result = loadPreset(preset, { ...defaultSettings, costing: "bicycle" })
    expect(result.settings.costing).toBe("auto")
  })

  it("keeps settings the preset does not own", () => {
    const preset = {
      name: "x",
      waypoints: [[1, 1], [2, 2]],
      pace: "walk",
      loop: false,
      costing: "pedestrian",
    } as unknown as Preset
    const settings = { ...defaultSettings, durationMin: "45", scatterM: "9" }
    const result = loadPreset(preset, settings)
    expect(result.settings.durationMin).toBe("45")
    expect(result.settings.scatterM).toBe("9")
  })
})

describe("clearRoute", () => {
  it("empties the waypoints and the name", () => {
    expect(clearRoute()).toEqual({ waypoints: [], name: null, literal: false })
  })
})

describe("pasteRoute", () => {
  it("parses lat, lon lines into a literal route", () => {
    const result = pasteRoute("19.03709, 78.644732\n19.038134, 78.646628\n")
    expect(result).toEqual({
      waypoints: [
        [19.03709, 78.644732],
        [19.038134, 78.646628],
      ],
      name: null,
      literal: true,
    })
  })

  it("ignores blank lines", () => {
    const result = pasteRoute("19.0, 78.0\n\n   \n19.1, 78.1\n")
    expect("error" in result ? result.error : result.waypoints).toEqual([
      [19.0, 78.0],
      [19.1, 78.1],
    ])
  })

  it("rejects a line that is not two numbers", () => {
    const result = pasteRoute("19.0, 78.0\nnope\n19.1, 78.1")
    expect(result).toEqual({ error: expect.stringContaining("line 2") })
  })

  it("rejects an out-of-range coordinate", () => {
    const result = pasteRoute("190.0, 78.0\n19.1, 78.1")
    expect(result).toEqual({ error: expect.stringContaining("out of range") })
  })

  it("rejects fewer than 2 points", () => {
    const result = pasteRoute("19.0, 78.0")
    expect(result).toEqual({ error: expect.stringContaining("at least 2") })
  })
})

describe("routeLengthM", () => {
  it("is zero for fewer than 2 points", () => {
    expect(routeLengthM([])).toBe(0)
    expect(routeLengthM([[1, 1]])).toBe(0)
  })

  it("sums segment distances", () => {
    // 1 degree of latitude is ~111.2 km.
    const length = routeLengthM([
      [0, 0],
      [1, 0],
      [2, 0],
    ])
    expect(length).toBeGreaterThan(220_000)
    expect(length).toBeLessThan(224_000)
  })
})
