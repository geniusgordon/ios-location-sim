import { describe, expect, it } from "vitest"
import { formatDistance, formatDuration, formatSpeed } from "./format"

describe("formatDistance", () => {
  it("uses metres below a kilometre, with no decimals", () => {
    expect(formatDistance(0)).toBe("0 m")
    expect(formatDistance(940.6)).toBe("941 m")
  })

  it("switches to kilometres at 1000 m, with two decimals", () => {
    expect(formatDistance(1000)).toBe("1.00 km")
    expect(formatDistance(12345)).toBe("12.35 km")
  })
})

describe("formatDuration", () => {
  it("shows mm:ss below an hour", () => {
    expect(formatDuration(0)).toBe("00:00")
    expect(formatDuration(65)).toBe("01:05")
    expect(formatDuration(599.9)).toBe("09:59")
  })

  it("shows h:mm:ss at and above an hour", () => {
    expect(formatDuration(3600)).toBe("1:00:00")
    expect(formatDuration(3725)).toBe("1:02:05")
  })

  it("clamps negatives rather than printing a minus sign", () => {
    expect(formatDuration(-5)).toBe("00:00")
  })
})

describe("formatSpeed", () => {
  it("reports km/h, one decimal -- the unit the 20 km/h ceiling is stated in", () => {
    expect(formatSpeed(0)).toBe("0.0 km/h")
    expect(formatSpeed(1.4)).toBe("5.0 km/h")
    expect(formatSpeed(5.56)).toBe("20.0 km/h")
  })
})
