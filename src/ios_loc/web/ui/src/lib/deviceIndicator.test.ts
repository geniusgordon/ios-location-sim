import { describe, expect, it } from "vitest"
import type { DeviceStatus } from "@/api/types"
import { deviceIndicator } from "./deviceIndicator"

function status(reason: DeviceStatus["reason"], detail = "detail"): DeviceStatus {
  return { connected: reason === "ok", reason, detail }
}

describe("deviceIndicator", () => {
  it.each(["walking", "starting", "pinned"] as const)(
    "reports connected while the service holds the device (%s)",
    (state) => {
      const result = deviceIndicator(state, null)
      expect(result.connected).toBe(true)
      expect(result.label).toBe("Device")
      expect(result.tone).toBe("ok")
    },
  )

  it("reports a warn tone while reconnecting", () => {
    const result = deviceIndicator("reconnecting", null)
    expect(result.connected).toBe(false)
    expect(result.label).toBe("Reconnecting")
    expect(result.tone).toBe("warn")
  })

  it("reports an error tone once the device is lost", () => {
    const result = deviceIndicator("error", null)
    expect(result.connected).toBe(false)
    expect(result.label).toBe("Device lost")
    expect(result.tone).toBe("error")
  })

  it("shows a muted 'Checking…' state when idle with no probe yet", () => {
    const result = deviceIndicator("idle", null)
    expect(result.connected).toBe(false)
    expect(result.label).toBe("Checking…")
    expect(result.tone).toBe("muted")
  })

  it("reflects an ok probe when idle", () => {
    const result = deviceIndicator("idle", status("ok"))
    expect(result.connected).toBe(true)
    expect(result.label).toBe("Device")
  })

  it("reflects a no_device probe when idle", () => {
    const result = deviceIndicator("idle", status("no_device"))
    expect(result.connected).toBe(false)
    expect(result.label).toBe("No device")
    expect(result.tone).toBe("warn")
  })

  it("reflects a tunneld_down probe when idle", () => {
    const result = deviceIndicator("idle", status("tunneld_down"))
    expect(result.connected).toBe(false)
    expect(result.label).toBe("tunneld down")
    expect(result.tone).toBe("error")
  })

  it("reflects an error probe when idle", () => {
    const result = deviceIndicator("idle", status("error"))
    expect(result.connected).toBe(false)
    expect(result.label).toBe("No device")
    expect(result.tone).toBe("error")
  })

  it("also applies the same idle fallback for finished state", () => {
    const result = deviceIndicator("finished", status("ok"))
    expect(result.connected).toBe(true)
    expect(result.label).toBe("Device")
  })
})
