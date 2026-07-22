import { describe, expect, it } from "vitest"
import type { Preset } from "@/api/types"
import {
  addWaypoint,
  clearRoute,
  defaultSettings,
  emptyRoute,
  loadPreset,
  moveWaypoint,
  removeLast,
  removeWaypoint,
} from "./draft"

const LOADED = { waypoints: [[1, 1], [2, 2]] as [number, number][], name: "riverside" }

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
      profile: "bike",
      loop: true,
    } as unknown as Preset
    const result = loadPreset(preset, defaultSettings)
    expect(result.route).toEqual({ waypoints: [[1, 1], [2, 2]], name: "riverside" })
    expect(result.settings.profile).toBe("bike")
    expect(result.settings.loop).toBe(true)
  })

  it("keeps settings the preset does not own", () => {
    const preset = {
      name: "x",
      waypoints: [[1, 1], [2, 2]],
      profile: "walk",
      loop: false,
    } as unknown as Preset
    const settings = { ...defaultSettings, costing: "bicycle", scatterM: "9" }
    const result = loadPreset(preset, settings)
    expect(result.settings.costing).toBe("bicycle")
    expect(result.settings.scatterM).toBe("9")
  })
})

describe("clearRoute", () => {
  it("empties the waypoints and the name", () => {
    expect(clearRoute()).toEqual(emptyRoute)
  })
})
