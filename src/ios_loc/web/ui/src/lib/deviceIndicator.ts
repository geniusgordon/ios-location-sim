import type { DeviceStatus, WalkStateName } from "@/api/types"

export interface DeviceIndicator {
  connected: boolean
  label: string
  tone: "ok" | "warn" | "error" | "muted"
  detail: string
}

/**
 * The single source of the displayed device-connectivity indicator. While the
 * service holds the device (walking/starting/pinned/reconnecting/error), the
 * walk STATE is the truth -- polling then would open a second tunnel and could
 * show a stale value. Otherwise fall back to the polled `/api/device` probe.
 */
export function deviceIndicator(state: WalkStateName, polled: DeviceStatus | null): DeviceIndicator {
  switch (state) {
    case "walking":
    case "starting":
    case "pinned":
      return { connected: true, label: "Device", tone: "ok", detail: "Device connected" }
    case "reconnecting":
      return { connected: false, label: "Reconnecting", tone: "warn", detail: "Reconnecting to the device…" }
    case "error":
      return { connected: false, label: "Device lost", tone: "error", detail: "The device was lost" }
    default:
      break
  }
  if (!polled) return { connected: false, label: "Checking…", tone: "muted", detail: "Checking for a device…" }
  switch (polled.reason) {
    case "ok":
      return { connected: true, label: "Device", tone: "ok", detail: polled.detail }
    case "no_device":
      return { connected: false, label: "No device", tone: "warn", detail: polled.detail }
    case "tunneld_down":
      return { connected: false, label: "tunneld down", tone: "error", detail: polled.detail }
    default:
      return { connected: false, label: "No device", tone: "error", detail: polled.detail }
  }
}
