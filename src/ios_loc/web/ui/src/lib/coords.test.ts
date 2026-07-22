import { describe, expect, it } from "vitest"
import { formatLatLon, parseLatLon } from "./coords"

describe("parseLatLon", () => {
  it("parses a plain comma-separated pair", () => {
    expect(parseLatLon("48.858666,2.293991")).toEqual({ point: [48.858666, 2.293991] })
  })

  it("tolerates surrounding and post-comma whitespace", () => {
    expect(parseLatLon("  48.858666, 2.293991  ")).toEqual({
      point: [48.858666, 2.293991],
    })
  })

  it("parses negative coordinates", () => {
    expect(parseLatLon("-33.8688,151.2093")).toEqual({ point: [-33.8688, 151.2093] })
  })

  it("rejects out-of-range latitude", () => {
    const result = parseLatLon("200,2")
    expect("error" in result).toBe(true)
  })

  it("rejects out-of-range longitude", () => {
    const result = parseLatLon("48,200")
    expect("error" in result).toBe(true)
  })

  it("rejects a single number", () => {
    expect("error" in parseLatLon("48.858666")).toBe(true)
  })

  it("rejects non-numeric text", () => {
    expect("error" in parseLatLon("羅浮宮")).toBe(true)
  })

  it("rejects the empty string", () => {
    expect("error" in parseLatLon("")).toBe(true)
  })
})

describe("formatLatLon", () => {
  it("formats a point to 5 decimals, comma-space separated", () => {
    expect(formatLatLon([48.858666, 2.293991])).toBe("48.85867, 2.29399")
  })
  it("round-trips through parseLatLon", () => {
    const parsed = parseLatLon(formatLatLon([25.033, 121.5654]))
    expect("point" in parsed && parsed.point).toEqual([25.033, 121.5654])
  })
})
